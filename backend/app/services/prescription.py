"""Parsing of prescription text such as "8-10", "10/side", "20-40 sec" or "35 min"."""

import re
from dataclasses import dataclass

_RANGE = r"(\d+)\s*(?:-|–|to)\s*(\d+)|(\d+)"
_PATTERN = re.compile(
    rf"^\s*(?:{_RANGE})\s*(?P<unit>sec|secs|seconds|s|min|mins|minutes|m)?\s*"
    r"(?:/\s*(?P<per>side|leg|arm))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Prescription:
    text: str
    rep_min: int | None = None
    rep_max: int | None = None
    duration_min: int | None = None  # seconds
    duration_max: int | None = None  # seconds
    per_side: bool = False

    @property
    def is_duration(self) -> bool:
        return self.duration_min is not None


def parse_prescription(text: str | None) -> Prescription | None:
    """Parse a prescription. Returns None for empty or unrecognised text."""
    if text is None or not text.strip():
        return None
    match = _PATTERN.match(text)
    if not match:
        return None
    if match.group(3):
        low = high = int(match.group(3))
    else:
        low, high = int(match.group(1)), int(match.group(2))
    if low > high:
        low, high = high, low
    unit = (match.group("unit") or "").lower()
    per_side = match.group("per") is not None
    clean = text.strip()
    if unit.startswith("s"):
        return Prescription(clean, duration_min=low, duration_max=high, per_side=per_side)
    if unit.startswith("m"):
        return Prescription(clean, duration_min=low * 60, duration_max=high * 60, per_side=per_side)
    return Prescription(clean, rep_min=low, rep_max=high, per_side=per_side)


def format_prescription(
    rep_min: int | None,
    rep_max: int | None,
    duration_min: int | None,
    duration_max: int | None,
    per_side: bool,
) -> str | None:
    """Build display text from structured targets (used when targets are edited)."""
    suffix = "/side" if per_side else ""
    if duration_min is not None:
        hi = duration_max if duration_max is not None else duration_min
        if duration_min % 60 == 0 and hi % 60 == 0 and duration_min >= 120:
            lo_m, hi_m = duration_min // 60, hi // 60
            return f"{lo_m} min{suffix}" if lo_m == hi_m else f"{lo_m}-{hi_m} min{suffix}"
        return f"{duration_min} sec{suffix}" if duration_min == hi else f"{duration_min}-{hi} sec{suffix}"
    if rep_min is not None:
        hi = rep_max if rep_max is not None else rep_min
        return f"{rep_min}{suffix}" if rep_min == hi else f"{rep_min}-{hi}{suffix}"
    return None
