"""The WIQL subset (contracts/wiql.md, research R-08).

A tokenizer and a recursive-descent parser for the documented subset, compiled to
parameterised SQL. Anything outside the subset is refused with a message naming it, never
answered with a partial result (FR-010, FR-011).

Dates follow ADO: without ``timePrecision=true`` a date literal may not carry a time and
comparisons use whole days; with it, comparisons use the stored precision (microseconds).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ado_sim.db import Database, format_time, utc_now
from ado_sim.errors import AdoError, invalid
from ado_sim.process import FieldDef, all_fields, area_paths, project_info

MAX_TOP = 20000
MAX_QUERY_BYTES = 32 * 1024
LINK_TYPE_FIELD = "System.Links.LinkType"
HIERARCHY_FORWARD = "System.LinkTypes.Hierarchy-Forward"
_COLUMNS = {
    "system.id": "id",
    "system.rev": "rev",
    "system.changeddate": "changed_date",
    "system.state": "state",
    "system.areapath": "area_path",
    "system.workitemtype": "type_name",
}
_TOKEN = re.compile(
    r"""(?P<space>\s+)
      | (?P<field>\[[^\]]*\])
      | (?P<string>'(?:[^']|'')*'|"(?:[^"]|"")*")
      | (?P<number>\d+(?:\.\d+)?)
      | (?P<macro>@[A-Za-z_][A-Za-z0-9_]*)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op><>|<=|>=|=|<|>|!=)
      | (?P<punct>[(),.+\-*])""",
    re.VERBOSE,
)
_UNSUPPORTED_WORDS = {
    "ASOF",
    "EVER",
    "CONTAINS",
    "WAS",
    "IS",
    "LIKE",
    "GROUP",
    "TOP",
    "DISTINCT",
    "JOIN",
}


def unsupported(construct: str) -> AdoError:
    return invalid(
        f"The WIQL construct '{construct}' is not supported by the ADO simulator; "
        "see its contract for the supported subset.",
        "WiqlUnsupportedException",
    )


def syntax(message: str) -> AdoError:
    return invalid(f"The WIQL query is not valid: {message}.", "WiqlSyntaxException")


# ------------------------------------------------------------------- tokens


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            snippet = text[position : position + 10]
            if snippet[:1] in "'\"":
                raise syntax(f"unterminated string at position {position}")
            raise syntax(f"unexpected character at position {position}: {snippet!r}")
        kind = match.lastgroup or ""
        raw = match.group()
        if kind != "space":
            value = raw
            if kind == "field":
                value = raw[1:-1].strip()
            elif kind == "string":
                quote = raw[0]
                value = raw[1:-1].replace(quote * 2, quote)
            tokens.append(Token(kind, value, position))
        position = match.end()
    return tokens


# --------------------------------------------------------------------- tree


@dataclass(frozen=True)
class FieldName:
    name: str
    prefix: str | None = None  # "source" or "target" in link queries


@dataclass(frozen=True)
class Value:
    kind: str  # string, number, macro
    value: Any
    offset: int = 0


@dataclass(frozen=True)
class Condition:
    field: FieldName
    op: str  # = <> < <= > >= in under
    values: tuple[Value, ...]
    negate: bool = False


@dataclass(frozen=True)
class Logical:
    op: str  # and, or, not
    parts: tuple[Any, ...]


@dataclass(frozen=True)
class Order:
    field: FieldName
    descending: bool


@dataclass
class Query:
    source: str
    columns: list[FieldName]
    where: Any = None
    order: list[Order] = field(default_factory=list)
    mode: str | None = None


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def peek(self, offset: int = 0) -> Token | None:
        position = self.index + offset
        return self.tokens[position] if position < len(self.tokens) else None

    def next(self) -> Token:
        token = self.peek()
        if token is None:
            raise syntax("unexpected end of query")
        self.index += 1
        return token

    def word(self, offset: int = 0) -> str | None:
        token = self.peek(offset)
        return token.value.upper() if token is not None and token.kind == "ident" else None

    def expect_word(self, *words: str) -> str:
        token = self.next()
        if token.kind != "ident" or token.value.upper() not in words:
            raise self.unexpected(token, " or ".join(words))
        return token.value.upper()

    def expect(self, kind: str, value: str | None = None) -> Token:
        token = self.next()
        if token.kind != kind or (value is not None and token.value != value):
            raise self.unexpected(token, value or kind)
        return token

    def unexpected(self, token: Token, wanted: str) -> AdoError:
        if token.kind == "ident" and token.value.upper() in _UNSUPPORTED_WORDS:
            return unsupported(token.value.upper())
        return syntax(f"expected {wanted} but found '{token.value}' at position {token.position}")

    def query(self) -> Query:
        self.expect_word("SELECT")
        columns = [self.field_name()]
        while self.peek() is not None and self.peek().value == ",":  # type: ignore[union-attr]
            self.next()
            columns.append(self.field_name())
        self.expect_word("FROM")
        source_token = self.next()
        source = source_token.value.lower()
        if source_token.kind != "ident" or source not in ("workitems", "workitemlinks"):
            raise unsupported(f"FROM {source_token.value}")
        query = Query(source, columns)
        while self.peek() is not None:
            word = self.word()
            if word == "WHERE" and query.where is None:
                self.next()
                query.where = self.expression()
            elif word == "ORDER" and not query.order:
                self.next()
                self.expect_word("BY")
                query.order = self.orders()
            elif word == "MODE" and query.mode is None:
                self.next()
                self.expect("punct", "(")
                query.mode = self.expect("ident").value
                self.expect("punct", ")")
            else:
                raise self.unexpected(self.next(), "WHERE, ORDER BY, MODE or the end")
        return query

    def field_name(self) -> FieldName:
        token = self.next()
        if token.kind == "punct" and token.value == "*":
            raise unsupported("SELECT *")
        if token.kind != "field":
            raise self.unexpected(token, "a field in brackets")
        nxt = self.peek()
        if token.value.lower() in ("source", "target") and nxt is not None and nxt.value == ".":
            self.next()
            inner = self.expect("field")
            return FieldName(inner.value, token.value.lower())
        return FieldName(token.value)

    def orders(self) -> list[Order]:
        orders = [self.order()]
        while self.peek() is not None and self.peek().value == ",":  # type: ignore[union-attr]
            self.next()
            orders.append(self.order())
        return orders

    def order(self) -> Order:
        name = self.field_name()
        descending = False
        if self.word() in ("ASC", "DESC"):
            descending = self.next().value.upper() == "DESC"
        return Order(name, descending)

    def expression(self) -> Any:
        parts = [self.conjunction()]
        while self.word() == "OR":
            self.next()
            parts.append(self.conjunction())
        return parts[0] if len(parts) == 1 else Logical("or", tuple(parts))

    def conjunction(self) -> Any:
        parts = [self.negation()]
        while self.word() == "AND":
            self.next()
            parts.append(self.negation())
        return parts[0] if len(parts) == 1 else Logical("and", tuple(parts))

    def negation(self) -> Any:
        if self.word() == "NOT":
            self.next()
            return Logical("not", (self.negation(),))
        token = self.peek()
        if token is not None and token.value == "(" and token.kind == "punct":
            self.next()
            inner = self.expression()
            self.expect("punct", ")")
            return inner
        return self.condition()

    def condition(self) -> Condition:
        name = self.field_name()
        negate = False
        if self.word() == "NOT":
            self.next()
            negate = True
        token = self.next()
        if token.kind == "op":
            if token.value == "!=":
                raise unsupported("!=")
            if negate:
                raise self.unexpected(token, "IN or UNDER after NOT")
            return Condition(name, token.value, (self.value(),))
        word = token.value.upper() if token.kind == "ident" else None
        if word == "IN":
            if self.word() == "GROUP":
                raise unsupported("IN GROUP")
            self.expect("punct", "(")
            values = [self.value()]
            while self.peek() is not None and self.peek().value == ",":  # type: ignore[union-attr]
                self.next()
                values.append(self.value())
            self.expect("punct", ")")
            return Condition(name, "in", tuple(values), negate)
        if word == "UNDER":
            return Condition(name, "under", (self.value(),), negate)
        if word == "CONTAINS" and self.word() == "WORDS":
            raise unsupported("CONTAINS WORDS")
        if word == "IS" and self.word() == "EMPTY":
            raise unsupported("IS EMPTY")
        if word == "WAS" and self.word() == "EVER":
            raise unsupported("WAS EVER")
        raise self.unexpected(token, "a comparison operator, IN or UNDER")

    def value(self) -> Value:
        token = self.next()
        if token.kind == "string":
            return Value("string", token.value)
        if token.kind == "number":
            number = float(token.value) if "." in token.value else int(token.value)
            return Value("number", number)
        if token.kind == "punct" and token.value == "-" and self.peek() is not None:
            number_token = self.expect("number")
            return Value(
                "number",
                -(
                    float(number_token.value)
                    if "." in number_token.value
                    else int(number_token.value)
                ),
            )
        if token.kind == "macro":
            name = token.value.lower()
            if name not in ("@project", "@today"):
                raise unsupported(token.value)
            offset = 0
            sign = self.peek()
            if name == "@today" and sign is not None and sign.value in ("+", "-"):
                self.next()
                amount = int(self.expect("number").value)
                offset = amount if sign.value == "+" else -amount
            return Value("macro", name, offset)
        if token.kind == "field":
            raise unsupported("field comparison [" + token.value + "]")
        raise self.unexpected(token, "a value")


def parse(text: str) -> Query:
    if len(text.encode("utf-8")) > MAX_QUERY_BYTES:
        raise invalid("A WIQL query may be at most 32 KB long.")
    return _Parser(tokenize(text)).query()


# ---------------------------------------------------------------- compiling


@dataclass
class WiqlResult:
    query_type: str
    columns: list[FieldDef]
    sort_columns: list[tuple[FieldDef, bool]]
    work_items: list[int]
    relations: list[tuple[str | None, int | None, int]]
    as_of: str


@dataclass
class _Context:
    fields: dict[str, FieldDef]
    by_name: dict[str, FieldDef]
    areas: dict[str, str]
    project: str
    today: date
    time_precision: bool
    link_query: bool
    link_type_seen: bool = False
    params: list[Any] = field(default_factory=list)

    def resolve(self, name: FieldName) -> FieldDef:
        if name.prefix and not self.link_query:
            raise unsupported(f"[{name.prefix.title()}] outside a workitemLinks query")
        key = name.name.lower()
        definition = self.fields.get(key) or self.by_name.get(key)
        if definition is None:
            raise invalid(
                f"TF51005: The query references a field that does not exist: {name.name}."
            )
        return definition

    def alias(self, name: FieldName) -> str:
        if not self.link_query:
            return "w"
        return "t" if name.prefix == "target" else "s"


_SAFE_REFERENCE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*$")


def _column(definition: FieldDef, alias: str, context: _Context, part: str = "") -> str:
    """The SQL expression of a field; reference names are validated when the seed loads."""
    key = definition.reference_name.lower()
    if key in _COLUMNS and not part:
        return f"{alias}.{_COLUMNS[key]}"
    if not _SAFE_REFERENCE.match(definition.reference_name) or part not in (
        "",
        ".uniqueName",
        ".displayName",
    ):
        raise invalid(f"The field {definition.reference_name} cannot be queried.")
    return f"json_extract({alias}.fields, '$.\"{definition.reference_name}\"{part}')"


def _midnight(day: date) -> str:
    return format_time(datetime(day.year, day.month, day.day, tzinfo=UTC))


def _literal(definition: FieldDef, value: Value, context: _Context) -> Any:
    """A query value converted to the stored form of the field; dates return (start, end)."""
    if value.kind == "macro":
        if value.value == "@project":
            return context.project
        day = context.today + timedelta(days=value.offset)
        if definition.type != "dateTime":
            raise invalid(
                f"@today can only be compared with a date field, not {definition.reference_name}."
            )
        return (_midnight(day), _midnight(day + timedelta(days=1)))
    raw = value.value
    kind = definition.type
    if kind == "dateTime":
        text = str(raw)
        has_time = "T" in text or ":" in text
        if has_time and not context.time_precision:
            raise invalid(
                "You cannot supply a time with the date when running a query using date "
                "precision; pass timePrecision=true to compare times."
            )
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as error:
            raise invalid(f"'{text}' is not a date for {definition.reference_name}.") from error
        if has_time:
            exact = format_time(moment if moment.tzinfo else moment.replace(tzinfo=UTC))
            return (exact, None)
        day = moment.date()
        if context.time_precision:
            return (_midnight(day), None)
        return (_midnight(day), _midnight(day + timedelta(days=1)))
    if kind == "integer":
        if isinstance(raw, int) or (isinstance(raw, str) and raw.lstrip("-").isdigit()):
            return int(raw)
        raise invalid(f"The value '{raw}' is not an integer for {definition.reference_name}.")
    if kind == "double":
        try:
            return float(raw)
        except ValueError as error:
            raise invalid(
                f"The value '{raw}' is not a number for {definition.reference_name}."
            ) from error
    if kind == "boolean":
        text = str(raw).lower()
        if text not in ("true", "false"):
            raise invalid(
                f"The value '{raw}' is not true or false for {definition.reference_name}."
            )
        return 1 if text == "true" else 0
    return str(raw)


def _date_condition(column: str, op: str, bounds: tuple[str, str | None], context: _Context) -> str:
    start, end = bounds
    if end is None:  # exact moment
        context.params.append(start)
        return f"{column} {op} ?" if op != "<>" else f"({column} IS NULL OR {column} <> ?)"
    if op == "=":
        context.params.extend([start, end])
        return f"({column} >= ? AND {column} < ?)"
    if op == "<>":
        context.params.extend([start, end])
        return f"({column} IS NULL OR {column} < ? OR {column} >= ?)"
    context.params.append({"<": start, "<=": end, ">": end, ">=": start}[op])
    return f"{column} {'<' if op in ('<', '<=') else '>='} ?"


def _compile(node: Any, context: _Context) -> str:
    if isinstance(node, Logical):
        if node.op == "not":
            return f"NOT COALESCE({_compile(node.parts[0], context)}, 0)"
        joiner = " AND " if node.op == "and" else " OR "
        return "(" + joiner.join(_compile(part, context) for part in node.parts) + ")"
    assert isinstance(node, Condition)  # noqa: S101
    if node.field.name.lower() == LINK_TYPE_FIELD.lower():
        return _link_type(node, context)
    definition = context.resolve(node.field)
    alias = context.alias(node.field)
    if node.op == "under":
        return _under(definition, alias, node, context)
    if definition.type == "identity":
        return _identity(definition, alias, node, context)
    if node.op == "in":
        terms = [_equals(definition, alias, value, context) for value in node.values]
        joined = "(" + " OR ".join(terms) + ")"
        return f"NOT COALESCE({joined}, 0)" if node.negate else joined
    if definition.type == "dateTime":
        bounds = _literal(definition, node.values[0], context)
        return _date_condition(_column(definition, alias, context), node.op, bounds, context)
    column = _column(definition, alias, context)
    literal = _literal(definition, node.values[0], context)
    context.params.append(literal)
    collate = " COLLATE NOCASE" if isinstance(literal, str) else ""
    if node.op == "<>":
        return f"({column} IS NOT ?{collate})"
    return f"{column} {node.op} ?{collate}"


def _equals(definition: FieldDef, alias: str, value: Value, context: _Context) -> str:
    if definition.type == "dateTime":
        bounds = _literal(definition, value, context)
        return _date_condition(_column(definition, alias, context), "=", bounds, context)
    column = _column(definition, alias, context)
    literal = _literal(definition, value, context)
    context.params.append(literal)
    return f"{column} = ?" + (" COLLATE NOCASE" if isinstance(literal, str) else "")


def _under(definition: FieldDef, alias: str, node: Condition, context: _Context) -> str:
    if definition.type != "treePath":
        raise unsupported(f"UNDER on {definition.reference_name}")
    path = str(node.values[0].value)
    if path.lower() not in context.areas:
        raise invalid(f"TF51011: The specified area path does not exist: {path}.")
    column = _column(definition, alias, context)
    lowered = path.lower()
    context.params.extend([lowered, len(lowered) + 1, lowered + "\\"])
    clause = f"(lower({column}) = ? OR substr(lower({column}), 1, ?) = ?)"
    return f"NOT {clause}" if node.negate else clause


def _identity(definition: FieldDef, alias: str, node: Condition, context: _Context) -> str:
    if node.op not in ("=", "<>", "in"):
        raise unsupported(f"{node.op} on the identity field {definition.reference_name}")
    terms = []
    for value in node.values:
        text = str(value.value).strip()
        if text.endswith(">") and "<" in text:
            unique = text[text.rindex("<") + 1 : -1].strip()
            terms.append(f"{_column(definition, alias, context, '.uniqueName')} = ? COLLATE NOCASE")
            context.params.append(unique)
        else:
            unique_column = _column(definition, alias, context, ".uniqueName")
            display_column = _column(definition, alias, context, ".displayName")
            context.params.extend([text, text])
            terms.append(
                f"({unique_column} = ? COLLATE NOCASE OR {display_column} = ? COLLATE NOCASE)"
            )
    clause = "(" + " OR ".join(terms) + ")"
    return f"NOT COALESCE({clause}, 0)" if node.op == "<>" or node.negate else clause


def _link_type(node: Condition, context: _Context) -> str:
    if not context.link_query:
        raise unsupported(f"[{LINK_TYPE_FIELD}] outside a workitemLinks query")
    if node.op not in ("=", "in") or node.negate:
        raise unsupported(f"{node.op} on [{LINK_TYPE_FIELD}]")
    for value in node.values:
        if str(value.value).lower() != HIERARCHY_FORWARD.lower():
            raise unsupported(f"link type {value.value}")
    context.link_type_seen = True
    context.params.append(HIERARCHY_FORWARD)
    return "r.rel = ?"


def _order_term(order: Order, context: _Context) -> tuple[str, FieldDef]:
    definition = context.resolve(order.field)
    alias = context.alias(order.field)
    if definition.type == "identity":
        column = _column(definition, alias, context, ".displayName")
    else:
        column = _column(definition, alias, context)
    return f"{column} {'DESC' if order.descending else 'ASC'}", definition


def run_query(
    db: Database,
    text: str,
    *,
    top: int | None = None,
    time_precision: bool = False,
    today: date | None = None,
) -> WiqlResult:
    if not isinstance(text, str) or not text.strip():
        raise invalid('The request body must hold a WIQL query: {"query": "SELECT ..."}.')
    if top is not None and not 1 <= top <= MAX_TOP:
        raise invalid(f"$top must be between 1 and {MAX_TOP}.")
    query = parse(text)
    with db.read() as conn:
        return _execute(conn, query, top, time_precision, today)


def _execute(
    conn: sqlite3.Connection,
    query: Query,
    top: int | None,
    time_precision: bool,
    today: date | None,
) -> WiqlResult:
    fields = all_fields(conn)
    project = project_info(conn)
    link_query = query.source == "workitemlinks"
    if not link_query and query.mode is not None:
        raise unsupported(f"MODE ({query.mode}) in a workitems query")
    if link_query and query.mode is not None and query.mode.lower() != "mustcontain":
        raise unsupported(f"MODE ({query.mode})")
    context = _Context(
        fields=fields,
        by_name={f.name.lower(): f for f in fields.values()},
        areas=area_paths(conn),
        project=project.project if project else "",
        today=today or datetime.now(UTC).date(),
        time_precision=time_precision,
        link_query=link_query,
    )
    columns = [context.resolve(c) for c in query.columns]
    where = _compile(query.where, context) if query.where is not None else "1 = 1"
    if link_query and not context.link_type_seen:
        raise unsupported(
            f"a workitemLinks query without [{LINK_TYPE_FIELD}] = '{HIERARCHY_FORWARD}'"
        )
    order_terms = [_order_term(order, context) for order in query.order]
    sort_columns = [
        (definition, order.descending)
        for (_, definition), order in zip(order_terms, query.order, strict=True)
    ]
    order_sql = ", ".join(term for term, _ in order_terms)
    limit = top if top is not None else MAX_TOP + 1
    if not link_query:
        sql = (
            f"SELECT w.id FROM work_item w WHERE {where}"  # noqa: S608 - parameterised
            f" ORDER BY {order_sql + ', ' if order_sql else ''}w.id LIMIT ?"
        )
        ids = [int(row[0]) for row in conn.execute(sql, [*context.params, limit])]
        if top is None and len(ids) > MAX_TOP:
            raise invalid(
                f"VS402337: The number of work items returned exceeds the size limit of {MAX_TOP}."
            )
        return WiqlResult("flat", columns, sort_columns, ids, [], utc_now())
    sql = (
        "SELECT s.id AS source, t.id AS target, r.rel AS rel FROM work_item s"  # noqa: S608
        " JOIN relation r ON r.source_id = s.id JOIN work_item t ON t.id = r.target_id"
        f" WHERE {where} ORDER BY {order_sql + ', ' if order_sql else ''}s.id, t.id LIMIT ?"
    )
    rows = conn.execute(sql, [*context.params, limit]).fetchall()
    if top is None and len(rows) > MAX_TOP:
        raise invalid(
            f"VS402337: The number of work item links returned exceeds the size limit of {MAX_TOP}."
        )
    grouped: dict[int, list[tuple[str, int]]] = {}
    for row in rows:
        grouped.setdefault(int(row["source"]), []).append((row["rel"], int(row["target"])))
    relations: list[tuple[str | None, int | None, int]] = []
    for source, links in grouped.items():
        relations.append((None, None, source))
        relations.extend((rel, source, target) for rel, target in links)
    return WiqlResult("oneHop", columns, sort_columns, [], relations, utc_now())
