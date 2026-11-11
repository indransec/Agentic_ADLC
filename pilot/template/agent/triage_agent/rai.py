"""Basic responsible-AI counters (FR-005), labelled basic: fixed pattern lists, not classifiers."""

TOXIC_TERMS = ("idiot", "stupid", "useless", "shut up", "hate you", "moron")
JAILBREAK_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard your rules",
    "you are now",
    "pretend you are",
    "reveal your instructions",
)


def toxic_count(text: str) -> int:
    lowered = text.lower()
    return sum(term in lowered for term in TOXIC_TERMS)


def jailbreak_count(text: str) -> int:
    lowered = text.lower()
    return sum(phrase in lowered for phrase in JAILBREAK_PHRASES)
