"""Code-built answer keys (FR-B-30..33). LLM never authors these."""

from __future__ import annotations

from typing import Any

from payloq_schemas.models import ScenarioPack


def build_answer_key(pack: ScenarioPack) -> dict[str, Any]:
    """Derive the scoring key from generated figures + parameters."""
    params = pack.input.parameters_from_language_model
    months = pack.monthly_reports.months
    cash = pack.cash_and_invoices
    proj = cash.projection_from_open_invoices
    hist = cash.balance_history
    sid = (
        pack.input.options.scenario_id
        or pack.input.meta.scenario
        or "scenario"
    ).lower()

    first_neg_proj = next((w for w in proj if w.projected_balance < 0), None)
    first_neg_hist = next((p for p in hist if p.balance < 0), None)
    lowest_proj = min(proj, key=lambda w: w.projected_balance) if proj else None
    lowest_hist = min(hist, key=lambda p: p.balance) if hist else None

    rev0 = months[0].income_statement.revenue if months else None
    rev_last = months[-1].income_statement.revenue if months else None
    net_sum = sum(m.income_statement.net_result for m in months)
    mom_pairs: list[dict[str, Any]] = []
    for i in range(1, len(months)):
        prev = months[i - 1].income_statement.revenue
        cur = months[i].income_statement.revenue
        delta = round(cur - prev, 2)
        pct = round(delta / prev, 4) if prev else None
        direction = "up" if delta > 0 else ("down" if delta < 0 else "stable")
        mom_pairs.append(
            {
                "from_month": months[i - 1].month,
                "to_month": months[i].month,
                "delta_eur": delta,
                "pct": pct,
                "direction": direction,
            }
        )

    key_findings: list[dict[str, Any]] = [
        {
            "id": "cash_end",
            "label": "Cash at period end",
            "value": months[-1].balance_sheet.assets.cash if months else None,
            "unit": "EUR",
        },
        {
            "id": "revenue_last",
            "label": "Revenue in last month",
            "value": rev_last,
            "unit": "EUR",
        },
        {
            "id": "revenue_first_vs_last",
            "label": "Revenue last vs first month",
            "value": round((rev_last or 0) - (rev0 or 0), 2) if rev0 is not None else None,
            "unit": "EUR",
        },
        {
            "id": "net_result_sum",
            "label": "Sum of monthly net results",
            "value": round(net_sum, 2),
            "unit": "EUR",
        },
        {
            "id": "first_negative_projection_week",
            "label": "First week projected cash is negative",
            "value": first_neg_proj.week if first_neg_proj else None,
            "week": first_neg_proj.week if first_neg_proj else None,
            "balance_eur": first_neg_proj.projected_balance if first_neg_proj else None,
        },
        {
            "id": "lowest_projection_balance",
            "label": "Lowest projected balance",
            "value": lowest_proj.projected_balance if lowest_proj else None,
            "week": lowest_proj.week if lowest_proj else None,
        },
        {
            "id": "first_negative_history_week",
            "label": "First balance-history week with negative cash",
            "value": first_neg_hist.week if first_neg_hist else None,
            "week": first_neg_hist.week if first_neg_hist else None,
            "balance_eur": first_neg_hist.balance if first_neg_hist else None,
            "date": first_neg_hist.date if first_neg_hist else None,
        },
        {
            "id": "lowest_history_balance",
            "label": "Lowest balance-history cash",
            "value": lowest_hist.balance if lowest_hist else None,
            "week": lowest_hist.week if lowest_hist else None,
            "date": lowest_hist.date if lowest_hist else None,
        },
    ]

    questions = [
        {
            "id": "q_cash_negative_when",
            "question_en": "When does cash turn negative?",
            "question_fi": "Milloin kassa menee negatiiviseksi?",
            "answer_en": _when_negative_en(first_neg_proj, first_neg_hist),
            "answer_fi": _when_negative_fi(first_neg_proj, first_neg_hist),
            "expected_week": (first_neg_proj.week if first_neg_proj else None)
            or (first_neg_hist.week if first_neg_hist else None),
        },
        {
            "id": "q_cash_end",
            "question_en": "What is cash at period end?",
            "question_fi": "Mikä on kassasaldo kauden lopussa?",
            "answer_en": f"{months[-1].balance_sheet.assets.cash:.2f} EUR" if months else "n/a",
            "answer_fi": f"{months[-1].balance_sheet.assets.cash:.2f} EUR" if months else "n/a",
            "expected_value": months[-1].balance_sheet.assets.cash if months else None,
        },
        {
            "id": "q_revenue_trend",
            "question_en": "Did revenue rise or fall from first to last month?",
            "question_fi": "Nousiko vai laskiko liikevaihto ensimmäisestä viimeiseen kuukauteen?",
            "answer_en": _rev_trend_en(rev0, rev_last),
            "answer_fi": _rev_trend_fi(rev0, rev_last),
            "expected_direction": (
                "up"
                if rev0 is not None and rev_last is not None and rev_last > rev0
                else (
                    "down"
                    if rev0 is not None and rev_last is not None and rev_last < rev0
                    else "stable"
                )
            ),
        },
        {
            "id": "q_profitable",
            "question_en": "Is the company profitable overall across the months?",
            "question_fi": "Onko yritys kokonaisuudessaan voitollinen näillä kuukausilla?",
            "answer_en": "yes" if net_sum > 0 else "no",
            "answer_fi": "kyllä" if net_sum > 0 else "ei",
            "expected_value": net_sum > 0,
        },
    ]

    forbidden = _forbidden_claims(sid, net_sum > 0, first_neg_proj is not None or first_neg_hist is not None)

    return {
        "schema_version": 1,
        "scenario": sid,
        "parameters": params.model_dump(),
        "parameter_field_map_srs_6_1": {
            "revenue_level_eur_month": "monthly_revenue_start_eur",
            "monthly_growth_pct": "monthly_revenue_growth (*100 for percent)",
            "payment_terms_customers_days": "days_sales_outstanding",
            "payment_terms_suppliers_days": "days_payables_outstanding",
            "cash_target_week": "derived from first_negative_projection_week / history",
            "number_of_months": "options.months",
        },
        "key_findings": key_findings,
        "month_over_month_revenue": mom_pairs,
        "questions": questions,
        "forbidden_claims": forbidden,
    }


def _when_negative_en(proj, hist) -> str:
    if proj is not None:
        return f"Week {proj.week} (open-invoice projection), balance {proj.projected_balance:.2f} EUR"
    if hist is not None:
        return f"Balance-history week {hist.week} ({hist.date}), balance {hist.balance:.2f} EUR"
    return "Cash does not go negative in the projection or balance history."


def _when_negative_fi(proj, hist) -> str:
    if proj is not None:
        return f"Viikko {proj.week} (avointen laskujen ennuste), saldo {proj.projected_balance:.2f} EUR"
    if hist is not None:
        return f"Kassahistorian viikko {hist.week} ({hist.date}), saldo {hist.balance:.2f} EUR"
    return "Kassa ei mene negatiiviseksi ennusteessa eikä kassahistoriassa."


def _rev_trend_en(rev0: float | None, rev_last: float | None) -> str:
    if rev0 is None or rev_last is None:
        return "n/a"
    if rev_last > rev0:
        return f"Revenue rose from {rev0:.2f} to {rev_last:.2f} EUR"
    if rev_last < rev0:
        return f"Revenue fell from {rev0:.2f} to {rev_last:.2f} EUR"
    return f"Revenue was stable at {rev_last:.2f} EUR"


def _rev_trend_fi(rev0: float | None, rev_last: float | None) -> str:
    if rev0 is None or rev_last is None:
        return "n/a"
    if rev_last > rev0:
        return f"Liikevaihto nousi {rev0:.2f} → {rev_last:.2f} EUR"
    if rev_last < rev0:
        return f"Liikevaihto laski {rev0:.2f} → {rev_last:.2f} EUR"
    return f"Liikevaihto pysyi {rev_last:.2f} EUR"


def _forbidden_claims(sid: str, profitable: bool, cash_negative: bool) -> list[dict[str, str]]:
    claims = [
        {
            "id": "invented_strike",
            "claim_en": "Cash fell because of a strike in September",
            "claim_fi": "Kassa laski syyskuun lakon vuoksi",
            "why_wrong": "Cause not present in the synthetic data",
        },
        {
            "id": "invented_fraud",
            "claim_en": "The drop is explained by fraud",
            "claim_fi": "Laskua selittää petos",
            "why_wrong": "Forbidden / unsupported cause",
        },
    ]
    if sid == "cash_critical" or (profitable and cash_negative):
        claims.append(
            {
                "id": "profit_means_cash_ok",
                "claim_en": "The company is in profit, so cash is fine",
                "claim_fi": "Yritys on voitollinen, joten kassa on kunnossa",
                "why_wrong": "Profitability does not imply healthy cash timing",
            }
        )
    if sid == "weak" and not cash_negative:
        claims.append(
            {
                "id": "weak_means_cash_critical",
                "claim_en": "Cash is critical because the company is losing money",
                "claim_fi": "Kassa on kriittinen koska yritys tekee tappiota",
                "why_wrong": "Weak scenario: cash may stay positive in the period",
            }
        )
    if sid in {"good"} and not cash_negative:
        claims.append(
            {
                "id": "invented_risk",
                "claim_en": "The company should worry about rising costs creating a cash crisis",
                "claim_fi": "Yrityksen pitäisi huolestua nousevista kuluista ja kassakriisistä",
                "why_wrong": "Good scenario data does not show a cash crisis",
            }
        )
    return claims
