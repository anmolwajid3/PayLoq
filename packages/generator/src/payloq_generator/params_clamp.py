"""Clamp LLM parameters to allowed ranges (FR-A-11) and log changes."""

from __future__ import annotations

from typing import Any

from payloq_schemas.constants import (
    COST_SHARE_SUM_MAX,
    COST_SHARE_SUM_MIN,
    COST_SHARE_SUM_TARGET,
    PARAM_RANGES,
    REVENUE_FACTOR_MAX,
    REVENUE_FACTOR_MIN,
)
from payloq_schemas.models import ParametersFromLanguageModel


def cost_share_sum(shares: dict[str, Any] | None) -> float:
    if not isinstance(shares, dict):
        return 0.0
    return sum(float(shares.get(k) or 0.0) for k in ("materials", "services", "personnel", "other"))


def cost_shares_out_of_range(shares: dict[str, Any] | None) -> bool:
    s = cost_share_sum(shares)
    return s < COST_SHARE_SUM_MIN - 1e-9 or s > COST_SHARE_SUM_MAX + 1e-9


def clamp_parameters(
    params: ParametersFromLanguageModel | dict[str, Any],
) -> tuple[ParametersFromLanguageModel, list[dict[str, Any]]]:
    """
    Clip numeric fields to PARAM_RANGES and hard-repair cost-share sums (FR-A-11).

    Cost shares: each clipped to [0, 1]; if sum is outside ~0.9–1.0, scale to
    COST_SHARE_SUM_TARGET and log. Soft warning alone is not enough — this is blocking.

    Returns (clamped_model, list of change records for run_log).
    """
    if isinstance(params, ParametersFromLanguageModel):
        data = params.model_dump()
    else:
        data = dict(params)

    changes: list[dict[str, Any]] = []
    for key, (lo, hi) in PARAM_RANGES.items():
        if key not in data or data[key] is None:
            continue
        try:
            val = float(data[key])
        except (TypeError, ValueError):
            continue
        clipped = min(hi, max(lo, val))
        if clipped != val:
            changes.append(
                {
                    "field": key,
                    "original": val,
                    "clipped": clipped,
                    "range": [lo, hi],
                    "message": f"{key} clipped from {val} to {clipped} (allowed {lo}..{hi})",
                }
            )
            data[key] = clipped

    # Cost shares: clamp each to [0, 1], then enforce sum ∈ [0.9, 1.0]
    shares = data.get("cost_shares_of_revenue") or {}
    if isinstance(shares, dict):
        for sk in ("materials", "services", "personnel", "other"):
            if sk not in shares:
                continue
            try:
                sv = float(shares[sk])
            except (TypeError, ValueError):
                continue
            clipped = min(1.0, max(0.0, sv))
            if clipped != sv:
                changes.append(
                    {
                        "field": f"cost_shares_of_revenue.{sk}",
                        "original": sv,
                        "clipped": clipped,
                        "range": [0.0, 1.0],
                        "message": f"cost share {sk} clipped from {sv} to {clipped}",
                    }
                )
                shares[sk] = clipped

        share_sum = cost_share_sum(shares)
        if share_sum <= 0:
            # Degenerate → equal-ish default that sums to target
            equal = COST_SHARE_SUM_TARGET / 4.0
            before = dict(shares)
            shares = {
                "materials": equal,
                "services": equal,
                "personnel": equal,
                "other": equal,
            }
            changes.append(
                {
                    "field": "cost_shares_of_revenue",
                    "original": before,
                    "clipped": dict(shares),
                    "original_sum": share_sum,
                    "clipped_sum": COST_SHARE_SUM_TARGET,
                    "message": (
                        f"cost shares sum {share_sum:.4f} was non-positive; "
                        f"reset to equal shares summing to {COST_SHARE_SUM_TARGET}"
                    ),
                }
            )
        elif share_sum < COST_SHARE_SUM_MIN or share_sum > COST_SHARE_SUM_MAX:
            # Prefer nearest edge of allowed band, else target when far outside.
            if COST_SHARE_SUM_MIN <= share_sum <= COST_SHARE_SUM_MAX:
                target = share_sum
            elif share_sum < COST_SHARE_SUM_MIN:
                target = COST_SHARE_SUM_MIN
            elif share_sum <= COST_SHARE_SUM_MAX + 0.15:
                # Mild overshoot → clip to max
                target = COST_SHARE_SUM_MAX
            else:
                # Wild sum (e.g. 1.90) → normalize to target mid-band
                target = COST_SHARE_SUM_TARGET
            scale = target / share_sum
            before = {k: float(shares.get(k) or 0.0) for k in ("materials", "services", "personnel", "other")}
            for sk in ("materials", "services", "personnel", "other"):
                shares[sk] = round(float(shares.get(sk) or 0.0) * scale, 6)
            # Fix residual on "other"
            new_sum = cost_share_sum(shares)
            shares["other"] = round(float(shares["other"]) + (target - new_sum), 6)
            shares["other"] = min(1.0, max(0.0, float(shares["other"])))
            changes.append(
                {
                    "field": "cost_shares_of_revenue",
                    "original": before,
                    "clipped": {
                        k: float(shares[k]) for k in ("materials", "services", "personnel", "other")
                    },
                    "original_sum": share_sum,
                    "clipped_sum": cost_share_sum(shares),
                    "message": (
                        f"cost shares sum {share_sum:.4f} outside "
                        f"{COST_SHARE_SUM_MIN}..{COST_SHARE_SUM_MAX}; "
                        f"scaled to {cost_share_sum(shares):.4f} (FR-A-11 blocking repair)"
                    ),
                }
            )
        data["cost_shares_of_revenue"] = shares

    # Seasonality factors: normalize euro levels / pad/trim to 12, clip each
    factors = data.get("monthly_revenue_factors")
    if factors is not None:
        try:
            from payloq_llm.params_coerce import normalize_monthly_revenue_factors

            try:
                start_eur = float(data.get("monthly_revenue_start_eur") or 0) or None
            except (TypeError, ValueError):
                start_eur = None
            normalized, fchg = normalize_monthly_revenue_factors(
                factors, start_eur=start_eur
            )
            changes.extend(fchg)
            data["monthly_revenue_factors"] = normalized
        except Exception:  # noqa: BLE001 — keep local pad/clip if llm package unavailable
            try:
                raw = [float(x) for x in list(factors)]
            except (TypeError, ValueError):
                raw = [1.0] * 12
            if len(raw) < 12:
                raw = raw + [1.0] * (12 - len(raw))
                changes.append(
                    {
                        "field": "monthly_revenue_factors",
                        "message": f"padded monthly_revenue_factors to 12 entries (had {len(factors)})",
                    }
                )
            elif len(raw) > 12:
                raw = raw[:12]
                changes.append(
                    {
                        "field": "monthly_revenue_factors",
                        "message": f"truncated monthly_revenue_factors to 12 entries (had {len(factors)})",
                    }
                )
            clipped_factors: list[float] = []
            for i, fv in enumerate(raw):
                cf = min(REVENUE_FACTOR_MAX, max(REVENUE_FACTOR_MIN, fv))
                if cf != fv:
                    changes.append(
                        {
                            "field": f"monthly_revenue_factors[{i}]",
                            "original": fv,
                            "clipped": cf,
                            "range": [REVENUE_FACTOR_MIN, REVENUE_FACTOR_MAX],
                            "message": f"monthly_revenue_factors[{i}] clipped from {fv} to {cf}",
                        }
                    )
                clipped_factors.append(cf)
            data["monthly_revenue_factors"] = clipped_factors

    # special_investment_month
    try:
        mi = int(data.get("special_investment_month") or 2)
    except (TypeError, ValueError):
        mi = 2
    clipped_mi = min(24, max(1, mi))
    if clipped_mi != mi:
        changes.append(
            {
                "field": "special_investment_month",
                "original": mi,
                "clipped": clipped_mi,
                "message": f"special_investment_month clipped from {mi} to {clipped_mi}",
            }
        )
    data["special_investment_month"] = clipped_mi

    # one_off_events: drop invalid rows softly
    events = data.get("one_off_events") or []
    if isinstance(events, list):
        cleaned = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            try:
                amt = float(ev.get("amount_eur") or 0)
                month_i = int(ev.get("month_index") or 0)
            except (TypeError, ValueError):
                continue
            if amt <= 0 or month_i < 1:
                changes.append(
                    {
                        "field": "one_off_events",
                        "message": f"dropped invalid one_off_event: {ev!r}",
                    }
                )
                continue
            direction = str(ev.get("direction") or "out").lower()
            if direction not in {"in", "out"}:
                direction = "out"
            cleaned.append(
                {
                    "amount_eur": amt,
                    "month_index": min(24, max(1, month_i)),
                    "direction": direction,
                    "label": ev.get("label"),
                }
            )
        data["one_off_events"] = cleaned

    return ParametersFromLanguageModel.model_validate(data), changes
