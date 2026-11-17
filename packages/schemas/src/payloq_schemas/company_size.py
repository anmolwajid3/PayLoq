"""Parse company size for FR-A-02 / FR-A-06 (employee count or small/medium)."""

from __future__ import annotations

import re
from typing import Any

MISSING_MSG = (
    "Company size is missing. Use a number of employees or a label (small, medium)."
)
INVALID_MSG = (
    "Company size must be a number of employees or a label (small, medium)."
)

# Canonical labels (SRS FR-A-06) plus common Finnish synonyms for the UI/CLI.
_LABEL_ALIASES: dict[str, str] = {
    "small": "small",
    "medium": "medium",
    "pieni": "small",
    "keskikokoinen": "medium",
    "keski": "medium",
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

    Accepts (FR-A-06):
    - labels ``small`` / ``medium`` (and FI synonyms pieni / keskikokoinen)
    - employee counts: ``8``, ``12 employees``, ``12 työntekijää``

    Returns ``"small"``, ``"medium"``, or ``"{n} employees"``.
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
