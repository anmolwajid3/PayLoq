"""Industry × company-size range tables for assumed parameters (work order B).

No company-specific heuristics — only generic industry keys and size bands.
Code draws unstated values with a fixed seed; every draw is ``source: assumed``.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any, Literal

from payloq_schemas.company_size import size_band
from payloq_schemas.constants import (
    COST_SHARE_SUM_MAX,
    COST_SHARE_SUM_MIN,
    COST_SHARE_SUM_TARGET,
    FIXED_DEPRECIATION_MONTHLY_EUR,
    HEALTHY_MIN_OPERATING_MARGIN,
    INTEREST_ANNUAL_RATE,
    LOAN_ANCHOR_EUR,
    LOSS_SHAPE_COST_SUM_TARGET,
)

IndustryKey = Literal[
    "manufacturing",
    "hospitality",
    "food_service",
    "retail",
    "professional_services",
    "other",
]
SizeBand = Literal["small", "medium", "large"]

# Inclusive ranges: (lo, hi) drawn uniformly with a seeded RNG.
# Revenue / cash are monthly EUR; growth is a MoM fraction; DSO/DPO in days.
_RANGE_TABLE: dict[IndustryKey, dict[SizeBand, dict[str, tuple[float, float]]]] = {
    "manufacturing": {
        "small": {
            "monthly_revenue_start_eur": (80_000.0, 250_000.0),
            "monthly_revenue_growth": (-0.005, 0.012),
            "days_sales_outstanding": (30.0, 50.0),
            "days_payables_outstanding": (25.0, 45.0),
            "starting_cash_eur": (80_000.0, 280_000.0),
            "target_cash_at_end_eur": (100_000.0, 350_000.0),
            "cost_materials": (0.30, 0.42),
            "cost_services": (0.05, 0.12),
            "cost_personnel": (0.28, 0.38),
            "cost_other": (0.10, 0.18),
        },
        "medium": {
            "monthly_revenue_start_eur": (250_000.0, 800_000.0),
            "monthly_revenue_growth": (-0.005, 0.012),
            "days_sales_outstanding": (32.0, 55.0),
            "days_payables_outstanding": (28.0, 48.0),
            "starting_cash_eur": (200_000.0, 700_000.0),
            "target_cash_at_end_eur": (250_000.0, 900_000.0),
            "cost_materials": (0.32, 0.44),
            "cost_services": (0.05, 0.12),
            "cost_personnel": (0.26, 0.36),
            "cost_other": (0.10, 0.16),
        },
        "large": {
            "monthly_revenue_start_eur": (800_000.0, 5_000_000.0),
            "monthly_revenue_growth": (-0.004, 0.010),
            "days_sales_outstanding": (35.0, 60.0),
            "days_payables_outstanding": (30.0, 55.0),
            "starting_cash_eur": (800_000.0, 4_000_000.0),
            "target_cash_at_end_eur": (1_000_000.0, 5_000_000.0),
            "cost_materials": (0.34, 0.46),
            "cost_services": (0.04, 0.10),
            "cost_personnel": (0.24, 0.34),
            "cost_other": (0.08, 0.15),
        },
    },
    "hospitality": {
        "small": {
            "monthly_revenue_start_eur": (60_000.0, 220_000.0),
            "monthly_revenue_growth": (-0.008, 0.010),
            "days_sales_outstanding": (14.0, 35.0),
            "days_payables_outstanding": (20.0, 40.0),
            "starting_cash_eur": (40_000.0, 200_000.0),
            "target_cash_at_end_eur": (50_000.0, 250_000.0),
            "cost_materials": (0.18, 0.30),
            "cost_services": (0.08, 0.16),
            "cost_personnel": (0.30, 0.42),
            "cost_other": (0.12, 0.22),
        },
        "medium": {
            "monthly_revenue_start_eur": (200_000.0, 600_000.0),
            "monthly_revenue_growth": (-0.006, 0.010),
            "days_sales_outstanding": (14.0, 40.0),
            "days_payables_outstanding": (22.0, 42.0),
            "starting_cash_eur": (120_000.0, 500_000.0),
            "target_cash_at_end_eur": (150_000.0, 600_000.0),
            "cost_materials": (0.18, 0.28),
            "cost_services": (0.08, 0.15),
            "cost_personnel": (0.30, 0.40),
            "cost_other": (0.12, 0.20),
        },
        "large": {
            "monthly_revenue_start_eur": (500_000.0, 2_500_000.0),
            "monthly_revenue_growth": (-0.005, 0.008),
            "days_sales_outstanding": (18.0, 45.0),
            "days_payables_outstanding": (25.0, 45.0),
            "starting_cash_eur": (400_000.0, 2_000_000.0),
            "target_cash_at_end_eur": (500_000.0, 2_500_000.0),
            "cost_materials": (0.16, 0.28),
            "cost_services": (0.08, 0.14),
            "cost_personnel": (0.28, 0.38),
            "cost_other": (0.12, 0.20),
        },
    },
    "food_service": {
        "small": {
            "monthly_revenue_start_eur": (25_000.0, 80_000.0),
            "monthly_revenue_growth": (-0.006, 0.010),
            "days_sales_outstanding": (14.0, 35.0),
            "days_payables_outstanding": (20.0, 40.0),
            "starting_cash_eur": (20_000.0, 90_000.0),
            "target_cash_at_end_eur": (25_000.0, 100_000.0),
            "cost_materials": (0.28, 0.40),
            "cost_services": (0.05, 0.12),
            "cost_personnel": (0.30, 0.42),
            "cost_other": (0.10, 0.18),
        },
        "medium": {
            "monthly_revenue_start_eur": (70_000.0, 220_000.0),
            "monthly_revenue_growth": (-0.005, 0.010),
            "days_sales_outstanding": (16.0, 38.0),
            "days_payables_outstanding": (22.0, 42.0),
            "starting_cash_eur": (50_000.0, 200_000.0),
            "target_cash_at_end_eur": (60_000.0, 220_000.0),
            "cost_materials": (0.28, 0.38),
            "cost_services": (0.05, 0.12),
            "cost_personnel": (0.30, 0.40),
            "cost_other": (0.10, 0.16),
        },
        "large": {
            "monthly_revenue_start_eur": (200_000.0, 800_000.0),
            "monthly_revenue_growth": (-0.004, 0.008),
            "days_sales_outstanding": (18.0, 40.0),
            "days_payables_outstanding": (24.0, 45.0),
            "starting_cash_eur": (150_000.0, 600_000.0),
            "target_cash_at_end_eur": (180_000.0, 700_000.0),
            "cost_materials": (0.26, 0.38),
            "cost_services": (0.05, 0.12),
            "cost_personnel": (0.28, 0.38),
            "cost_other": (0.10, 0.16),
        },
    },
    "retail": {
        "small": {
            "monthly_revenue_start_eur": (40_000.0, 150_000.0),
            "monthly_revenue_growth": (-0.006, 0.012),
            "days_sales_outstanding": (14.0, 35.0),
            "days_payables_outstanding": (25.0, 45.0),
            "starting_cash_eur": (30_000.0, 140_000.0),
            "target_cash_at_end_eur": (40_000.0, 160_000.0),
            "cost_materials": (0.40, 0.55),
            "cost_services": (0.04, 0.10),
            "cost_personnel": (0.18, 0.30),
            "cost_other": (0.08, 0.16),
        },
        "medium": {
            "monthly_revenue_start_eur": (140_000.0, 450_000.0),
            "monthly_revenue_growth": (-0.005, 0.012),
            "days_sales_outstanding": (16.0, 40.0),
            "days_payables_outstanding": (28.0, 48.0),
            "starting_cash_eur": (100_000.0, 400_000.0),
            "target_cash_at_end_eur": (120_000.0, 450_000.0),
            "cost_materials": (0.40, 0.52),
            "cost_services": (0.04, 0.10),
            "cost_personnel": (0.18, 0.28),
            "cost_other": (0.08, 0.14),
        },
        "large": {
            "monthly_revenue_start_eur": (400_000.0, 2_000_000.0),
            "monthly_revenue_growth": (-0.004, 0.010),
            "days_sales_outstanding": (18.0, 42.0),
            "days_payables_outstanding": (30.0, 50.0),
            "starting_cash_eur": (300_000.0, 1_500_000.0),
            "target_cash_at_end_eur": (350_000.0, 1_800_000.0),
            "cost_materials": (0.38, 0.52),
            "cost_services": (0.04, 0.10),
            "cost_personnel": (0.16, 0.28),
            "cost_other": (0.08, 0.14),
        },
    },
    "professional_services": {
        "small": {
            "monthly_revenue_start_eur": (40_000.0, 140_000.0),
            "monthly_revenue_growth": (-0.004, 0.015),
            "days_sales_outstanding": (30.0, 55.0),
            "days_payables_outstanding": (20.0, 40.0),
            "starting_cash_eur": (40_000.0, 160_000.0),
            "target_cash_at_end_eur": (50_000.0, 180_000.0),
            "cost_materials": (0.05, 0.15),
            "cost_services": (0.08, 0.18),
            "cost_personnel": (0.40, 0.55),
            "cost_other": (0.10, 0.20),
        },
        "medium": {
            "monthly_revenue_start_eur": (120_000.0, 400_000.0),
            "monthly_revenue_growth": (-0.004, 0.014),
            "days_sales_outstanding": (32.0, 58.0),
            "days_payables_outstanding": (22.0, 42.0),
            "starting_cash_eur": (100_000.0, 350_000.0),
            "target_cash_at_end_eur": (120_000.0, 400_000.0),
            "cost_materials": (0.05, 0.14),
            "cost_services": (0.08, 0.16),
            "cost_personnel": (0.40, 0.52),
            "cost_other": (0.10, 0.18),
        },
        "large": {
            "monthly_revenue_start_eur": (350_000.0, 1_500_000.0),
            "monthly_revenue_growth": (-0.003, 0.012),
            "days_sales_outstanding": (35.0, 60.0),
            "days_payables_outstanding": (25.0, 45.0),
            "starting_cash_eur": (300_000.0, 1_200_000.0),
            "target_cash_at_end_eur": (350_000.0, 1_400_000.0),
            "cost_materials": (0.04, 0.12),
            "cost_services": (0.08, 0.16),
            "cost_personnel": (0.38, 0.50),
            "cost_other": (0.10, 0.18),
        },
    },
    "other": {
        "small": {
            "monthly_revenue_start_eur": (50_000.0, 200_000.0),
            "monthly_revenue_growth": (-0.005, 0.012),
            "days_sales_outstanding": (25.0, 50.0),
            "days_payables_outstanding": (22.0, 42.0),
            "starting_cash_eur": (50_000.0, 220_000.0),
            "target_cash_at_end_eur": (60_000.0, 250_000.0),
            "cost_materials": (0.25, 0.40),
            "cost_services": (0.06, 0.14),
            "cost_personnel": (0.28, 0.40),
            "cost_other": (0.10, 0.18),
        },
        "medium": {
            "monthly_revenue_start_eur": (180_000.0, 550_000.0),
            "monthly_revenue_growth": (-0.005, 0.012),
            "days_sales_outstanding": (28.0, 52.0),
            "days_payables_outstanding": (25.0, 45.0),
            "starting_cash_eur": (150_000.0, 500_000.0),
            "target_cash_at_end_eur": (180_000.0, 550_000.0),
            "cost_materials": (0.25, 0.40),
            "cost_services": (0.06, 0.14),
            "cost_personnel": (0.28, 0.38),
            "cost_other": (0.10, 0.16),
        },
        "large": {
            "monthly_revenue_start_eur": (500_000.0, 3_000_000.0),
            "monthly_revenue_growth": (-0.004, 0.010),
            "days_sales_outstanding": (30.0, 55.0),
            "days_payables_outstanding": (28.0, 50.0),
            "starting_cash_eur": (400_000.0, 2_500_000.0),
            "target_cash_at_end_eur": (500_000.0, 3_000_000.0),
            "cost_materials": (0.25, 0.40),
            "cost_services": (0.05, 0.12),
            "cost_personnel": (0.26, 0.36),
            "cost_other": (0.08, 0.16),
        },
    },
}

_INDUSTRY_KEYWORDS: list[tuple[IndustryKey, tuple[str, ...]]] = [
    (
        "hospitality",
        ("hotel", "hotelli", "lodging", "majoitus", "hospitality", "adr", "occupancy"),
    ),
    (
        "food_service",
        (
            "bakery",
            "leipomo",
            "leipuri",
            "cafe",
            "kahvila",
            "restaurant",
            "ravintola",
            "food",
            "catering",
        ),
    ),
    (
        "manufacturing",
        (
            "steel",
            "teräs",
            "teras",
            "fabricat",
            "manufactur",
            "workshop",
            "konepaja",
            "metal",
            "machine shop",
            "valmistus",
            "factory",
            "tehta",
        ),
    ),
    ("retail", ("retail", "shop", "store", "kauppa", "myymälä", "mymala")),
    (
        "professional_services",
        ("consult", "software", "it ", "agency", "palvelu", "lawyer", "accountan"),
    ),
]


def classify_industry(industry: str | None, description: str | None = None) -> IndustryKey:
    """Map free-text industry / description to a generic industry key."""
    blob = f"{industry or ''} {description or ''}".casefold()
    for key, words in _INDUSTRY_KEYWORDS:
        if any(w in blob for w in words):
            return key
    return "other"


def _seeded_rng(seed: int, industry: IndustryKey, band: SizeBand) -> random.Random:
    material = f"{seed}|{industry}|{band}".encode()
    digest = hashlib.sha256(material).hexdigest()
    return random.Random(int(digest[:16], 16))


def _draw(rng: random.Random, lo: float, hi: float) -> float:
    if hi < lo:
        lo, hi = hi, lo
    return float(rng.uniform(lo, hi))


def draw_assumed_defaults(
    *,
    industry: str | None,
    company_size: str | None,
    seed: int,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Draw a full assumed-parameter set from the industry×size range table.

    Returns flat parameter values plus ``field_sources`` all marked ``assumed``.
    Cost shares are normalized to sum ≈ 0.94 after draw.
    """
    # Generic assumptions for every industry. No keyword matching, so a new or
    # unlisted industry gets exactly the same values. All such values are "assumed".
    key = "other"
    band = size_band(str(company_size or "small"))
    ranges = _RANGE_TABLE[key][band]
    rng = _seeded_rng(seed, key, band)

    materials = _draw(rng, *ranges["cost_materials"])
    services = _draw(rng, *ranges["cost_services"])
    personnel = _draw(rng, *ranges["cost_personnel"])
    other = _draw(rng, *ranges["cost_other"])
    share_sum = materials + services + personnel + other
    target = 0.94
    if share_sum > 0:
        scale = target / share_sum
        materials *= scale
        services *= scale
        personnel *= scale
        other *= scale

    values: dict[str, Any] = {
        "monthly_revenue_start_eur": round(_draw(rng, *ranges["monthly_revenue_start_eur"]), 2),
        "monthly_revenue_growth": round(_draw(rng, *ranges["monthly_revenue_growth"]), 6),
        "days_sales_outstanding": round(_draw(rng, *ranges["days_sales_outstanding"]), 2),
        "days_payables_outstanding": round(_draw(rng, *ranges["days_payables_outstanding"]), 2),
        "starting_cash_eur": round(_draw(rng, *ranges["starting_cash_eur"]), 2),
        "target_cash_at_end_eur": round(_draw(rng, *ranges["target_cash_at_end_eur"]), 2),
        "cost_shares_of_revenue": {
            "materials": round(materials, 6),
            "services": round(services, 6),
            "personnel": round(personnel, 6),
            "other": round(other, 6),
        },
        "special_investment_eur": 0.0,
        "special_investment_month": 2,
        "one_off_events": [],
        "partly_fixed_costs": False,
        "industry_key": key,
        "size_band": band,
    }
    sources = {
        "monthly_revenue_start_eur": "assumed",
        "monthly_revenue_growth": "assumed",
        "days_sales_outstanding": "assumed",
        "days_payables_outstanding": "assumed",
        "starting_cash_eur": "assumed",
        "target_cash_at_end_eur": "assumed",
        "cost_shares_of_revenue": "assumed",
        "special_investment_eur": "assumed",
    }
    values["field_sources"] = sources
    return values


def range_for(
    field: str,
    *,
    industry: str | None,
    company_size: str | None,
    description: str | None = None,
) -> tuple[float, float] | None:
    """Return (lo, hi) for a scalar field, or None if unknown."""
    key = classify_industry(industry, description)
    band = size_band(str(company_size or "small"))
    return _RANGE_TABLE[key][band].get(field)


def healthy_variable_cost_sum(start_revenue_eur: float) -> float:
    """Sum of variable cost shares that leaves a healthy profile profitable.

    Fixed charges (depreciation + interest on the loan anchor) are a fixed euro
    amount per month, so they weigh more on a small revenue base. The variable
    cost sum is lowered as far as the blocking FR-A-11 band allows
    (COST_SHARE_SUM_MIN) to keep HEALTHY_MIN_OPERATING_MARGIN after fixed charges.
    """
    fixed_monthly = FIXED_DEPRECIATION_MONTHLY_EUR + LOAN_ANCHOR_EUR * INTEREST_ANNUAL_RATE / 12.0
    fixed_ratio = fixed_monthly / max(float(start_revenue_eur), 1.0)
    target = 1.0 - fixed_ratio - HEALTHY_MIN_OPERATING_MARGIN
    return min(COST_SHARE_SUM_TARGET, max(COST_SHARE_SUM_MIN, target))


def calibrate_cost_shares_for_shape(
    shares: dict[str, Any],
    *,
    start_revenue_eur: float,
    scenario_shape: str | None,
) -> dict[str, Any]:
    """Rescale ASSUMED cost shares for the scenario shape.

    - ``healthy`` / ``cash_critical`` → profitable variable-cost sum (VR-22 /
      work-order: cash-critical stress comes from payment timing, not a loss).
    - ``weak`` / ``cash_tight`` → loss-making cost sum.
    Stated shares are never passed here (the caller calibrates assumed shares only).
    """
    shape = (scenario_shape or "").strip().lower()
    keys = ("materials", "services", "personnel", "other")
    total = sum(float(shares.get(k) or 0.0) for k in keys)
    if total <= 0:
        return dict(shares)
    if shape in {"weak", "cash_tight"}:
        target = LOSS_SHAPE_COST_SUM_TARGET
    elif shape in {"healthy", "cash_critical"}:
        target = healthy_variable_cost_sum(start_revenue_eur)
    else:
        return dict(shares)
    scale = target / total
    out = dict(shares)
    for k in keys:
        out[k] = round(float(shares.get(k) or 0.0) * scale, 6)
    # Guard: never leave the FR-A-11 band (the calibration can only land inside it).
    total_after = sum(float(out[k]) for k in keys)
    assert COST_SHARE_SUM_MIN - 1e-6 <= total_after <= COST_SHARE_SUM_MAX + 1e-6
    return out
