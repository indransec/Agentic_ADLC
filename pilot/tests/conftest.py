"""Shared paths for the pilot tests."""

from pathlib import Path

PILOT = Path(__file__).resolve().parents[1]
TEMPLATE = PILOT / "template"
DEFAULT_FILL = PILOT / "fills" / "default"
VARIANT_FILL = PILOT / "fills" / "variant"
