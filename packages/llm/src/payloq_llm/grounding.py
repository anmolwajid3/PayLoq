"""Ground stated LLM parameter numbers against the NL description (work order A).

Every stated number must appear in the description after parsing units (k, M, %, €).
Reject → retry once with the error listed → fail if still mismatched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from payloq_llm.nl_cash_intent import extract_euro_amounts
from payloq_llm.nl_param_hints import extract_growth_rate
from payloq_schemas.constants import (
    GROUNDING_ABSOLUTE_TOLERANCE_EUR,
    GROUNDING_RELATIVE_TOLERANCE,
)


# Fields checked for euro grounding when non-null / stated.
_EURO_GROUND_FIELDS: tuple[str, ...] = (
    "monthly_revenue_start_eur",
    "starting_cash_eur",
    "target_cash_at_end_eur",
    "covenant_min_cash_eur",
    "special_investment_eur",
)

_DAY_GROUND_FIELDS: tuple[str, ...] = (
    "days_sales_outstanding",
    "days_payables_outstanding",
)


@dataclass
class GroundingIssue:
    field: str
    value: float
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "value": self.value, "message": self.message}


@dataclass
class GroundingResult:
    ok: bool
    issues: list[GroundingIssue] = field(default_factory=list)

    def error_text(self) -> str:
        if not self.issues:
            return ""
        parts = [f"{i.field}={i.value}: {i.message}" for i in self.issues]
        return "Grounding rejected: " + "; ".join(parts)


def _amounts_in_description(description: str) -> list[float]:
    return [amt for amt, _idx in extract_euro_amounts(description or "")]


def _near(value: float, candidate: float) -> bool:
    if abs(value - candidate) <= GROUNDING_ABSOLUTE_TOLERANCE_EUR:
        return True
    denom = max(abs(candidate), abs(value), 1.0)
    return abs(value - candidate) / denom <= GROUNDING_RELATIVE_TOLERANCE


def _value_appears(value: float, amounts: list[float]) -> bool:
    return any(_near(float(value), float(a)) for a in amounts)


def _day_literals(description: str) -> set[float]:
    """Collect day-like integers from the description (14–120)."""
    import re

    found: set[float] = set()
    for m in re.finditer(
        r"\b(\d{1,3})\s*(?:days?|pv|päivää|paivaa|day)\b",
        description or "",
        flags=re.IGNORECASE,
    ):
        found.add(float(m.group(1)))
    # Also bare integers that look like DSO/DPO when near payment wording
    blob = (description or "").lower()
    for m in re.finditer(r"\b(\d{2,3})\b", blob):
        n = float(m.group(1))
        if 14 <= n <= 120:
            window = blob[max(0, m.start() - 40) : m.end() + 40]
            if any(
                k in window
                for k in (
                    "dso",
                    "dpo",
                    "payment",
                    "receivable",
                    "payable",
                    "maksuehto",
                    "myyntisaami",
                    "ostovel",
                    "days",
                    "päiv",
                )
            ):
                found.add(n)
    return found


def _growth_matches(value: float, description: str) -> bool:
    """Growth fraction must match a % or fraction stated in the description."""
    nl = extract_growth_rate(description)
    if nl is not None and _near(float(value), float(nl)):
        return True
    import re

    # Explicit percent: 0.8% → 0.008
    for m in re.finditer(
        r"([+-]?\d+(?:[.,]\d+)?)\s*%",
        description or "",
    ):
        pct = float(m.group(1).replace(",", "."))
        frac = pct / 100.0
        if _near(float(value), frac):
            return True
    # Explicit fraction already in text
    for m in re.finditer(r"([+-]?0\.\d{2,6})", description or ""):
        if _near(float(value), float(m.group(1))):
            return True
    return False


def ground_stated_parameters(
    params: dict[str, Any],
    description: str,
    *,
    field_sources: dict[str, str] | None = None,
) -> GroundingResult:
    """
    Verify that every *stated* numeric field appears in ``description``.

    Assumed fields (source=assumed) are skipped. Null / missing fields are skipped.
    Special investment of 0 is ignored (means none).
    """
    sources = field_sources or params.get("field_sources") or {}
    issues: list[GroundingIssue] = []
    amounts = _amounts_in_description(description)
    day_lits = _day_literals(description)

    for key in _EURO_GROUND_FIELDS:
        if sources.get(key) == "assumed":
            continue
        raw = params.get(key)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if key == "special_investment_eur" and abs(val) < 1e-9:
            continue
        if not _value_appears(val, amounts):
            issues.append(
                GroundingIssue(
                    field=key,
                    value=val,
                    message=(
                        f"value {val} does not appear in the description after "
                        f"parsing units (k, M, €); description amounts sample="
                        f"{sorted(set(round(a, 2) for a in amounts))[:12]}"
                    ),
                )
            )

    for key in _DAY_GROUND_FIELDS:
        if sources.get(key) == "assumed":
            continue
        raw = params.get(key)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        # Only ground when the description mentions day terms at all
        if not day_lits:
            continue
        if not any(_near(val, d) for d in day_lits):
            issues.append(
                GroundingIssue(
                    field=key,
                    value=val,
                    message=f"value {val} days not found among description day literals {sorted(day_lits)}",
                )
            )

    growth_key = "monthly_revenue_growth"
    if sources.get(growth_key) != "assumed":
        raw = params.get(growth_key)
        if raw is not None and raw != "":
            try:
                gval = float(raw)
            except (TypeError, ValueError):
                gval = None
            if gval is not None and abs(gval) > 1e-12:
                # Only enforce when description appears to state growth
                import re

                mentions_growth = bool(
                    re.search(
                        r"%|growth|kasvu|per\s+month|kuukaudessa",
                        description or "",
                        flags=re.IGNORECASE,
                    )
                )
                if mentions_growth and not _growth_matches(gval, description):
                    issues.append(
                        GroundingIssue(
                            field=growth_key,
                            value=gval,
                            message=(
                                f"growth fraction {gval} does not match a % / fraction "
                                "stated in the description"
                            ),
                        )
                    )

    # one_off_events amounts
    if sources.get("one_off_events") != "assumed":
        events = params.get("one_off_events") or []
        if isinstance(events, list):
            for i, ev in enumerate(events):
                if not isinstance(ev, dict):
                    continue
                try:
                    amt = float(ev.get("amount_eur") or 0)
                except (TypeError, ValueError):
                    continue
                if amt <= 0:
                    continue
                if not _value_appears(amt, amounts):
                    issues.append(
                        GroundingIssue(
                            field=f"one_off_events[{i}].amount_eur",
                            value=amt,
                            message=f"event amount {amt} not found in description",
                        )
                    )

    return GroundingResult(ok=not issues, issues=issues)


def mark_stated_sources(params: dict[str, Any]) -> dict[str, str]:
    """Mark every non-null numeric / structured field as ``stated``."""
    sources: dict[str, str] = {}
    keys = (
        "monthly_revenue_start_eur",
        "monthly_revenue_growth",
        "days_sales_outstanding",
        "days_payables_outstanding",
        "target_cash_at_end_eur",
        "starting_cash_eur",
        "covenant_min_cash_eur",
        "special_investment_eur",
        "cost_shares_of_revenue",
        "one_off_events",
        "monthly_revenue_factors",
        "partly_fixed_costs",
    )
    for key in keys:
        val = params.get(key)
        if val is None or val == "":
            continue
        if key == "special_investment_eur" and float(val or 0) == 0:
            continue
        if key == "one_off_events" and not val:
            continue
        sources[key] = "stated"
    return sources
