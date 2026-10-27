"""Soft (non-blocking) NL → params quality hints for the app UI."""

from __future__ import annotations

from typing import Any


def assess_nl_params(
    text: str,
    params: dict[str, Any],
    *,
    language: str = "fi",
) -> list[dict[str, str]]:
    """
    Heuristic soft-warnings for extracted parameters vs the NL description.

    Never fails generation — warnings are informational for the researcher.
    Each item: {code, severity: "warning", message_fi, message_en}.
    """
    warnings: list[dict[str, str]] = []
    blob = (text or "").lower()
    growth = float(params.get("monthly_revenue_growth") or 0)
    cash = float(params.get("target_cash_at_end_eur") or 0)
    invest = float(params.get("special_investment_eur") or 0)
    shares = params.get("cost_shares_of_revenue") or {}
    share_sum = sum(float(shares.get(k) or 0) for k in ("materials", "services", "personnel", "other"))

    critical_kw = ("kriittinen", "critical", "negatiiv", "kolmen viikon", "three weeks", "cash critical")
    weak_kw = ("laskee", "falling", "tappioll", "weak", "heikko", "heikkene")
    good_kw = ("hyvä kassa", "healthy cash", "steady growth", "tasainen kasvu", "hyvä kassatilanne")

    looks_critical = any(k in blob for k in critical_kw)
    looks_weak = any(k in blob for k in weak_kw) and not looks_critical
    looks_good = any(k in blob for k in good_kw) and not looks_critical and not looks_weak

    if looks_critical and cash > 120_000:
        warnings.append(
            _w(
                "nl_cash_vs_critical",
                "Kuvaus vihjaa kriittiseen kassaan, mutta tavoitekassa on korkea "
                f"({cash:,.0f} €).",
                f"Description suggests critical cash, but target cash is high ({cash:,.0f} €).",
            )
        )
    if looks_critical and invest < 40_000:
        warnings.append(
            _w(
                "nl_invest_vs_critical",
                "Kriittinen kassa usein tarvitsee suuremman erityisinvestoinnin parametriin.",
                "Critical-cash wording usually needs a larger special_investment_eur.",
            )
        )
    if looks_weak and growth >= 0:
        warnings.append(
            _w(
                "nl_growth_vs_weak",
                f"Kuvaus kuulostaa heikolta, mutta kasvu on {growth:.3f} (≥ 0).",
                f"Description sounds weak, but growth is {growth:.3f} (≥ 0).",
            )
        )
    if looks_good and growth < 0:
        warnings.append(
            _w(
                "nl_growth_vs_good",
                f"Kuvaus kuulostaa hyvältä, mutta kasvu on negatiivinen ({growth:.3f}).",
                f"Description sounds healthy, but growth is negative ({growth:.3f}).",
            )
        )
    if looks_good and cash < 150_000:
        warnings.append(
            _w(
                "nl_cash_vs_good",
                f"Hyvä skenaario: tavoitekassa {cash:,.0f} € vaikuttaa matalalta.",
                f"Healthy scenario: target cash {cash:,.0f} € looks low.",
            )
        )

    if share_sum < 0.7 or share_sum > 1.15:
        warnings.append(
            _w(
                "nl_cost_share_sum",
                f"Kustannusosuuksien summa on {share_sum:.2f} (odotettu ~0.9–1.0).",
                f"Cost shares sum to {share_sum:.2f} (expected ~0.9–1.0).",
            )
        )

    dso = float(params.get("days_sales_outstanding") or 0)
    dpo = float(params.get("days_payables_outstanding") or 0)
    if dso < 5 or dso > 120:
        warnings.append(
            _w(
                "nl_dso_range",
                f"Myyntisaamisten kiertoaika (DSO) {dso:.0f} pv on epätavallinen.",
                f"Days sales outstanding (DSO) {dso:.0f} looks unusual.",
            )
        )
    if dpo < 5 or dpo > 120:
        warnings.append(
            _w(
                "nl_dpo_range",
                f"Ostovelkojen kiertoaika (DPO) {dpo:.0f} pv on epätavallinen.",
                f"Days payables outstanding (DPO) {dpo:.0f} looks unusual.",
            )
        )

    notes = str(params.get("notes") or "")
    if "stub:" in notes.lower() and language:
        warnings.append(
            _w(
                "nl_stub_heuristic",
                "Parametrit tulivat stub-heuristiikasta (ei live-mallia) — tarkista sopivuus kuvaukseen.",
                "Parameters came from stub heuristics (no live model) — check fit to the description.",
            )
        )

    return warnings


def _w(code: str, message_fi: str, message_en: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "warning",
        "message_fi": message_fi,
        "message_en": message_en,
    }
