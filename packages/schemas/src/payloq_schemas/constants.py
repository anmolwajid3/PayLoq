"""Shared constants."""

# Finnish standard VAT rate used in example packs (receivables / payables / invoices).
VAT_RATE_FI: float = 0.255

# Corporate tax rate used for simplified P&L (illustrative, not tax advice).
CORPORATE_TAX_RATE: float = 0.20

# SRS DR-02 / VR: money to the cent.
MONEY_TOLERANCE_EUR: float = 0.02

SOFTWARE_VERSION: str = "0.1.0"

# SRS §6.1-inspired ranges (mapped onto PayLoq parameter fields).
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "monthly_revenue_start_eur": (20_000.0, 2_000_000.0),
    "monthly_revenue_growth": (-0.10, 0.05),  # -10% .. +5% per month
    "days_sales_outstanding": (14.0, 90.0),
    "days_payables_outstanding": (14.0, 90.0),
    "target_cash_at_end_eur": (-50_000.0, 500_000.0),
    "special_investment_eur": (0.0, 2_000_000.0),
}

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
