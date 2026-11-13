"""014 T006 (US1/AC2, AC3; FR-003): presenter mode waits until the person has acted (no keyboard);
a step that misses its expectation stops with the reason and how to resume."""

from dataclasses import replace
from pathlib import Path

from adlc.demo.driver import DemoDriver
from tests.integration.demo.test_demo_auto import demo
from tests.support.orchestration import person
from tests.support.pg import PlatformDatabase


def test_presenter_mode_waits_for_the_person(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with demo(orch_template, tmp_path) as (h, driver, io):
        driver.script = replace(driver.script, steps=driver.script.steps[:1])  # submit and pass T0
        driver.auto = False
        acted: list[str] = []

        def presenter() -> None:  # what the presenter does in the web app, after the prompt
            prompt = io.said[-1]
            if "New use case" in prompt and not acted:
                h.service.submit_usecase(person("business_owner"), driver._name("main"), "x" * 250)
                acted.append("submit")
            elif "pass it" in prompt and "pass" not in acted:
                run_id = prompt.rsplit("(run ", 1)[1].rstrip(").")
                h.pass_run(run_id, {"risk_tier": "low"})
                acted.append("pass")

        io.pause = presenter  # type: ignore[method-assign]
        report = driver.run()
        assert report.ok, report.steps
        assert acted == ["submit", "pass"]
        assert any("As business_owner: open 'New use case'" in s for s in io.said)


def test_a_missed_expectation_stops_with_a_resume_hint(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with demo(orch_template, tmp_path) as (_, driver, io):
        first = driver.script.steps[0]
        wrong = replace(first, expect={"final_status": "rework"})
        driver.script = replace(driver.script, steps=(wrong, *driver.script.steps[1:3]))
        report = driver.run()
        assert not report.ok and len(report.steps) == 1
        assert (
            report.steps[0].outcome.startswith("failed: ")
            and "not rework" in report.steps[0].outcome
        )
        assert "resume with --from-step 1" in io.said[-1]


def test_resume_from_a_step_finds_the_use_case(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with demo(orch_template, tmp_path) as (_, driver, _io):
        steps = driver.script.steps
        driver.script = replace(driver.script, steps=steps[:2])
        assert driver.run().ok
        again = DemoDriver(
            replace(driver.script, steps=steps[:3]),
            driver.references,
            driver.replayer,
            driver.changes,
            driver.monitors,
            driver.io,
            auto=True,
            rounds=40,
        )
        report = again.run(from_step=3)
        assert [s.number for s in report.steps] == [3] and report.ok, report.steps
