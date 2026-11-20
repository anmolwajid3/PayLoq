"""Pre-generation parameter consistency checks (work order B).

Reject parameters when cost shares + profit margin ≥ 100%, growth is not a
fraction-scale value, or starting cash is non-positive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from payloq_schemas.models import OneOffCashEvent, ParametersFromLanguageModel


@dataclass
class ConsistencyIssue:
    code: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass
class ConsistencyResult:
    ok: bool
    issues: list[ConsistencyIssue] = field(default_factory=list)

    def error_text(self) -> str:
        return "; ".join(f"{i.code}: {i.message}" for i in self.issues)


class ParameterConsistencyError(ValueError):
    def __init__(self, result: ConsistencyResult) -> None:
        self.result = result
        super().__init__(result.error_text())


def check_parameters_consistency(
    params: ParametersFromLanguageModel | dict[str, Any],
    *,
    profit_margin_hint: float | None = None,
) -> ConsistencyResult:
    """
    Validate parameters before generation.

    Cost shares + implied profit margin must be < 100%. Growth must look like a
    MoM fraction (|g| ≤ 0.5). Starting cash, when set, must be positive.
    One-off events must have month_index and direction; CAPEX is outflow.
    """
    if isinstance(params, ParametersFromLanguageModel):
        data = params.model_dump()
        model = params
    else:
        data = dict(params)
        model = None

    issues: list[ConsistencyIssue] = []

    shares = data.get("cost_shares_of_revenue") or {}
    if isinstance(shares, dict):
        share_sum = sum(
            float(shares.get(k) or 0.0) for k in ("materials", "services", "personnel", "other")
        )
    else:
        share_sum = 0.0
        issues.append(
            ConsistencyIssue(
                code="cost_shares_invalid",
                message="cost_shares_of_revenue must be an object",
                field="cost_shares_of_revenue",
            )
        )

    # Cost shares must leave room for profit (shares + margin < 100%).
    # Default implied margin is the residual below 1.0; an explicit hint overrides.
    if profit_margin_hint is not None:
        combined = share_sum + float(profit_margin_hint)
    else:
        # Residual margin = max(0, 1 - share_sum); require share_sum strictly < 1.
        combined = share_sum + max(0.0, 1.0 - share_sum) if share_sum >= 1.0 else share_sum
    if share_sum >= 1.0 - 1e-9 or combined >= 1.0 - 1e-9 and profit_margin_hint is not None:
        issues.append(
            ConsistencyIssue(
                code="cost_shares_plus_margin",
                message=(
                    f"cost shares sum {share_sum:.4f}"
                    + (
                        f" + profit margin {profit_margin_hint:.4f} = {combined:.4f}"
                        if profit_margin_hint is not None
                        else ""
                    )
                    + " must be below 100%"
                ),
                field="cost_shares_of_revenue",
            )
        )

    try:
        growth = float(data.get("monthly_revenue_growth"))
    except (TypeError, ValueError):
        growth = None
        issues.append(
            ConsistencyIssue(
                code="growth_not_fraction",
                message="monthly_revenue_growth / growth_per_month_fraction is required",
                field="monthly_revenue_growth",
            )
        )
    if growth is not None:
        # Reject percent-scale mistakes like 0.8 meaning 80%/mo or 3 meaning 300%.
        if abs(growth) > 0.5:
            issues.append(
                ConsistencyIssue(
                    code="growth_not_fraction",
                    message=(
                        f"growth {growth} is not a MoM fraction "
                        "(expected e.g. 0.003 for 0.3%/month, |g|≤0.5)"
                    ),
                    field="monthly_revenue_growth",
                )
            )

    starting = data.get("starting_cash_eur")
    if starting is not None and starting != "":
        try:
            cash0 = float(starting)
        except (TypeError, ValueError):
            cash0 = None
            issues.append(
                ConsistencyIssue(
                    code="starting_cash_invalid",
                    message="starting_cash_eur must be a number",
                    field="starting_cash_eur",
                )
            )
        if cash0 is not None and cash0 <= 0:
            issues.append(
                ConsistencyIssue(
                    code="starting_cash_non_positive",
                    message=f"starting_cash_eur must be positive (got {cash0})",
                    field="starting_cash_eur",
                )
            )

    events = data.get("one_off_events") or []
    if isinstance(events, list):
        for i, ev in enumerate(events):
            try:
                if model is not None and i < len(model.one_off_events):
                    OneOffCashEvent.model_validate(model.one_off_events[i].model_dump())
                elif isinstance(ev, dict):
                    OneOffCashEvent.model_validate(ev)
                else:
                    raise ValueError("event must be an object")
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    ConsistencyIssue(
                        code="one_off_event_invalid",
                        message=f"one_off_events[{i}] rejected: {exc}",
                        field=f"one_off_events[{i}]",
                    )
                )
                continue
            if isinstance(ev, dict):
                if ev.get("month_index") is None:
                    issues.append(
                        ConsistencyIssue(
                            code="one_off_missing_month",
                            message=f"one_off_events[{i}] missing month_index",
                            field=f"one_off_events[{i}].month_index",
                        )
                    )
                if ev.get("direction") is None:
                    issues.append(
                        ConsistencyIssue(
                            code="one_off_missing_direction",
                            message=f"one_off_events[{i}] missing direction",
                            field=f"one_off_events[{i}].direction",
                        )
                    )

    return ConsistencyResult(ok=not issues, issues=issues)


def require_consistent(params: ParametersFromLanguageModel | dict[str, Any]) -> None:
    result = check_parameters_consistency(params)
    if not result.ok:
        raise ParameterConsistencyError(result)
