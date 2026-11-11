"""A basic personal-data check: e-mail addresses and phone numbers (FR-005, SC-006)."""

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(
    r"(?<![\w])(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)\d{3,4}[\s-]?\d{3,4}(?![\w])"
)


def find_pii(text: str) -> list[str]:
    found = [m.group(0) for m in EMAIL.finditer(text)]
    found += [m.group(0).strip() for m in PHONE.finditer(text)]
    return found
