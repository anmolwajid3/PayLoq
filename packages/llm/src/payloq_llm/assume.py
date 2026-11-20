"""Fill unstated parameters from industry×size range tables (work order B).

LLM extract returns nulls for unstated fields; this code draws defaults with a
fixed seed and marks ``source: assumed``. Never invents company-specific values.
"""

from __future__ import annotations

from typing import Any

from payloq_schemas.constants import REQUIRED_STATED_FIELDS
from payloq_schemas.industry_defaults import draw_assumed_defaults


class MissingRequiredParameterError(ValueError):
    """Raised when a required stated field is null after LLM extraction."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"Missing required parameter: {field}")


# Fields that may be assumed when null (work order B).
_ASSUMABLE_SCALARS: tuple[str, ...] = (
    "monthly_revenue_start_eur",
    "monthly_revenue_growth",
    "days_sales_outstanding",
    "days_payables_outstanding",
    "target_cash_at_end_eur",
    "covenant_min_cash_eur",
    "special_investment_eur",
    "special_investment_month",
)


def drop_incomplete_one_off_events(
    events: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Keep only one-off events that have amount, month_index, and direction.

    Incomplete rows (null amount / month / direction) are dropped — work order B
    rejects missing month or direction; Run #19 Ollama often emits partial CAPEX
    stubs with null numerics.
    """
    changes: list[dict[str, Any]] = []
    if events is None:
        return [], changes
    if not isinstance(events, list):
        return [], [
            {
                "field": "one_off_events",
                "original": events,
                "clipped": [],
                "message": "dropped non-list one_off_events",
                "source": "assume",
            }
        ]

    cleaned: list[dict[str, Any]] = []
    for i, raw in enumerate(events):
        if not isinstance(raw, dict):
            changes.append(
                {
                    "field": f"one_off_events[{i}]",
                    "original": raw,
                    "clipped": None,
                    "message": "dropped non-object one_off event",
                    "source": "assume",
                }
            )
            continue
        amount = raw.get("amount_eur")
        month = raw.get("month_index")
        direction = raw.get("direction")
        event_type = str(raw.get("type") or "other").strip().lower() or "other"
        # CAPEX is always an outflow — fill missing direction before completeness check.
        if event_type in {"capex", "capital_expenditure", "investment"} and (
            direction is None or direction == ""
        ):
            direction = "out"
            event_type = "capex"
        missing = [
            name
            for name, val in (
                ("amount_eur", amount),
                ("month_index", month),
                ("direction", direction),
            )
            if val is None or val == ""
        ]
        if missing:
            changes.append(
                {
                    "field": f"one_off_events[{i}]",
                    "original": raw,
                    "clipped": None,
                    "message": (
                        "dropped incomplete one_off event "
                        f"(missing {', '.join(missing)})"
                    ),
                    "source": "assume",
                }
            )
            continue
        try:
            amt_f = float(amount)
            month_i = int(month)
        except (TypeError, ValueError):
            changes.append(
                {
                    "field": f"one_off_events[{i}]",
                    "original": raw,
                    "clipped": None,
                    "message": "dropped one_off event with non-numeric amount/month",
                    "source": "assume",
                }
            )
            continue
        if amt_f <= 0 or not (1 <= month_i <= 24):
            changes.append(
                {
                    "field": f"one_off_events[{i}]",
                    "original": raw,
                    "clipped": None,
                    "message": "dropped one_off event with invalid amount/month range",
                    "source": "assume",
                }
            )
            continue
        direction_s = str(direction).strip().lower()
        if direction_s in {"inflow", "in"}:
            direction_s = "in"
        elif direction_s in {"outflow", "out"}:
            direction_s = "out"
        else:
            changes.append(
                {
                    "field": f"one_off_events[{i}]",
                    "original": raw,
                    "clipped": None,
                    "message": f"dropped one_off event with invalid direction={direction!r}",
                    "source": "assume",
                }
            )
            continue
        if event_type in {"capex", "capital_expenditure", "investment"}:
            event_type = "capex"
            direction_s = "out"
        cleaned.append(
            {
                "type": event_type,
                "amount_eur": amt_f,
                "month_index": month_i,
                "direction": direction_s,
                "label": raw.get("label"),
            }
        )
    return cleaned, changes


def apply_assumed_defaults(
    extracted: dict[str, Any],
    *,
    industry: str | None,
    company_size: str | None,
    seed: int,
    description: str | None = None,
    require_starting_cash: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Merge stated extraction with assumed draws.

    - Stated (non-null) values keep ``source: stated``.
    - Null assumable fields are filled from the industry×size table.
    - ``starting_cash_eur`` is required when ``require_starting_cash`` (LLM path).
    """
    out = dict(extracted or {})
    changes: list[dict[str, Any]] = []
    sources: dict[str, str] = dict(out.get("field_sources") or {})

    # Normalize covenant ↔ target before required checks
    if out.get("target_cash_at_end_eur") is None and out.get("covenant_min_cash_eur") is not None:
        out["target_cash_at_end_eur"] = out["covenant_min_cash_eur"]
        sources.setdefault("target_cash_at_end_eur", sources.get("covenant_min_cash_eur", "stated"))
    if out.get("covenant_min_cash_eur") is None and out.get("target_cash_at_end_eur") is not None:
        out["covenant_min_cash_eur"] = out["target_cash_at_end_eur"]

    for key in REQUIRED_STATED_FIELDS:
        if key == "starting_cash_eur" and not require_starting_cash:
            continue
        if out.get(key) is None or out.get(key) == "":
            raise MissingRequiredParameterError(key)

    drawn = draw_assumed_defaults(
        industry=industry,
        company_size=company_size,
        seed=seed,
        description=description,
    )

    # Work order B / Run #19: drop incomplete one-offs before assuming scalars so a
    # complete CAPEX event can populate special_investment_* as stated.
    cleaned_events, drop_changes = drop_incomplete_one_off_events(out.get("one_off_events"))
    out["one_off_events"] = cleaned_events
    changes.extend(drop_changes)
    if not cleaned_events:
        sources.setdefault("one_off_events", "assumed")
    else:
        sources.setdefault("one_off_events", "stated")
        if out.get("special_investment_eur") in (None, "", 0, 0.0):
            for ev in cleaned_events:
                direction = str(ev.get("direction") or "out").lower()
                if direction in {"out", "outflow"} and ev.get("amount_eur"):
                    out["special_investment_eur"] = float(ev["amount_eur"])
                    out["special_investment_month"] = int(ev.get("month_index") or 2)
                    sources["special_investment_eur"] = "stated"
                    sources["special_investment_month"] = "stated"
                    break

    for key in _ASSUMABLE_SCALARS:
        if out.get(key) is None or out.get(key) == "":
            fill = drawn.get(key)
            if fill is None:
                continue
            out[key] = fill
            sources[key] = "assumed"
            changes.append(
                {
                    "field": key,
                    "original": None,
                    "clipped": fill,
                    "message": f"assumed {key}={fill} from industry×size range table",
                    "source": "assume",
                }
            )
        else:
            sources.setdefault(key, "stated")

    # starting_cash: if allowed to assume (hand-authored / tests)
    if (out.get("starting_cash_eur") is None or out.get("starting_cash_eur") == "") and not require_starting_cash:
        fill = drawn["starting_cash_eur"]
        out["starting_cash_eur"] = fill
        sources["starting_cash_eur"] = "assumed"
        changes.append(
            {
                "field": "starting_cash_eur",
                "original": None,
                "clipped": fill,
                "message": f"assumed starting_cash_eur={fill} from industry×size range table",
                "source": "assume",
            }
        )
    elif out.get("starting_cash_eur") is not None:
        sources.setdefault("starting_cash_eur", "stated")

    shares_raw = out.get("cost_shares_of_revenue")
    shares = shares_raw
    # Treat all-null share objects as missing (Ollama often returns keys with nulls).
    if isinstance(shares, dict) and shares and all(
        shares.get(sk) is None for sk in ("materials", "services", "personnel", "other")
    ):
        shares = None
    if not isinstance(shares, dict) or not shares:
        out["cost_shares_of_revenue"] = drawn["cost_shares_of_revenue"]
        sources["cost_shares_of_revenue"] = "assumed"
        for sk in ("materials", "services", "personnel", "other"):
            sources[f"cost_shares_of_revenue.{sk}"] = "assumed"
        changes.append(
            {
                "field": "cost_shares_of_revenue",
                "original": shares_raw,
                "clipped": drawn["cost_shares_of_revenue"],
                "message": "assumed cost_shares_of_revenue from industry×size range table",
                "source": "assume",
            }
        )
    else:
        fixed = dict(shares)
        drawn_shares = drawn["cost_shares_of_revenue"]
        for sk in ("materials", "services", "personnel", "other"):
            if sk not in fixed or fixed[sk] is None:
                fixed[sk] = drawn_shares[sk]
                sources[f"cost_shares_of_revenue.{sk}"] = "assumed"
                changes.append(
                    {
                        "field": f"cost_shares_of_revenue.{sk}",
                        "original": None,
                        "clipped": drawn_shares[sk],
                        "message": f"assumed cost share {sk}",
                        "source": "assume",
                    }
                )
            else:
                sources.setdefault(f"cost_shares_of_revenue.{sk}", "stated")
        out["cost_shares_of_revenue"] = fixed
        if all(
            sources.get(f"cost_shares_of_revenue.{sk}") == "assumed"
            for sk in ("materials", "services", "personnel", "other")
        ):
            sources["cost_shares_of_revenue"] = "assumed"
        else:
            sources.setdefault("cost_shares_of_revenue", "stated")

    if out.get("partly_fixed_costs") is None:
        out["partly_fixed_costs"] = False
        sources["partly_fixed_costs"] = "assumed"
        changes.append(
            {
                "field": "partly_fixed_costs",
                "original": None,
                "clipped": False,
                "message": "assumed partly_fixed_costs=false",
                "source": "assume",
            }
        )
    else:
        sources.setdefault("partly_fixed_costs", "stated")

    if out.get("special_investment_month") is None:
        out["special_investment_month"] = 2
        sources["special_investment_month"] = "assumed"

    out["field_sources"] = sources
    out["_assume_meta"] = {
        "industry_key": drawn.get("industry_key"),
        "size_band": drawn.get("size_band"),
        "seed": seed,
    }
    return out, changes
