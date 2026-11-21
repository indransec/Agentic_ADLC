"""A static accessibility check of a rendered page (017 research R-09, SC-005).

Not a browser: it checks what can be read from the HTML. ``lang`` on ``<html>``; one ``<main>``;
``<header>`` and ``<nav>`` landmarks; exactly one ``<h1>``; every form control (except hidden
inputs and buttons) labelled by a ``<label for>`` or ``aria-label``; every button and link with a
name; no positive ``tabindex``. Returns the problems found.
"""

from __future__ import annotations

from html.parser import HTMLParser


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.labels: set[str] = set()
        self.open: list[tuple[str, dict[str, str], list[str]]] = []
        self.named: list[tuple[str, str]] = []  # (tag, accessible text) of buttons and links

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: v or "" for k, v in attrs}
        self.tags.append((tag, values))
        if tag == "label" and "for" in values:
            self.labels.add(values["for"])
        if tag in ("button", "a"):
            self.open.append((tag, values, []))

    def handle_data(self, data: str) -> None:
        for _, _, texts in self.open:
            texts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("button", "a") and self.open and self.open[-1][0] == tag:
            name, values, texts = self.open.pop()
            self.named.append((name, values.get("aria-label") or "".join(texts).strip()))


def problems(html: str) -> list[str]:
    found = _Collector()
    found.feed(html)
    tags = found.tags
    names = [t for t, _ in tags]
    issues = []
    html_tag = next((a for t, a in tags if t == "html"), None)
    if html_tag is None or not html_tag.get("lang"):
        issues.append("<html> has no lang")
    if names.count("main") != 1:
        issues.append(f"{names.count('main')} <main> landmarks")
    for landmark in ("header", "nav"):
        if landmark not in names:
            issues.append(f"no <{landmark}> landmark")
    if names.count("h1") != 1:
        issues.append(f"{names.count('h1')} <h1> headings")
    for tag, attrs in tags:
        labelled = attrs.get("id") in found.labels or attrs.get("aria-label")
        control = tag in ("input", "select", "textarea") and attrs.get("type") not in (
            "hidden",
            "submit",
        )
        if control and not labelled:
            issues.append(f"<{tag} name={attrs.get('name')!r}> has no label")
        if attrs.get("tabindex", "0").lstrip("-").isdigit() and int(attrs.get("tabindex", "0")) > 0:
            issues.append(f"<{tag}> has a positive tabindex")
    issues += [f"<{tag}> has no accessible name" for tag, text in found.named if not text]
    return issues
