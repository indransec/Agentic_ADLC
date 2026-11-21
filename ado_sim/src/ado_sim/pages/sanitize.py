"""Allow-list HTML for display (feature 018, FR-005, FR-006; research R-05).

Keeps a small formatting subset and http(s) links; drops every other tag and every other
attribute; drops the content of elements that hold code or embedded documents; escapes all text.
Its output is the only string marked safe in any template.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser

KEPT = frozenset({"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "a"})
VOID = frozenset({"br"})
DROPPED_WITH_CONTENT = frozenset({"script", "style", "iframe", "object", "template"})
LINK_SCHEMES = ("http://", "https://")


def web_address(value: str) -> str | None:
    """The value as a link target when it is wholly an http(s) address, else None."""
    text = value.strip()
    if text.lower().startswith(LINK_SCHEMES) and not any(c.isspace() for c in text):
        return text
    return None


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[tuple[str, bool]] = []  # (tag, emitted)
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROPPED_WITH_CONTENT:
            self.skipping += 1
            return
        if self.skipping or tag not in KEPT:
            return
        if tag in VOID:
            self.out.append(f"<{tag}>")
            return
        if tag == "a":
            href = web_address(dict(attrs).get("href") or "")
            if href is None:
                self.open.append((tag, False))
                return
            self.out.append(
                f'<a href="{html.escape(href, quote=True)}" target="_blank"'
                ' rel="noopener noreferrer">'
            )
        else:
            self.out.append(f"<{tag}>")
        self.open.append((tag, True))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROPPED_WITH_CONTENT:
            return
        self.handle_starttag(tag, attrs)
        if tag in KEPT and tag not in VOID and not self.skipping:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in DROPPED_WITH_CONTENT:
            self.skipping = max(0, self.skipping - 1)
            return
        if self.skipping or tag not in KEPT or tag in VOID:
            return
        if not any(name == tag for name, _ in self.open):
            return
        while self.open:
            name, emitted = self.open.pop()
            if emitted:
                self.out.append(f"</{name}>")
            if name == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        self.close()
        while self.open:
            name, emitted = self.open.pop()
            if emitted:
                self.out.append(f"</{name}>")
        return "".join(self.out)


def clean(value: str) -> str:
    cleaner = _Cleaner()
    cleaner.feed(value)
    return cleaner.result()
