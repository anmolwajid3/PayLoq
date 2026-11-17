"""Clamp LLM parameters to allowed ranges (FR-A-11) and log changes."""

from __future__ import annotations

from typing import Any

from payloq_schemas.constants import PARAM_RANGES
from payloq_schemas.models import ParametersFromLanguageModel


def clamp_parameters(
    params: ParametersFromLanguageModel | dict[str, Any],
) -> tuple[ParametersFromLanguageModel, list[dict[str, Any]]]:
    """
    Clip numeric fields to PARAM_RANGES.

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

    # Cost shares: clamp each to [0, 1]
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
        data["cost_shares_of_revenue"] = shares

    return ParametersFromLanguageModel.model_validate(data), changes
