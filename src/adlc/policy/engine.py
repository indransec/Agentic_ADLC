"""The policy engine (contracts/policy-engine.md; SA §9; constitution VI, XI).

``evaluate`` never raises: every outcome other than ``true`` is "not passed" with a reason.
Conditions about approvals and follow-on events use a fail-safe direction when they cannot be
evaluated (research R-09). Every call writes one decision record and runs in a span.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from celpy import celtypes
from celpy.evaluation import CELEvalError

from adlc.orchestration.interfaces import Clock, EvalContext, EvalResult, SystemClock
from adlc.orchestration.tracing import span
from adlc.policy import activation as act
from adlc.policy import authorization
from adlc.policy.compiler import compile_rule, program, register_functions
from adlc.policy.evidence import Answer, EvidenceProvider
from adlc.policy.predicates import PredicateFn, check_catalogue
from adlc.policy.predicates.context import CallContext, bind, unbind
from adlc.policy.store import DecisionSink, NullSink, PolicyDecision
from adlc.policy.values import to_json

TIME_LIMIT_MS = 1000.0
APPROVAL_PREFIXES = ("plus:", "external:")
FOLLOW_ON_PREFIX = "then_when:"


class CatalogueMismatch(RuntimeError):
    """The predicate library does not match predicates.yaml (FR-002)."""


@dataclass(frozen=True)
class Outcome:
    passed: bool
    value: Any
    reason: str


class CelPolicyEngine:
    def __init__(
        self,
        evidence: EvidenceProvider,
        predicates: Mapping[str, tuple[PredicateFn, int]],
        *,
        catalogue: Callable[[str], Mapping[str, Any] | None] = lambda name: None,
        spec_for: Callable[[EvalContext], Mapping[str, Any] | None] = lambda ctx: None,
        sink: DecisionSink | None = None,
        clock: Clock | None = None,
        timer: Callable[[], float] = time.perf_counter,
        predicate_catalogue: Mapping[str, Any] | None = None,
    ) -> None:
        if predicate_catalogue is not None:
            problems = check_catalogue(predicate_catalogue, predicates)
            if problems:
                raise CatalogueMismatch("; ".join(problems))
        self.evidence = evidence
        self.catalogue = catalogue
        self.spec_for = spec_for
        self.sink = sink or NullSink()
        self.clock = clock or SystemClock()
        self.timer = timer
        self._functions_key = register_functions({n: fn for n, (fn, _) in predicates.items()})

    # -------------------------------------------------------------- evaluate

    def evaluate(self, expression: str, context: EvalContext) -> EvalResult:
        with span(
            "policy",
            "evaluate",
            run_id=context.run_id,
            usecase_id=context.usecase_id,
            terminal_id=context.terminal_id,
        ) as s:
            s.set_attribute("check_id", context.check_id)
            started = self.timer()
            inputs = act.Inputs()
            outcome = self._evaluate(expression, context, inputs)
            elapsed_ms = (self.timer() - started) * 1000
            if elapsed_ms > TIME_LIMIT_MS:
                outcome = Outcome(
                    False, outcome.value, f"evaluation too slow ({elapsed_ms:.0f} ms)"
                )
            outcome, fail_safe = _apply_fail_safe(context.check_id, outcome)
            self.sink.record(
                PolicyDecision(
                    kind="evaluate",
                    check_id=context.check_id,
                    rule=expression,
                    passed=outcome.passed,
                    reason=outcome.reason,
                    run_id=context.run_id,
                    usecase_id=context.usecase_id,
                    terminal_id=context.terminal_id,
                    value=_safe_json(outcome.value),
                    inputs=inputs.read,
                    synthetic=inputs.synthetic,
                    fail_safe=fail_safe,
                    duration_ms=elapsed_ms,
                    attempt=context.attempt,
                )
            )
            return EvalResult(
                passed=outcome.passed,
                value=_safe_json(outcome.value),
                reason=outcome.reason,
                synthetic=inputs.synthetic,
            )

    def _evaluate(self, expression: str, context: EvalContext, inputs: act.Inputs) -> Outcome:
        compiled = compile_rule(expression)
        if compiled.error is not None or compiled.ast is None:
            return Outcome(False, None, f"evaluation error: {compiled.error}")
        cache: dict[str, Answer] = {}

        def fetch(source: str) -> Answer:
            if source not in cache:
                cache[source] = self.evidence.get(source, context)
            return cache[source]

        call = CallContext(
            eval=context,
            fetch=self._recording_fetch(fetch, inputs),
            catalogue=self.catalogue,
            spec=self.spec_for(context),
            nested=lambda expr, check: self.evaluate(expr, _nested(context, check)),
            now=self.clock.now(),
        )
        try:
            answers = {root: fetch(root) for root in compiled.roots}
            built = act.build(expression, compiled.refs, answers, inputs)
            runnable = program(built.text, self._functions_key)
            token = bind(call)
            try:
                value = runnable.evaluate(built.variables)
            finally:
                unbind(token)
        except act.TooLarge as exc:
            return Outcome(False, None, f"evidence too large: {exc}")
        except CELEvalError as exc:
            return Outcome(False, None, _error_reason(exc, call, inputs))
        except Exception as exc:  # fail closed on anything else (FR-004)
            return Outcome(False, None, f"evaluation error: {type(exc).__name__}: {exc}")
        if isinstance(value, CELEvalError):
            return Outcome(False, None, _error_reason(value, call, inputs))
        if not isinstance(value, celtypes.BoolType | bool):
            return Outcome(False, value, f"rule did not return true/false: {to_json(value)!r}")
        if bool(value):
            return Outcome(True, True, "passed")
        reason = call.reasons[0] if call.reasons else f"rule is false: {expression}"
        return Outcome(False, False, reason)

    @staticmethod
    def _recording_fetch(
        fetch: Callable[[str], Answer], inputs: act.Inputs
    ) -> Callable[[str], Answer]:
        def recording(source: str) -> Answer:
            answer = fetch(source)
            if hasattr(answer, "value"):
                inputs.add(source, answer.value, answer.source, answer.synthetic)  # type: ignore[union-attr]
            else:
                inputs.missing(source)
            return answer

        return recording

    # -------------------------------------------------------------- authorize

    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool:
        return self.authorize_decision(actor, action, resource, context)[0]

    def authorize_decision(
        self, actor: str, action: str, resource: str, context: EvalContext
    ) -> tuple[bool, str]:
        with span(
            "policy",
            "authorize",
            run_id=context.run_id,
            usecase_id=context.usecase_id,
            terminal_id=context.terminal_id,
        ):
            started = self.timer()
            spec = self.spec_for(context)
            run = self.evidence.get("run", context)  # 012: mode-conditional tool scopes
            value = getattr(run, "value", None)
            mode = value.get("mode") if isinstance(value, dict) else None
            allowed, reason = authorization.decide(
                actor, action, resource, context.run_id, spec, mode
            )
            self.sink.record(
                PolicyDecision(
                    kind="authorize",
                    check_id="authorize",
                    rule=authorization.request(action, resource),
                    passed=allowed,
                    reason=reason,
                    run_id=context.run_id,
                    usecase_id=context.usecase_id,
                    terminal_id=context.terminal_id,
                    actor=actor,
                    duration_ms=(self.timer() - started) * 1000,
                )
            )
            return allowed, reason


def _nested(context: EvalContext, check_id: str) -> EvalContext:
    return EvalContext(
        context.terminal_id, check_id, context.run_id, context.usecase_id, context.variables
    )


def _error_reason(exc: CELEvalError, call: CallContext, inputs: act.Inputs) -> str:
    message = str(exc.args[0]) if exc.args else str(exc)
    if message.startswith("evidence not available"):
        return message
    if call.reasons:
        return call.reasons[0]
    missing = [path for path, read in inputs.read.items() if read["source"] == "not available"]
    if missing:  # CEL folds several missing values into one operator error; name the first
        return f"evidence not available: {missing[0]}"
    return f"evaluation error: {message}"


def _apply_fail_safe(check_id: str, outcome: Outcome) -> tuple[Outcome, bool]:
    """R-09: an approval condition that cannot be decided requires the approval; a follow-on
    event condition that cannot be decided does not fire. A plain false is not a failure."""
    undecided = not outcome.passed and outcome.value is not False
    if not undecided:
        return outcome, False
    if check_id.startswith(APPROVAL_PREFIXES):
        return Outcome(True, None, f"fail-safe: approval required ({outcome.reason})"), True
    if check_id.startswith(FOLLOW_ON_PREFIX):
        return Outcome(False, None, f"fail-safe: no follow-on ({outcome.reason})"), True
    return outcome, False


def _safe_json(value: Any) -> Any:
    try:
        return to_json(value)
    except (TypeError, ValueError):
        return str(value)
