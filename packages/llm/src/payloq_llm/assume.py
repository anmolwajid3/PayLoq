"""Fill unstated parameters from industry×size + scenario_shape ranges (pilot §D).

LLM extract returns nulls for unstated fields; this code draws defaults with a
fixed seed and marks ``source: assumed``. Starting cash is never a fail reason.
"""

from __future__ import annotations

from typing import Any

from payloq_schemas.industry_defaults import calibrate_cost_shares_for_shape, draw_assumed_defaults
from payloq_schemas.scenario_shape_ranges import overlay_shape_on_drawn


class MissingRequiredParameterError(ValueError):
    """Deprecated — kept for older tests; no longer raised on the generate path."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"Missing required parameter: {field}")


_ASSUMABLE_SCALARS: tuple[str, ...] = (
    "monthly_revenue_start_eur",
    "monthly_revenue_growth",
    "days_sales_outstanding",
    "days_payables_outstanding",
    "target_cash_at_end_eur",
    "covenant_min_cash_eur",
    "starting_cash_eur",
    "special_investment_eur",
    "special_investment_month",
)


def drop_incomplete_one_off_events(
    events: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep only one-off events that have amount, month_index, and direction."""
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
        if event_type in {"capex", "capital_expenditure", "investment"} and (
            direction is None or direction == ""
        ):
            direction = "outflow"
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
            direction_s = "inflow"
        elif direction_s in {"outflow", "out"}:
            direction_s = "outflow"
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
            direction_s = "outflow"
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
    require_starting_cash: bool = False,
    scenario_shape: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Merge stated extraction with assumed draws.

    - Stated (non-null) values keep ``source: stated``.
    - Null assumable fields are filled from industry×size + scenario_shape tables.
    - ``starting_cash_eur`` is always assumed when null (never a fail reason).
    - ``require_starting_cash`` is ignored (kept for call-site compatibility).
    """
    _ = require_starting_cash  # removed by pilot fix §D / §G
    out = dict(extracted or {})
    changes: list[dict[str, Any]] = []
    sources: dict[str, str] = dict(out.get("field_sources") or {})
    shape = scenario_shape or out.get("scenario_shape")

    # Do NOT copy covenant → target_cash. A stated covenant must not force
    # target_cash equal to it; target is assumed independently when unstated.
    if out.get("covenant_min_cash_eur") is None and out.get("target_cash_at_end_eur") is not None:
        out["covenant_min_cash_eur"] = out["target_cash_at_end_eur"]
        sources.setdefault(
            "covenant_min_cash_eur", sources.get("target_cash_at_end_eur", "stated")
        )

    drawn = draw_assumed_defaults(
        industry=industry,
        company_size=company_size,
        seed=seed,
        description=description,
    )
    drawn = overlay_shape_on_drawn(drawn, scenario_shape=shape, seed=seed)

    cleaned_events, drop_changes = drop_incomplete_one_off_events(out.get("one_off_events"))
    out["one_off_events"] = cleaned_events
    changes.extend(drop_changes)
    if not cleaned_events:
        sources.setdefault("one_off_events", "assumed")
    else:
        sources.setdefault("one_off_events", "stated")
        if out.get("special_investment_eur") in (None, "", 0, 0.0):
            for ev in cleaned_events:
                direction = str(ev.get("direction") or "outflow").lower()
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
                    "message": (
                        f"assumed {key}={fill} from industry×size / "
                        f"scenario_shape={shape or 'unspecified'} range table"
                    ),
                    "source": "assume",
                }
            )
        else:
            sources.setdefault(key, "stated")

    # After assumes: fill missing covenant from target only (not the reverse).
    if out.get("covenant_min_cash_eur") is None and out.get("target_cash_at_end_eur") is not None:
        out["covenant_min_cash_eur"] = out["target_cash_at_end_eur"]
        sources.setdefault(
            "covenant_min_cash_eur", sources.get("target_cash_at_end_eur", "assumed")
        )

    shares_raw = out.get("cost_shares_of_revenue")
    shares = shares_raw
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

    # Assumed growth is drawn as a fraction. The schema field is the percent figure.
    if (
        sources.get("monthly_revenue_growth") == "assumed"
        and out.get("growth_per_month_percent") in (None, "")
        and out.get("monthly_revenue_growth") is not None
    ):
        out["growth_per_month_percent"] = round(float(out["monthly_revenue_growth"]) * 100.0, 10)
        sources["growth_per_month_percent"] = "assumed"

    if out.get("partly_fixed_costs") is None:
        out["partly_fixed_costs"] = shape in {"weak", "cash_tight", "cash_critical"}
        sources["partly_fixed_costs"] = "assumed"
        changes.append(
            {
                "field": "partly_fixed_costs",
                "original": None,
                "clipped": out["partly_fixed_costs"],
                "message": f"assumed partly_fixed_costs={out['partly_fixed_costs']}",
                "source": "assume",
            }
        )
    else:
        sources.setdefault("partly_fixed_costs", "stated")

    if out.get("special_investment_month") is None:
        out["special_investment_month"] = 2
        sources["special_investment_month"] = "assumed"

    if out.get("special_investment_eur") is None:
        out["special_investment_eur"] = 0.0
        sources.setdefault("special_investment_eur", "assumed")

    out["scenario_shape"] = shape or "unspecified"
    # Stable key order so input.json hashes do not depend on insertion path.
    out["field_sources"] = dict(sorted((str(k), v) for k, v in sources.items()))
    if (
        sources.get("cost_shares_of_revenue") == "assumed"
        and isinstance(out.get("cost_shares_of_revenue"), dict)
        and out.get("monthly_revenue_start_eur") is not None
    ):
        out["cost_shares_of_revenue"] = calibrate_cost_shares_for_shape(
            out["cost_shares_of_revenue"],
            start_revenue_eur=float(out["monthly_revenue_start_eur"]),
            scenario_shape=shape,
        )
    shares_out = out.get("cost_shares_of_revenue")
    if isinstance(shares_out, dict):
        out["cost_shares_of_revenue"] = {
            k: shares_out[k]
            for k in ("materials", "services", "personnel", "other")
            if k in shares_out
        }
        for k, v in shares_out.items():
            if k not in out["cost_shares_of_revenue"]:
                out["cost_shares_of_revenue"][k] = v
    out["_assume_meta"] = {
        "industry_key": drawn.get("industry_key"),
        "size_band": drawn.get("size_band"),
        "seed": seed,
        "scenario_shape": out["scenario_shape"],
    }
    return out, changes
