"""Shared constants."""

# Finnish standard VAT rate used in example packs (receivables / payables / invoices).
VAT_RATE_FI: float = 0.255

# Corporate tax rate used for simplified P&L (illustrative, not tax advice).
CORPORATE_TAX_RATE: float = 0.20

# SRS DR-02 / VR: money to the cent.
MONEY_TOLERANCE_EUR: float = 0.02

SOFTWARE_VERSION: str = "0.1.0"

# SRS §6.1-inspired ranges (mapped onto PayLoq parameter fields).
# Ceilings cover mid-market / large manufacturing (e.g. ~€4M/mo revenue, multi-million CAPEX).
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "monthly_revenue_start_eur": (20_000.0, 10_000_000.0),
    "monthly_revenue_growth": (-0.10, 0.05),  # -10% .. +5% per month
    "days_sales_outstanding": (14.0, 90.0),
    "days_payables_outstanding": (14.0, 90.0),
    "target_cash_at_end_eur": (-50_000.0, 5_000_000.0),
    "special_investment_eur": (0.0, 10_000_000.0),
}

# FR-A-11: cost shares of revenue must sum roughly to 0.9–1.0 (blocking repair).
COST_SHARE_SUM_MIN: float = 0.9
COST_SHARE_SUM_MAX: float = 1.0
COST_SHARE_SUM_TARGET: float = 0.94

# Seasonality factor bounds (per calendar month).
REVENUE_FACTOR_MIN: float = 0.05
REVENUE_FACTOR_MAX: float = 2.0

# Projection vs history weekly-move scale (VR-08). Ratio above this is blocking.
PROJECTION_HISTORY_SCALE_RATIO: float = 5.0
# Early projection negativity vs late history crisis (VR-08 timing).
PROJECTION_EARLY_NEG_WEEK: int = 4
HISTORY_LATE_NEG_WEEK: int = 18

FORBIDDEN_TEXT_WORDS: frozenset[str] = frozenset(
    {
        "fraud",
        "petos",
        "bankruptcy",
        "konkurssi",
        "nokia",
        "apple",
        "google",
        "microsoft",
        "amazon",
        "tesla",
        "samsung",
    }
)
