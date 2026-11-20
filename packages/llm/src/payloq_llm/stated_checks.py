"""Section C: code checks on model extraction (stated quotes + conversions)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from payloq_llm.nl_cash_intent import extract_euro_amounts
from payloq_schemas.constants import (
    GROUNDING_ABSOLUTE_TOLERANCE_EUR,
    GROUNDING_RELATIVE_TOLERANCE,
)

GROWTH_MIN = -0.2
GROWTH_MAX = 0.2

# Section B field → engine / fidelity field names.
B_TO_ENGINE: dict[str, str] = {
    "revenue_monthly_eur": "monthly_revenue_start_eur",
    "revenue_annual_eur": "revenue_annual_eur",
    "growth_per_month_fraction": "monthly_revenue_growth",
    "starting_cash_eur": "starting_cash_eur",
    "covenant_min_cash_eur": "covenant_min_cash_eur",
    "dso_days": "days_sales_outstanding",
    "dpo_days": "days_payables_outstanding",
}

ENGINE_TO_B: dict[str, str] = {v: k for k, v in B_TO_ENGINE.items() if k != "revenue_annual_eur"}


@dataclass
class StatedIssue:
    field: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "message": self.message}


@dataclass
class StatedCheckResult:
    ok: bool
    issues: list[StatedIssue] = field(default_factory=list)

    def error_text(self) -> str:
        if not self.issues:
            return ""
        return "; ".join(f"{i.field}: {i.message}" for i in self.issues)


def _near(value: float, candidate: float) -> bool:
    if abs(value - candidate) <= GROUNDING_ABSOLUTE_TOLERANCE_EUR:
        return True
    denom = max(abs(candidate), abs(value), 1.0)
    return abs(value - candidate) / denom <= GROUNDING_RELATIVE_TOLERANCE


def _amounts_in_text(text: str) -> list[float]:
    return [amt for amt, _ in extract_euro_amounts(text or "")]


def _value_in_quote(value: float, quote: str, *, field: str) -> bool:
    """Value must appear in the quote after unit parsing (k, M, million, %, €)."""
    q = quote or ""
    if field in {"dso_days", "dpo_days", "days_sales_outstanding", "days_payables_outstanding"}:
        for m in re.finditer(r"\b(\d{1,3})\b", q):
            if _near(float(value), float(m.group(1))):
                return True
        return False
    if field in {"growth_per_month_fraction", "monthly_revenue_growth"}:
        for m in re.finditer(r"([+-]?\d+(?:[.,]\d+)?)\s*%", q):
            pct = float(m.group(1).replace(",", "."))
            if _near(float(value), pct / 100.0):
                return True
        for m in re.finditer(r"([+-]?0\.\d{2,6})", q):
            if _near(float(value), float(m.group(1))):
                return True
        return False
    amounts = _amounts_in_text(q)
    # Also parse bare "million" / k / M inside quote
    low = q.casefold()
    for m in re.finditer(
        r"(\d+(?:[.,]\d+)?)\s*(million|miljoonaa|m\b|k\b)?",
        low,
        flags=re.IGNORECASE,
    ):
        try:
            n = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit.startswith("m"):
            n *= 1_000_000.0
        elif unit == "k":
            n *= 1_000.0
        amounts.append(n)
    return any(_near(float(value), float(a)) for a in amounts)


_KNOWN_STATED_FIELDS: frozenset[str] = frozenset(
    {
        "revenue_monthly_eur",
        "revenue_annual_eur",
        "growth_per_month_fraction",
        "starting_cash_eur",
        "covenant_min_cash_eur",
        "dso_days",
        "dpo_days",
        "one_off_events",
        "industry",
        "company_size",
        "scenario_shape",
        # engine aliases
        "monthly_revenue_start_eur",
        "monthly_revenue_growth",
        "days_sales_outstanding",
        "days_payables_outstanding",
        "special_investment_eur",
        "special_investment_month",
        "target_cash_at_end_eur",
    }
)


def normalize_stated_map(
    stated: dict[str, str] | None,
    parameters: dict[str, Any] | None,
) -> dict[str, str]:
    """
    Remap malformed ``stated`` keys.

    Weak models sometimes use the quote text as the key. Map those back onto
    parameter field names by matching values inside the quote.
    """
    stated = dict(stated or {})
    parameters = parameters or {}
    out: dict[str, str] = {}
    for key, quote in stated.items():
        quote_s = str(quote or "")
        if key in _KNOWN_STATED_FIELDS:
            out[key] = quote_s
            continue
        # key is probably a quote — find matching parameter field
        matched: str | None = None
        for field_name, raw in parameters.items():
            if field_name in {"one_off_events", "industry", "company_size"}:
                continue
            if raw is None or raw == "":
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if _value_in_quote(val, quote_s or key, field=field_name):
                matched = field_name
                break
        # one_off amounts
        if matched is None:
            events = parameters.get("one_off_events") or []
            if isinstance(events, list) and events:
                try:
                    amt = float(events[0].get("amount_eur"))  # type: ignore[union-attr]
                except (TypeError, ValueError, AttributeError):
                    amt = None
                if amt is not None and _value_in_quote(amt, quote_s or key, field="amount_eur"):
                    matched = "one_off_events"
        if matched:
            out[matched] = quote_s or str(key)
        else:
            # Keep original only if it looks like a field name; else drop noise
            if key in _KNOWN_STATED_FIELDS:
                out[key] = quote_s
    return out


def check_stated_quotes(
    *,
    description: str,
    stated: dict[str, str] | None,
    parameters: dict[str, Any] | None,
) -> StatedCheckResult:
    """
    For every field in ``stated``: quote must appear in description (case-insensitive),
    and the parameter value must appear in the quote after unit parsing.
    """
    issues: list[StatedIssue] = []
    stated = stated or {}
    parameters = parameters or {}
    desc_low = (description or "").casefold()

    skip_numeric = {
        "scenario_shape",
        "industry",
        "company_size",
        "scenario_shape_quote",
    }
    for field_name, quote in stated.items():
        if quote is None or str(quote).strip() == "":
            issues.append(
                StatedIssue(
                    field=field_name,
                    message="stated entry has empty quote",
                )
            )
            continue
        quote_s = str(quote)
        if quote_s.casefold() not in desc_low:
            issues.append(
                StatedIssue(
                    field=field_name,
                    message=f"quote not found in description: {quote_s!r}",
                )
            )
            continue

        if field_name in skip_numeric:
            # industry / company_size / scenario_shape: quote presence already checked;
            # no numeric value required.
            continue

        # Resolve value from parameters (B names or engine aliases).
        raw = parameters.get(field_name)
        if raw is None and field_name in B_TO_ENGINE:
            raw = parameters.get(B_TO_ENGINE[field_name])
        if raw is None and field_name in ENGINE_TO_B:
            raw = parameters.get(ENGINE_TO_B[field_name])
        if field_name == "one_off_events" or field_name.startswith("one_off"):
            # Validated separately via event amounts.
            events = parameters.get("one_off_events") or []
            if isinstance(events, list):
                for i, ev in enumerate(events):
                    if not isinstance(ev, dict):
                        continue
                    try:
                        amt = float(ev.get("amount_eur"))
                    except (TypeError, ValueError):
                        continue
                    if not _value_in_quote(amt, quote_s, field="amount_eur"):
                        issues.append(
                            StatedIssue(
                                field=f"one_off_events[{i}].amount_eur",
                                message=f"value {amt} not in quote {quote_s!r}",
                            )
                        )
            continue
        if raw is None or raw == "":
            issues.append(
                StatedIssue(
                    field=field_name,
                    message="listed in stated but parameter value is null",
                )
            )
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if not _value_in_quote(val, quote_s, field=field_name):
            issues.append(
                StatedIssue(
                    field=field_name,
                    message=f"value {val} not found in quote after unit parsing: {quote_s!r}",
                )
            )

    return StatedCheckResult(ok=not issues, issues=issues)


def apply_annual_to_monthly(parameters: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """If annual set and monthly null: monthly = annual / 12. Record conversion."""
    out = dict(parameters)
    changes: list[dict[str, Any]] = []
    monthly = out.get("revenue_monthly_eur")
    if monthly is None:
        monthly = out.get("monthly_revenue_start_eur")
    annual = out.get("revenue_annual_eur")
    if (monthly is None or monthly == "") and annual not in (None, ""):
        try:
            annual_f = float(annual)
        except (TypeError, ValueError):
            return out, changes
        monthly_f = round(annual_f / 12.0, 2)
        out["revenue_monthly_eur"] = monthly_f
        out["monthly_revenue_start_eur"] = monthly_f
        changes.append(
            {
                "field": "revenue_monthly_eur",
                "original": None,
                "clipped": monthly_f,
                "message": f"converted revenue_annual_eur={annual_f} / 12 → {monthly_f}",
                "source": "code_conversion",
            }
        )
    return out, changes


def check_growth_bounds(growth: float | None) -> StatedIssue | None:
    if growth is None:
        return None
    try:
        g = float(growth)
    except (TypeError, ValueError):
        return StatedIssue(field="growth_per_month_fraction", message="not a number")
    if g < GROWTH_MIN or g > GROWTH_MAX:
        return StatedIssue(
            field="growth_per_month_fraction",
            message=f"growth {g} outside [{GROWTH_MIN}, {GROWTH_MAX}]",
        )
    return None


def check_one_off_events(
    events: Any,
    *,
    months: int,
) -> list[StatedIssue]:
    issues: list[StatedIssue] = []
    if events is None:
        return issues
    if not isinstance(events, list):
        return [
            StatedIssue(field="one_off_events", message="must be an array"),
        ]
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            issues.append(StatedIssue(field=f"one_off_events[{i}]", message="must be object"))
            continue
        try:
            month = int(ev.get("month_index"))
        except (TypeError, ValueError):
            issues.append(
                StatedIssue(
                    field=f"one_off_events[{i}].month_index",
                    message="month_index required",
                )
            )
            continue
        if month < 1 or month > int(months):
            issues.append(
                StatedIssue(
                    field=f"one_off_events[{i}].month_index",
                    message=f"month_index {month} not in 1..{months}",
                )
            )
        direction = str(ev.get("direction") or "").strip().lower()
        if direction in {"in", "out"}:
            direction = "inflow" if direction == "in" else "outflow"
        if direction not in {"inflow", "outflow"}:
            issues.append(
                StatedIssue(
                    field=f"one_off_events[{i}].direction",
                    message="direction must be inflow or outflow",
                )
            )
    return issues


def map_b_parameters_to_engine(parameters: dict[str, Any]) -> dict[str, Any]:
    """Map section-B parameter names onto engine ``ParametersFromLanguageModel`` keys."""
    p = dict(parameters or {})
    out: dict[str, Any] = {}

    monthly = p.get("revenue_monthly_eur")
    if monthly is None:
        monthly = p.get("monthly_revenue_start_eur")
    if monthly is not None:
        out["monthly_revenue_start_eur"] = monthly

    growth = p.get("growth_per_month_fraction")
    if growth is None:
        growth = p.get("monthly_revenue_growth")
    if growth is not None:
        out["monthly_revenue_growth"] = growth

    if p.get("starting_cash_eur") is not None:
        out["starting_cash_eur"] = p["starting_cash_eur"]

    cov = p.get("covenant_min_cash_eur")
    if cov is not None:
        out["covenant_min_cash_eur"] = cov
        out["target_cash_at_end_eur"] = cov

    dso = p.get("dso_days")
    if dso is None:
        dso = p.get("days_sales_outstanding")
    if dso is not None:
        out["days_sales_outstanding"] = dso

    dpo = p.get("dpo_days")
    if dpo is None:
        dpo = p.get("days_payables_outstanding")
    if dpo is not None:
        out["days_payables_outstanding"] = dpo

    events = p.get("one_off_events")
    if events:
        mapped: list[dict[str, Any]] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            direction = str(ev.get("direction") or "outflow").strip().lower()
            if direction in {"out", "outflow"}:
                direction = "outflow"
            elif direction in {"in", "inflow"}:
                direction = "inflow"
            mapped.append(
                {
                    "type": ev.get("type") or "other",
                    "amount_eur": ev.get("amount_eur"),
                    "month_index": ev.get("month_index"),
                    "direction": direction,
                    "label": ev.get("label"),
                }
            )
        out["one_off_events"] = mapped
        # Mirror first outflow into special_investment_* for the engine.
        for ev in mapped:
            if ev.get("direction") == "outflow" and ev.get("amount_eur"):
                out["special_investment_eur"] = float(ev["amount_eur"])
                out["special_investment_month"] = int(ev.get("month_index") or 2)
                break

    if "revenue_annual_eur" in p:
        out["revenue_annual_eur"] = p.get("revenue_annual_eur")

    return out
