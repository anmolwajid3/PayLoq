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

    shares = out.get("cost_shares_of_revenue")
    if not isinstance(shares, dict) or not shares:
        out["cost_shares_of_revenue"] = drawn["cost_shares_of_revenue"]
        sources["cost_shares_of_revenue"] = "assumed"
        changes.append(
            {
                "field": "cost_shares_of_revenue",
                "original": shares,
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

    if out.get("one_off_events") is None:
        out["one_off_events"] = []
        sources.setdefault("one_off_events", "assumed")
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
