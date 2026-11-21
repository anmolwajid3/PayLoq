"""Config ranges selected by scenario_shape (pilot fix prompt §D).

Neutral defaults plus optional industry overlays. No company-specific hardcodes.
``cash_critical`` biases growth/starting cash so generation can hit a trough
around week 3 when the model classifies that shape.
"""

from __future__ import annotations

from typing import Any, Literal

ScenarioShape = Literal[
    "healthy",
    "weak",
    "cash_tight",
    "cash_critical",
    "unspecified",
]

# Inclusive (lo, hi) for assumed draws when the field is null.
# Keys use legacy engine names after mapping from section B.
SCENARIO_SHAPE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "healthy": {
        "monthly_revenue_growth": (0.002, 0.012),
        "starting_cash_eur": (120_000.0, 400_000.0),
        "target_cash_at_end_eur": (150_000.0, 450_000.0),
    },
    "weak": {
        "monthly_revenue_growth": (-0.02, -0.002),
        "starting_cash_eur": (60_000.0, 150_000.0),
        "target_cash_at_end_eur": (40_000.0, 120_000.0),
    },
    "cash_tight": {
        "monthly_revenue_growth": (-0.01, 0.004),
        "starting_cash_eur": (40_000.0, 90_000.0),
        "target_cash_at_end_eur": (20_000.0, 55_000.0),
    },
    # Cash trough within ~3 weeks: low opening cash + low covenant/target.
    "cash_critical": {
        "monthly_revenue_growth": (-0.008, 0.004),
        "starting_cash_eur": (35_000.0, 55_000.0),
        "target_cash_at_end_eur": (5_000.0, 25_000.0),
    },
    "unspecified": {
        "monthly_revenue_growth": (-0.005, 0.010),
        "starting_cash_eur": (80_000.0, 250_000.0),
        "target_cash_at_end_eur": (90_000.0, 280_000.0),
    },
}

SCENARIO_SHAPE_TO_PROFILE: dict[str, str] = {
    "healthy": "good",
    "weak": "weak",
    "cash_tight": "weak",
    "cash_critical": "cash_critical",
    "unspecified": "custom",
}


def ranges_for_shape(scenario_shape: str | None) -> dict[str, tuple[float, float]]:
    key = (scenario_shape or "unspecified").strip().lower()
    return dict(SCENARIO_SHAPE_RANGES.get(key, SCENARIO_SHAPE_RANGES["unspecified"]))


def profile_for_shape(scenario_shape: str | None) -> str:
    key = (scenario_shape or "unspecified").strip().lower()
    return SCENARIO_SHAPE_TO_PROFILE.get(key, "custom")


def overlay_shape_on_drawn(
    drawn: dict[str, Any],
    *,
    scenario_shape: str | None,
    seed: int,
) -> dict[str, Any]:
    """Replace growth/cash draws with scenario_shape config ranges (seeded)."""
    import hashlib
    import random

    ranges = ranges_for_shape(scenario_shape)
    material = f"{seed}|shape|{scenario_shape or 'unspecified'}".encode()
    digest = hashlib.sha256(material).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    out = dict(drawn)
    # Iterate the config table in its declared order (fresh RNG from seed each call).
    for field, (lo, hi) in ranges.items():
        if hi < lo:
            lo, hi = hi, lo
        out[field] = round(float(rng.uniform(lo, hi)), 6 if "growth" in field else 2)
    out["scenario_shape"] = (scenario_shape or "unspecified").strip().lower()
    return out
