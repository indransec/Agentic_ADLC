"""018 T004: the allow-list sanitiser for HTML fields (FR-005, FR-006, SC-004; research R-05)."""

from __future__ import annotations

import random
import re

import pytest

from ado_sim.pages.sanitize import KEPT, clean, web_address


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("<p>One</p><p>Two</p>", "<p>One</p><p>Two</p>"),
        (
            "<ul><li>a</li><li><strong>b</strong></li></ul>",
            "<ul><li>a</li><li><strong>b</strong></li></ul>",
        ),
        ("line<br>next", "line<br>next"),
        (
            "<em>i</em><b>b</b><i>i</i><ol><li>x</li></ol>",
            "<em>i</em><b>b</b><i>i</i><ol><li>x</li></ol>",
        ),
        ('<p class="x" style="color:red" onclick="go()">t</p>', "<p>t</p>"),
        ("<div><span>kept text</span></div>", "kept text"),
        ("a < b & c > d", "a &lt; b &amp; c &gt; d"),
        ("<p>unclosed", "<p>unclosed</p>"),
    ],
)
def test_allowed_tags_and_text(given: str, expected: str) -> None:
    assert clean(given) == expected


@pytest.mark.parametrize("tag", ["script", "style", "iframe", "object", "template"])
def test_dangerous_elements_go_with_their_content(tag: str) -> None:
    assert clean(f"<p>a</p><{tag}>alert(1)</{tag}><p>b</p>") == "<p>a</p><p>b</p>"


def test_links() -> None:
    assert clean('<a href="https://ui.test/run?id=1">run</a>') == (
        '<a href="https://ui.test/run?id=1" target="_blank" rel="noopener noreferrer">run</a>'
    )
    for href in (
        "javascript:alert(1)",
        "data:text/html,x",
        "/relative",
        "JaVaScRiPt:x",
        " javascript:x",
    ):
        assert clean(f'<a href="{href}">text</a>') == "text"


def test_web_addresses() -> None:
    assert web_address(" https://ui.test/runs/1 ") == "https://ui.test/runs/1"
    for value in ("javascript:alert(1)", "see https://x.test", "ftp://x.test", "http://a b"):
        assert web_address(value) is None


def test_a_value_with_quotes_in_the_link_is_escaped() -> None:
    assert clean('<a href="https://x.test/?a=&quot;b">t</a>').startswith(
        '<a href="https://x.test/?a=&quot;b"'
    )


PIECES = (
    "<script>",
    "</script>",
    "<img src=x onerror=alert(1)>",
    "<a href='javascript:x'>",
    "<p>",
    "</p>",
    "<style>",
    "<svg onload=1>",
    '" onmouseover="x',
    "<iframe>",
    "text",
    "&lt;",
    "<",
    ">",
    '<a href="https://ok.test">',
    "</a>",
    "<p style='x'>",
    "javascript:",
    "on",
    "<b onclick=x>",
    "<!--",
    "-->",
    '<a href="https://ok.test" onclick="x">',
    "<template>",
    "<li>",
    "</ul>",
)


def test_nothing_dangerous_survives() -> None:
    """A seeded random property: 3000 mixes of hostile pieces (SC-004)."""
    rng = random.Random(18)  # noqa: S311 - a repeatable test, not a secret
    for _ in range(3000):
        raw = "".join(rng.choice(PIECES) for _ in range(rng.randint(0, 12)))
        out = clean(raw)
        # every "<" of the text is escaped, so whatever is between < and > is a tag we emitted
        for tag in re.findall(r"<[^>]*>", out):
            name = re.match(r"</?([a-z]+)", tag)
            assert name is not None and name.group(1) in KEPT, (raw, tag)
            assert "style=" not in tag and "javascript:" not in tag.lower(), (raw, tag)
            assert not re.search(r"\son[a-z]+=", tag), (raw, tag)
