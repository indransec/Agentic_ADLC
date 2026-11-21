"""018 SC-004: hostile values in titles, descriptions, comments, answers and other fields are
never rendered as markup on the board, the backlog or the form (T020)."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from ado_sim.comments import add_comment
from ado_sim.pages.sanitize import KEPT
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages.conftest import BOARD, ITEM, sign_in

BACKLOG = "/adlc-demo/Agentic%20ADLC/_backlogs/backlog"
PARENT = "System.LinkTypes.Hierarchy-Reverse"
HOSTILE = (
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(2)">',
    '<a href="javascript:alert(3)">x</a>',
    "<style>body{display:none}</style>",
    '"><svg onload=alert(4)>',
    "</textarea><script>alert(5)</script>",
    "<iframe src=//evil.test></iframe>",
    '<p style="background:url(javascript:alert(6))">s</p>',
)
EVIL = re.compile(
    r"<(script|img|svg|iframe|style)\b|\son[a-z]+=|javascript:alert|style=\"background", re.I
)


def _rendered_markup(page: str) -> list[str]:
    """Marks of markup from a value in the page's body (its own scripts are in <head>)."""
    body = page.split("<body", 1)[-1]
    # text "<" is always escaped, so everything between < and > is a tag the page emitted
    # and a quote inside a value is escaped, so a quoted value cannot end early: blank them out,
    # leaving the tag's own names and attributes
    tags = (re.sub(r'"[^"]*"', '""', tag) for tag in re.findall(r"<[^>]*>", body))
    return [tag for tag in tags if EVIL.search(tag)]


def test_hostile_values_are_never_markup(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    epic = store.create("Epic", [title("Use case")], people.service).id
    items = [epic]
    for n, value in enumerate(HOSTILE):
        kind = "Feature" if n % 2 else "Task"
        item = store.create(
            kind,
            [
                title(value[:120]),
                add("/fields/System.Description", value),
                add("/fields/Custom.AdlcClarificationAnswer", value),
                add("/fields/Custom.AdlcValues", value),
                add("/fields/Custom.AdlcSubStage", value[:120]),
                add("/relations/-", {"rel": PARENT, "url": f"http://h/_apis/wit/workItems/{epic}"}),
            ],
            people.service,
        ).id
        add_comment(store, item, value, people.service)
        items.append(item)
    store.update(epic, [add("/fields/Custom.AdlcSubStage", HOSTILE[1])], people.service)
    sign_in(client)
    pages = [BOARD, BOARD + "/cards", BACKLOG, BACKLOG + "/rows"] + [f"{ITEM}{i}" for i in items]
    for path in pages:
        page = client.get(path)
        assert page.status_code == 200, path
        assert _rendered_markup(page.text) == [], path
        for href in re.findall(r'\shref="([^"]*)"', page.text):
            assert href.startswith(("/", "#", "http://", "https://")), (path, href)
        # the only real tags are the page's own (vendored script tags in <head> aside)
        body = page.text.split("<body", 1)[-1]
        for tag in re.findall(r"<([a-z0-9]+)", body):
            assert tag in KEPT | {
                "header",
                "nav",
                "span",
                "strong",
                "form",
                "input",
                "button",
                "main",
                "h1",
                "h2",
                "h3",
                "section",
                "div",
                "details",
                "summary",
                "label",
                "select",
                "option",
                "textarea",
                "fieldset",
                "legend",
                "table",
                "thead",
                "tbody",
                "tr",
                "th",
                "td",
                "html",
                "dl",
                "dt",
                "dd",
                "article",
            }, (path, tag)
