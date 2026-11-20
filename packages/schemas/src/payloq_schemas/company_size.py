"""Parse company size for FR-A-02 / FR-A-06 (employee count or small/medium/large)."""

from __future__ import annotations

import re
from typing import Any, Literal

SizeBand = Literal["small", "medium", "large"]

MISSING_MSG = (
    "Company size is missing. Use a number of employees or a label "
    "(small, medium, large)."
)
INVALID_MSG = (
    "Company size must be a number of employees or a label "
    "(small, medium, large)."
)

# Canonical labels (SRS FR-A-06 + large) plus common Finnish synonyms for the UI/CLI.
_LABEL_ALIASES: dict[str, str] = {
    "small": "small",
    "medium": "medium",
    "large": "large",
    "pieni": "small",
    "keskikokoinen": "medium",
    "keski": "medium",
    "suuri": "large",
    "iso": "large",
}

# EU-style headcount bands for numeric sizes → generator scale.
_SMALL_MAX_EMPLOYEES = 49
_MEDIUM_MAX_EMPLOYEES = 249

# Stub / repair defaults: monthly revenue and cash/invest multipliers vs small baseline.
_BAND_REVENUE_EUR: dict[SizeBand, float] = {
    "small": 200_000.0,
    "medium": 550_000.0,
    # Mid-market / steel-style NL should not collapse to SME (~2M/year) scale.
    "large": 1_200_000.0,
}
_BAND_CASH_MULT: dict[SizeBand, float] = {
    "small": 1.0,
    "medium": 2.5,
    "large": 5.0,
}
_BAND_INVEST_MULT: dict[SizeBand, float] = {
    "small": 1.0,
    "medium": 2.0,
    "large": 4.0,
}

_EMPLOYEE_RE = re.compile(
    r"""
    ^\s*
    (?P<n>\d{1,6})
    (?:
        \s+
        (?:
            employees?
            |emps?
            |työntekijää
            |tyontekijaa
            |henkilöä
            |henkiloa
        )
    )?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_company_size(value: Any) -> str:
    """
    Normalize company size to a canonical string for ``options.company_size``.

    Accepts (FR-A-06 + large):
    - labels ``small`` / ``medium`` / ``large`` (and FI synonyms pieni / keskikokoinen / suuri)
    - employee counts: ``8``, ``12 employees``, ``420``, ``12 työntekijää``

    Returns ``"small"``, ``"medium"``, ``"large"``, or ``"{n} employees"``.
    Raises ``ValueError`` with a clear message when empty or invalid.
    """
    if value is None:
        raise ValueError(MISSING_MSG)

    if isinstance(value, bool):
        raise ValueError(INVALID_MSG)

    if isinstance(value, int):
        if value < 1:
            raise ValueError(INVALID_MSG)
        return f"{value} employees"

    if isinstance(value, float):
        if not value.is_integer() or value < 1:
            raise ValueError(INVALID_MSG)
        return f"{int(value)} employees"

    text = str(value).strip()
    if not text:
        raise ValueError(MISSING_MSG)

    label = _LABEL_ALIASES.get(text.casefold())
    if label is not None:
        return label

    match = _EMPLOYEE_RE.match(text)
    if match:
        n = int(match.group("n"))
        if n < 1:
            raise ValueError(INVALID_MSG)
        return f"{n} employees"

    raise ValueError(INVALID_MSG)


def size_band(canonical: str) -> SizeBand:
    """
    Map a canonical ``parse_company_size`` result to a generator scale band.

    Labels map 1:1. Employee counts use EU-style thresholds:
    1–49 small, 50–249 medium, 250+ large.
    """
    text = (canonical or "").strip().casefold()
    if text in ("small", "medium", "large"):
        return text  # type: ignore[return-value]

    match = _EMPLOYEE_RE.match(text)
    if match:
        n = int(match.group("n"))
        if n <= _SMALL_MAX_EMPLOYEES:
            return "small"
        if n <= _MEDIUM_MAX_EMPLOYEES:
            return "medium"
        return "large"

    # Unknown free-text that skipped the parser — keep legacy small defaults.
    return "small"


def scale_defaults_for_size(canonical: str) -> dict[str, Any]:
    """
    Sensible repair defaults for revenue and cash/invest multipliers.

    Returns ``band``, ``monthly_revenue_start_eur``, ``cash_mult``, ``invest_mult``.
    """
    band = size_band(canonical)
    return {
        "band": band,
        "monthly_revenue_start_eur": _BAND_REVENUE_EUR[band],
        "cash_mult": _BAND_CASH_MULT[band],
        "invest_mult": _BAND_INVEST_MULT[band],
    }
