"""Parse CEL expressions and extract what they reference (research R-01, R-02).

Parsing only: evaluation belongs to the policy engine (feature 004). The result lists
member-access chains (``Tn.status`` → ``("Tn", "status")``), function calls with argument
kinds, and method names. Variables bound by CEL macros (``list.exists(x, ...)``) are local and
not reported as references.
"""

from dataclasses import dataclass
from functools import cache

from celpy import celparser
from lark import Token, Tree

CEL_MACROS = frozenset({"all", "exists", "exists_one", "map", "filter"})


class ExpressionError(ValueError):
    def __init__(self, message: str, column: int | None = None) -> None:
        super().__init__(message)
        self.column = column


@dataclass(frozen=True)
class Ref:
    path: tuple[str, ...]

    @property
    def root(self) -> str:
        return self.path[0]

    def dotted(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class Arg:
    kind: str  # ref | list | string | number | other
    ref: Ref | None = None
    items: tuple[str, ...] = ()
    text: str = ""


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[Arg, ...]


@dataclass(frozen=True)
class ParsedExpression:
    refs: tuple[Ref, ...]
    calls: tuple[Call, ...]
    methods: tuple[str, ...]


@cache
def _parser() -> celparser.CELParser:
    return celparser.CELParser()


def _children(node: object) -> list[object]:
    return list(node.children) if isinstance(node, Tree) else []


def _chain(node: Tree) -> tuple[str, ...] | None:  # type: ignore[type-arg]
    """Flatten member_dot(member_dot(primary(ident X), a), b) → (X, a, b)."""
    if node.data == "member":
        kids = _children(node)
        return _chain(kids[0]) if len(kids) == 1 and isinstance(kids[0], Tree) else None
    if node.data == "primary":
        kids = _children(node)
        if len(kids) == 1 and isinstance(kids[0], Tree) and kids[0].data == "ident":
            return (str(kids[0].children[0]),)
        return None
    if node.data == "member_dot":
        inner, name = node.children[0], node.children[1]
        base = _chain(inner) if isinstance(inner, Tree) else None
        return None if base is None else (*base, str(name))
    return None


def _unwrap(node: object) -> object:
    """Descend through single-child wrapper nodes to the meaningful node."""
    while isinstance(node, Tree) and node.data in (
        "expr",
        "conditionalor",
        "conditionaland",
        "relation",
        "addition",
        "multiplication",
        "unary",
        "member",
        "primary",
    ):
        kids = _children(node)
        if len(kids) != 1:
            break
        node = kids[0]
    return node


def _literal(token: Token) -> Arg:
    text = str(token)
    if text[:1] in ('"', "'"):
        return Arg(kind="string", text=text[1:-1])
    if text in ("true", "false", "null"):
        return Arg(kind="other", text=text)
    return Arg(kind="number", text=text)


def _arg(expr: object) -> Arg:
    chain = None
    node = expr
    while (
        isinstance(node, Tree)
        and node.data
        in (
            "expr",
            "conditionalor",
            "conditionaland",
            "relation",
            "addition",
            "multiplication",
            "unary",
        )
        and len(node.children) == 1
    ):
        node = node.children[0]
    if isinstance(node, Tree) and node.data == "member":
        chain = _chain(node)
    if chain is not None:
        return Arg(kind="ref", ref=Ref(chain))
    inner = _unwrap(expr)
    if isinstance(inner, Tree) and inner.data == "literal":
        return _literal(inner.children[0])  # type: ignore[arg-type]
    if isinstance(inner, Tree) and inner.data == "list_lit":
        items: list[str] = []
        for item in _children(inner.children[0]) if inner.children else []:
            lit = _unwrap(item)
            if isinstance(lit, Tree) and lit.data == "literal":
                items.append(_literal(lit.children[0]).text)  # type: ignore[arg-type]
        return Arg(kind="list", items=tuple(items))
    return Arg(kind="other")


class _Collector:
    def __init__(self) -> None:
        self.refs: list[Ref] = []
        self.calls: list[Call] = []
        self.methods: list[str] = []
        self.bound: set[str] = set()

    def visit(self, node: object) -> None:
        if not isinstance(node, Tree):
            return
        if node.data == "member_dot":
            chain = _chain(node)
            if chain is not None:
                self.refs.append(Ref(chain))
                return
        if node.data == "primary":
            kids = _children(node)
            if len(kids) == 1 and isinstance(kids[0], Tree) and kids[0].data == "ident":
                self.refs.append(Ref((str(kids[0].children[0]),)))
                return
        if node.data == "ident_arg":
            name = str(node.children[0])
            exprs = _children(node.children[1]) if len(node.children) > 1 else []
            self.calls.append(Call(name, tuple(_arg(e) for e in exprs)))
            for e in exprs:
                self.visit(e)
            return
        if node.data == "member_dot_arg":
            target, method = node.children[0], str(node.children[1])
            exprs = _children(node.children[2]) if len(node.children) > 2 else []
            self.methods.append(method)
            if method in CEL_MACROS and exprs:
                first = _arg(exprs[0])
                if first.ref is not None and len(first.ref.path) == 1:
                    self.bound.add(first.ref.root)
                exprs = exprs[1:]
            self.visit(target)
            for e in exprs:
                self.visit(e)
            return
        for child in node.children:
            self.visit(child)


def parse_expression(text: str) -> ParsedExpression:
    if not text.strip():
        raise ExpressionError("empty expression", 1)
    try:
        tree = _parser().parse(text)
    except Exception as exc:  # celpy raises CELParseError; keep the column when present
        column = getattr(exc, "column", None)
        message = str(exc).splitlines()[0] if str(exc) else "cannot parse expression"
        raise ExpressionError(message, column if isinstance(column, int) else None) from None
    collector = _Collector()
    collector.visit(tree)
    refs = tuple(r for r in collector.refs if r.root not in collector.bound)
    return ParsedExpression(
        refs=refs, calls=tuple(collector.calls), methods=tuple(collector.methods)
    )
