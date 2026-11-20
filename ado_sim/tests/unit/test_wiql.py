"""WIQL subset: tokenizer, parser and compiler (T026, written before ado_sim.wiql)."""

from datetime import date

import pytest

from ado_sim.db import Database
from ado_sim.errors import AdoError
from ado_sim.wiql import MAX_QUERY_BYTES, MAX_TOP, parse, run_query, tokenize
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title

LINK = "System.LinkTypes.Hierarchy-Reverse"


def ids(store: WorkItemStore, text: str, **kwargs: object) -> list[int]:
    return run_query(store.db, text, **kwargs).work_items  # type: ignore[arg-type]


def refusal(store: WorkItemStore, text: str, **kwargs: object) -> str:
    with pytest.raises(AdoError) as raised:
        run_query(store.db, text, **kwargs)  # type: ignore[arg-type]
    assert raised.value.status == 400
    return raised.value.message


def parent(target: int) -> dict[str, object]:
    return {
        "op": "add",
        "path": "/relations/-",
        "value": {"rel": LINK, "url": f"http://h/_apis/wit/workItems/{target}"},
    }


@pytest.fixture
def board(store: WorkItemStore, people: People) -> dict[str, int]:
    def make(kind: str, name: str, *extra: dict[str, object]) -> int:
        return store.create(kind, [title(name), *extra], people.service).id

    epic_a = make("Epic", "Epic A", add("/fields/System.AreaPath", "Agentic ADLC\\Use cases"))
    epic_b = make("Epic", "Epic B", add("/fields/System.State", "T1 Requirements & Outcome"))
    task_1 = make("Task", "Task 1", parent(epic_a), add("/fields/Custom.AdlcRunId", "run-1"))
    task_2 = make("Task", "Task's 2", parent(epic_a), add("/fields/System.State", "Active"))
    bug = make("Bug", "Bug", add("/fields/System.AssignedTo", "product.owner@adlc.demo"))
    return {"epic_a": epic_a, "epic_b": epic_b, "task_1": task_1, "task_2": task_2, "bug": bug}


def test_tokenizer() -> None:
    kinds = [
        t.kind for t in tokenize("SELECT [System.Id] FROM x WHERE [a] <> 'it''s' AND @today - 1")
    ]
    assert kinds == [
        "ident",
        "field",
        "ident",
        "ident",
        "ident",
        "field",
        "op",
        "string",
        "ident",
        "macro",
        "punct",
        "number",
    ]
    assert tokenize("'it''s'")[0].value == "it's"
    assert tokenize('"double"')[0].value == "double"
    with pytest.raises(AdoError):
        tokenize("SELECT ~")
    with pytest.raises(AdoError):
        tokenize("'unterminated")


def test_parser_shapes() -> None:
    query = parse(
        "select [System.Id], [System.Title] from WorkItems where ([a] = 1 or not [b] in (1, 2))"
        " and [c] under 'x' order by [System.ChangedDate] desc, [System.Id]"
    )
    assert query.source == "workitems"
    assert [c.name for c in query.columns] == ["System.Id", "System.Title"]
    assert [(o.field.name, o.descending) for o in query.order] == [
        ("System.ChangedDate", True),
        ("System.Id", False),
    ]


def test_flat_filters(store: WorkItemStore, board: dict[str, int]) -> None:
    q = "SELECT [System.Id] FROM workitems WHERE "
    assert ids(store, q + "[System.WorkItemType] = 'Epic' ORDER BY [System.Id]") == [
        board["epic_a"],
        board["epic_b"],
    ]
    assert ids(
        store,
        q + "[System.WorkItemType] = 'epic' AND [System.State] = 'T0 Intake & Qualification'"
        " AND [System.AreaPath] UNDER 'Agentic ADLC\\Use cases'",
    ) == [board["epic_a"]]
    assert ids(
        store,
        q + "[System.AreaPath] UNDER 'Agentic ADLC' AND [System.WorkItemType] IN ('Task', 'Bug')"
        " ORDER BY [System.Id] DESC",
    ) == [board["bug"], board["task_2"], board["task_1"]]
    assert ids(store, q + "[System.State] <> 'New' AND [System.WorkItemType] = 'Task'") == [
        board["task_2"]
    ]
    assert ids(store, q + "[Custom.AdlcRunId] <> 'run-1' AND [System.WorkItemType] = 'Task'") == [
        board["task_2"]
    ]
    assert ids(store, q + "[State] = 'Active'") == [board["task_2"]]
    assert ids(store, q + "[System.Title] = 'Task''s 2'") == [board["task_2"]]
    assert ids(
        store, q + "NOT ([System.WorkItemType] = 'Task' OR [System.WorkItemType] = 'Epic')"
    ) == [board["bug"]]
    assert ids(store, q + "[System.WorkItemType] NOT IN ('Task', 'Epic')") == [board["bug"]]
    assert ids(
        store, q + f"[System.Id] IN ({board['task_1']}, {board['bug']}) ORDER BY [System.Id]"
    ) == [board["task_1"], board["bug"]]
    assert ids(store, q + "[System.Id] > 3 ORDER BY [System.Id]") == [4, 5]
    assert ids(store, q + "[System.TeamProject] = @project AND [System.Id] <= 1") == [1]
    assert ids(store, q + "[System.AssignedTo] = 'Product Owner <product.owner@adlc.demo>'") == [
        board["bug"]
    ]
    assert ids(store, q + "[System.AssignedTo] = 'product owner'") == [board["bug"]]
    assert ids(
        store,
        q
        + "[System.AreaPath] NOT UNDER 'Agentic ADLC\\Use cases'"
        + " AND [System.WorkItemType] = 'Epic'",
    ) == [board["epic_b"]]


def test_order_and_top(store: WorkItemStore, board: dict[str, int]) -> None:
    query = "SELECT [System.Id] FROM workitems ORDER BY [System.ChangedDate] DESC"
    result = ids(store, query, top=2)
    assert result == [board["bug"], board["task_2"]]
    assert len(ids(store, query)) == 5
    assert "$top" in refusal(store, query, top=MAX_TOP + 1)
    assert "$top" in refusal(store, query, top=0)


def test_changed_since_with_time_precision(
    store: WorkItemStore, people: People, board: dict[str, int]
) -> None:
    latest = store.get(board["task_2"]).fields["System.ChangedDate"]
    store.update(board["epic_b"], [add("/fields/System.Title", "changed")], people.owner)
    query = (
        "SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '" + latest + "'"
        " ORDER BY [System.ChangedDate] ASC, [System.Id] ASC"
    )
    assert ids(store, query, time_precision=True) == [
        board["task_2"],
        board["bug"],
        board["epic_b"],
    ]
    message = refusal(store, query)
    assert "timePrecision" in message


def test_date_precision_compares_whole_days(store: WorkItemStore, board: dict[str, int]) -> None:
    today = date.fromisoformat(store.get(1).fields["System.ChangedDate"][:10])
    q = "SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] "
    assert len(ids(store, q + f"= '{today.isoformat()}'")) == 5
    assert ids(store, q + f"> '{today.isoformat()}'") == []
    assert len(ids(store, q + ">= @today", today=today)) == 5
    assert len(ids(store, q + ">= @today - 1", today=today)) == 5
    assert ids(store, q + "< @today", today=today) == []
    assert len(ids(store, q + "<= @today", today=today)) == 5
    assert ids(store, q + "<> @today", today=today) == []
    assert ids(store, q + "> @today + 1", today=today) == []


def test_link_query(store: WorkItemStore, board: dict[str, int]) -> None:
    result = run_query(
        store.db,
        "SELECT [System.Id] FROM workitemLinks WHERE ([Source].[System.WorkItemType] = 'Epic')"
        " AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'"
        " AND [Target].[System.WorkItemType] = 'Task' ORDER BY [System.Id] MODE (MustContain)",
    )
    assert result.query_type == "oneHop"
    assert result.relations == [
        (None, None, board["epic_a"]),
        ("System.LinkTypes.Hierarchy-Forward", board["epic_a"], board["task_1"]),
        ("System.LinkTypes.Hierarchy-Forward", board["epic_a"], board["task_2"]),
    ]
    by_id = run_query(
        store.db,
        f"SELECT [System.Id] FROM workitemLinks WHERE [Source].[System.Id] = {board['epic_a']}"
        " AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'"
        " AND [Target].[System.State] = 'Active'",
    )
    assert by_id.relations == [
        (None, None, board["epic_a"]),
        ("System.LinkTypes.Hierarchy-Forward", board["epic_a"], board["task_2"]),
    ]


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("SELECT [System.Id] FROM workitems WHERE [System.State] EVER 'Active'", "EVER"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Title] CONTAINS 'x'", "CONTAINS"),
        (
            "SELECT [System.Id] FROM workitems WHERE [System.Title] CONTAINS WORDS 'x'",
            "CONTAINS WORDS",
        ),
        ("SELECT [System.Id] FROM workitems WHERE [System.Title] IS EMPTY", "IS EMPTY"),
        ("SELECT [System.Id] FROM workitems WHERE [System.State] WAS EVER 'Active'", "WAS EVER"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Id] > 1 ASOF '2026-01-01'", "ASOF"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Title] = [System.State]", "field"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Missing] = 'x'", "System.Missing"),
        ("SELECT [System.Id] FROM workitems WHERE [System.AssignedTo] IN GROUP 'x'", "IN GROUP"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Id] = @me", "@me"),
        ("SELECT [System.Id] FROM workitems WHERE [System.AreaPath] UNDER 'Nowhere'", "area path"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Title] UNDER 'x'", "UNDER"),
        ("SELECT [System.Id] FROM workitems MODE (MustContain)", "MODE"),
        ("SELECT * FROM workitems", "*"),
        ("SELECT [System.Id] FROM queries", "queries"),
        ("SELECT [System.Id] FROM workitems WHERE [Source].[System.Id] = 1", "Source"),
        (
            "SELECT [System.Id] FROM workitemLinks WHERE [System.Links.LinkType] ="
            " 'System.LinkTypes.Dependency-Forward'",
            "System.LinkTypes.Dependency-Forward",
        ),
        ("SELECT [System.Id] FROM workitemLinks WHERE [Source].[System.Id] = 1", "LinkType"),
        (
            "SELECT [System.Id] FROM workitemLinks WHERE [System.Links.LinkType] ="
            " 'System.LinkTypes.Hierarchy-Forward' MODE (Recursive)",
            "MODE (Recursive)",
        ),
        (
            "SELECT [System.Id] FROM workitemLinks WHERE [System.Links.LinkType] ="
            " 'System.LinkTypes.Hierarchy-Forward' MODE (MayContain)",
            "MODE (MayContain)",
        ),
        ("SELECT [System.Id] FROM workitems WHERE", "end"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Id] = 1 extra", "extra"),
        ("SELECT [System.Id] FROM workitems WHERE [System.Id] = 'x'", "System.Id"),
    ],
)
def test_refusals_name_the_construct(
    store: WorkItemStore, board: dict[str, int], text: str, named: str
) -> None:
    assert named.lower() in refusal(store, text).lower()


def test_query_size_limit(store: WorkItemStore) -> None:
    text = (
        "SELECT [System.Id] FROM workitems WHERE [System.Title] = '" + "x" * MAX_QUERY_BYTES + "'"
    )
    assert "32 KB" in refusal(store, text)


def test_as_of_is_the_latest_change_the_query_saw(
    store: WorkItemStore, people: People, board: dict[str, int]
) -> None:
    store.update(board["task_1"], [add("/fields/System.Title", "latest")], people.owner)
    latest = store.get(board["task_1"]).fields["System.ChangedDate"]
    result = run_query(store.db, "SELECT [System.Id] FROM workitems WHERE [System.Id] = 1")
    assert result.as_of == latest


def test_changed_dates_increase_across_items_even_when_the_clock_stands_still(
    db: Database, people: People
) -> None:
    frozen = WorkItemStore(db, clock=lambda: "2026-11-20T10:00:00.000000Z")
    first = frozen.create("Task", [title("a")], people.service)
    second = frozen.create("Task", [title("b")], people.service)
    changed = frozen.update(first.id, [title("a2")], people.owner)
    dates = [
        first.fields["System.ChangedDate"],
        second.fields["System.ChangedDate"],
        changed.fields["System.ChangedDate"],
    ]
    assert dates == sorted(dates) and len(set(dates)) == 3
    assert dates[-1] == "2026-11-20T10:00:00.000002Z"
