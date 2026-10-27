"""Soft NL→params quality hints (non-blocking)."""

from payloq_llm.nl_quality import assess_nl_params


def test_critical_text_flags_high_cash() -> None:
    warnings = assess_nl_params(
        "Pieni konepaja, kassa on kriittinen kolmen viikon päästä.",
        {
            "monthly_revenue_start_eur": 200_000,
            "monthly_revenue_growth": 0.0,
            "cost_shares_of_revenue": {
                "materials": 0.37,
                "services": 0.08,
                "personnel": 0.34,
                "other": 0.15,
            },
            "days_sales_outstanding": 40,
            "days_payables_outstanding": 32,
            "target_cash_at_end_eur": 330_000,
            "special_investment_eur": 0,
            "notes": "stub: good / default heuristic",
        },
        language="fi",
    )
    codes = {w["code"] for w in warnings}
    assert "nl_cash_vs_critical" in codes
    assert "nl_stub_heuristic" in codes
    assert all(w["severity"] == "warning" for w in warnings)
    assert all(w["message_fi"] and w["message_en"] for w in warnings)


def test_matching_critical_params_minimal_warnings() -> None:
    warnings = assess_nl_params(
        "Cash turns critical in three weeks.",
        {
            "monthly_revenue_start_eur": 200_000,
            "monthly_revenue_growth": 0.0,
            "cost_shares_of_revenue": {
                "materials": 0.37,
                "services": 0.08,
                "personnel": 0.34,
                "other": 0.15,
            },
            "days_sales_outstanding": 40,
            "days_payables_outstanding": 32,
            "target_cash_at_end_eur": 45_000,
            "special_investment_eur": 80_000,
            "notes": "ollama ok",
        },
        language="en",
    )
    codes = {w["code"] for w in warnings}
    assert "nl_cash_vs_critical" not in codes
    assert "nl_invest_vs_critical" not in codes
