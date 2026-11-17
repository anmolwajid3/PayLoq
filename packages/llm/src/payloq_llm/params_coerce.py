"""Coerce / repair incomplete LLM JSON into ParametersFromLanguageModel shape.

Weak local models (e.g. llama3.2:1b) often omit required fields or return
absolute euro seasonality levels instead of 12 multiplicative factors.
Repair when possible instead of hard-failing into the stub adapter.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from payloq_schemas.constants import (
    COST_SHARE_SUM_TARGET,
    REVENUE_FACTOR_MAX,
    REVENUE_FACTOR_MIN,
)

from payloq_llm.nl_cash_intent import (
    looks_cash_critical,
    repair_params_from_nl,
    suggested_target_cash_eur,
)
from payloq_llm.nl_param_hints import (
    repair_investment_and_revenue_from_nl,
    suggest_revenue_start_eur,
)

DEFAULT_COST_SHARES: dict[str, float] = {
    "materials": 0.37,
    "services": 0.08,
    "personnel": 0.34,
    "other": 0.15,
}

# Prefer ~0.94 sum (DEFAULT_COST_SHARES already does).
assert abs(sum(DEFAULT_COST_SHARES.values()) - COST_SHARE_SUM_TARGET) < 0.02


def normalize_monthly_revenue_factors(
    raw: Any,
    *,
    start_eur: float | None = None,
) -> tuple[list[float] | None, list[dict[str, Any]]]:
    """
    Coerce model seasonality into exactly 12 Jan–Dec multiplicative factors.

    - Wrong length → pad/trim when ≥6 values; else drop (None → seasonality defaults).
    - Absolute euro levels (median/max ≫ factor range) → divide by median (or start_eur).
    - Clip each factor into [REVENUE_FACTOR_MIN, REVENUE_FACTOR_MAX].
    """
    changes: list[dict[str, Any]] = []
    if raw is None:
        return None, changes
    try:
        vals = [float(x) for x in list(raw)]
    except (TypeError, ValueError):
        changes.append(
            {
                "field": "monthly_revenue_factors",
                "message": "dropped unparseable monthly_revenue_factors",
                "source": "params_coerce",
            }
        )
        return None, changes
    if not vals:
        return None, changes

    original_len = len(vals)
    if len(vals) < 6:
        changes.append(
            {
                "field": "monthly_revenue_factors",
                "message": (
                    f"dropped monthly_revenue_factors (had {original_len} values; "
                    "need ~12 multipliers)"
                ),
                "source": "params_coerce",
            }
        )
        return None, changes
    if len(vals) < 12:
        vals = vals + [1.0] * (12 - len(vals))
        changes.append(
            {
                "field": "monthly_revenue_factors",
                "message": f"padded monthly_revenue_factors to 12 (had {original_len})",
                "source": "params_coerce",
            }
        )
    elif len(vals) > 12:
        vals = vals[:12]
        changes.append(
            {
                "field": "monthly_revenue_factors",
                "message": f"truncated monthly_revenue_factors to 12 (had {original_len})",
                "source": "params_coerce",
            }
        )

    med = float(median(vals))
    mx = max(vals)
    # Absolute euro levels: e.g. [12000, 10000, …] instead of multipliers
    looks_absolute = med > REVENUE_FACTOR_MAX or mx > REVENUE_FACTOR_MAX * 1.5
    if looks_absolute:
        base = med if med > 0 else (float(start_eur) if start_eur and start_eur > 0 else 1.0)
        if base <= 0:
            base = 1.0
        converted = [v / base for v in vals]
        # Re-center mean near 1.0 when all months are similar euro levels
        mean_c = sum(converted) / 12.0
        if mean_c > 0 and (mean_c < 0.4 or mean_c > 2.5):
            converted = [v / mean_c for v in converted]
        changes.append(
            {
                "field": "monthly_revenue_factors",
                "original": list(vals),
                "clipped": None,  # filled after clip
                "message": (
                    "monthly_revenue_factors looked like euro levels; "
                    f"normalized by {base:.2f} into multiplicative factors"
                ),
                "source": "params_coerce",
            }
        )
        vals = converted

    clipped: list[float] = []
    for i, fv in enumerate(vals):
        cf = min(REVENUE_FACTOR_MAX, max(REVENUE_FACTOR_MIN, float(fv)))
        if abs(cf - fv) > 1e-9:
            changes.append(
                {
                    "field": f"monthly_revenue_factors[{i}]",
                    "original": fv,
                    "clipped": cf,
                    "range": [REVENUE_FACTOR_MIN, REVENUE_FACTOR_MAX],
                    "message": f"monthly_revenue_factors[{i}] clipped from {fv} to {cf}",
                    "source": "params_coerce",
                }
            )
        clipped.append(round(cf, 6))

    # Update the euro-level change record with final clipped list
    for ch in changes:
        if ch.get("field") == "monthly_revenue_factors" and "euro levels" in str(
            ch.get("message")
        ):
            ch["clipped"] = list(clipped)

    return clipped, changes


def _fill_missing_scalar(
    data: dict[str, Any],
    field: str,
    value: Any,
    changes: list[dict[str, Any]],
    *,
    message: str,
) -> None:
    if data.get(field) is None or data.get(field) == "":
        data[field] = value
        changes.append(
            {
                "field": field,
                "original": None,
                "clipped": value,
                "message": message,
                "source": "params_coerce",
            }
        )


def coerce_parameters_dict(
    data: dict[str, Any],
    description: str,
    *,
    options: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Soft-repair incomplete / malformed LLM parameter JSON before Pydantic validate.

    Fills missing required fields from NL hints or safe industry defaults, and
    normalizes monthly_revenue_factors to 12 multipliers (or drops them).
    """
    out = dict(data or {})
    changes: list[dict[str, Any]] = []
    opts = options or {}
    industry = str(opts.get("industry") or "")
    company_size = str(opts.get("company_size") or "")
    blob = description or ""

    # --- cost shares ---
    shares = out.get("cost_shares_of_revenue")
    if not isinstance(shares, dict) or not shares:
        out["cost_shares_of_revenue"] = dict(DEFAULT_COST_SHARES)
        changes.append(
            {
                "field": "cost_shares_of_revenue",
                "original": shares,
                "clipped": dict(DEFAULT_COST_SHARES),
                "message": "filled missing cost_shares_of_revenue with defaults",
                "source": "params_coerce",
            }
        )
    else:
        fixed = dict(shares)
        for k, v in DEFAULT_COST_SHARES.items():
            if k not in fixed or fixed[k] is None:
                fixed[k] = v
                changes.append(
                    {
                        "field": f"cost_shares_of_revenue.{k}",
                        "original": None,
                        "clipped": v,
                        "message": f"filled missing cost share {k}",
                        "source": "params_coerce",
                    }
                )
        out["cost_shares_of_revenue"] = fixed

    # --- revenue start ---
    if out.get("monthly_revenue_start_eur") in (None, ""):
        suggested = suggest_revenue_start_eur(
            blob, industry=industry, company_size=company_size
        )
        fill = float(suggested) if suggested is not None else 80_000.0
        _fill_missing_scalar(
            out,
            "monthly_revenue_start_eur",
            fill,
            changes,
            message=(
                f"filled missing monthly_revenue_start_eur with {fill} "
                "(NL/industry default)"
            ),
        )

    # --- growth ---
    if out.get("monthly_revenue_growth") in (None, ""):
        growth = 0.0 if looks_cash_critical(blob) else 0.0
        _fill_missing_scalar(
            out,
            "monthly_revenue_growth",
            growth,
            changes,
            message=f"filled missing monthly_revenue_growth with {growth}",
        )

    # --- DSO / DPO ---
    _fill_missing_scalar(
        out,
        "days_sales_outstanding",
        40.0,
        changes,
        message="filled missing days_sales_outstanding with 40",
    )
    _fill_missing_scalar(
        out,
        "days_payables_outstanding",
        32.0,
        changes,
        message="filled missing days_payables_outstanding with 32",
    )

    # --- target cash ---
    if out.get("target_cash_at_end_eur") in (None, ""):
        cash = suggested_target_cash_eur(blob)
        if cash is None:
            cash = 45_000.0 if looks_cash_critical(blob) else 120_000.0
        _fill_missing_scalar(
            out,
            "target_cash_at_end_eur",
            float(cash),
            changes,
            message=f"filled missing target_cash_at_end_eur with {cash}",
        )

    # --- optional investment defaults ---
    if "special_investment_eur" not in out or out.get("special_investment_eur") is None:
        out["special_investment_eur"] = 0.0
    if "special_investment_month" not in out or out.get("special_investment_month") is None:
        out["special_investment_month"] = 2
    if "one_off_events" not in out or out.get("one_off_events") is None:
        out["one_off_events"] = []
    if "partly_fixed_costs" not in out or out.get("partly_fixed_costs") is None:
        out["partly_fixed_costs"] = bool(looks_cash_critical(blob))

    # --- factors ---
    try:
        start_eur = float(out.get("monthly_revenue_start_eur") or 0) or None
    except (TypeError, ValueError):
        start_eur = None
    if "monthly_revenue_factors" in out:
        factors, fchg = normalize_monthly_revenue_factors(
            out.get("monthly_revenue_factors"), start_eur=start_eur
        )
        changes.extend(fchg)
        out["monthly_revenue_factors"] = factors

    # NL soft repairs (cash + investment/revenue scale)
    out, cash_chg = repair_params_from_nl(blob, out)
    changes.extend(cash_chg)
    out, inv_chg = repair_investment_and_revenue_from_nl(
        blob, out, industry=industry, company_size=company_size
    )
    changes.extend(inv_chg)

    return out, changes
