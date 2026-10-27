"""§4 chat demo: code supplies figures; LLM interprets only (stub + Ollama)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from payloq_schemas.models import ScenarioPack

from payloq_llm.adapters import FallbackAdapter, LlmAdapter, get_adapter
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

DemoPresetId = Literal["cash_drop", "cash_negative"]

DEMO_PRESETS: dict[str, dict[str, str]] = {
    "cash_drop": {
        "fi": "Miksi kassa laski?",
        "en": "Why did cash drop?",
    },
    "cash_negative": {
        "fi": "Milloin kassa menee negatiiviseksi?",
        "en": "When does cash go negative?",
    },
}


def resolve_question(
    *,
    question: str | None = None,
    preset: str | None = None,
    language: str = "fi",
) -> tuple[str, str | None]:
    """Return (question_text, preset_id). Prefers explicit question over preset."""
    if question and question.strip():
        return question.strip(), preset
    if preset:
        if preset not in DEMO_PRESETS:
            raise ValueError(f"Unknown chat preset '{preset}'. Choose: {list(DEMO_PRESETS)}")
        lang = language if language in {"fi", "en"} else "fi"
        return DEMO_PRESETS[preset][lang], preset
    raise ValueError("Provide question=… or preset=cash_drop|cash_negative")


def build_chat_figures(pack: ScenarioPack) -> dict[str, Any]:
    """
    Code-owned figure pack for chat.

    Extends the benchmark pack summary with cash-drop / projection facts so the
    model can interpret without inventing causes.
    """
    # Reuse compact summary from benchmark when available; keep llm free of
    # a hard dependency on payloq_benchmark by computing inline.
    months = pack.monthly_reports.months
    last = months[-1]
    prev = months[-2] if len(months) >= 2 else None
    cash = pack.cash_and_invoices
    hist = cash.balance_history

    revenue_last = last.income_statement.revenue
    revenue_prev = prev.income_statement.revenue if prev else None
    mom_revenue_change = None
    if revenue_prev is not None:
        mom_revenue_change = round(revenue_last - revenue_prev, 2)

    cash_end = last.balance_sheet.assets.cash
    cash_prev = prev.balance_sheet.assets.cash if prev else None
    mom_cash_change = None
    if cash_prev is not None:
        mom_cash_change = round(cash_end - cash_prev, 2)

    first_hist = hist[0] if hist else None
    last_hist = hist[-1] if hist else None
    history_change = None
    if first_hist and last_hist:
        history_change = round(last_hist.balance - first_hist.balance, 2)

    # Largest weekly drops in balance history (code-computed)
    weekly_deltas: list[dict[str, Any]] = []
    for i in range(1, len(hist)):
        delta = round(hist[i].balance - hist[i - 1].balance, 2)
        weekly_deltas.append(
            {
                "from_date": hist[i - 1].date,
                "to_date": hist[i].date,
                "delta": delta,
                "balance": hist[i].balance,
            }
        )
    largest_drops = sorted(weekly_deltas, key=lambda d: d["delta"])[:3]

    first_neg = None
    first_neg_date = None
    first_neg_balance = None
    for w in cash.projection_from_open_invoices:
        if w.projected_balance < 0:
            first_neg = w.week
            first_neg_date = w.week_end
            first_neg_balance = w.projected_balance
            break

    open_sales = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "sales")
    open_purch = sum(i.amount_incl_vat for i in cash.open_invoices if i.type == "purchase")
    overdue_sales = sum(
        i.amount_incl_vat
        for i in cash.open_invoices
        if i.type == "sales" and i.status == "overdue"
    )

    params = pack.input.parameters_from_language_model
    return {
        "scenario_id": pack.input.options.scenario_id or pack.input.meta.scenario,
        "months": len(months),
        "last_month": last.month,
        "prev_month": prev.month if prev else None,
        "revenue_last": revenue_last,
        "revenue_prev": revenue_prev,
        "mom_revenue_change": mom_revenue_change,
        "net_result_last": last.income_statement.net_result,
        "cash_end": cash_end,
        "cash_prev_month": cash_prev,
        "mom_cash_change": mom_cash_change,
        "balance_history_first": first_hist.balance if first_hist else None,
        "balance_history_last": last_hist.balance if last_hist else None,
        "balance_history_change": history_change,
        "balance_history_first_date": first_hist.date if first_hist else None,
        "balance_history_last_date": last_hist.date if last_hist else None,
        "largest_weekly_cash_drops": largest_drops,
        "receivables": last.balance_sheet.assets.receivables,
        "payables": last.balance_sheet.equity_and_liabilities.payables,
        "open_sales_sum": round(open_sales, 2),
        "open_purchase_sum": round(open_purch, 2),
        "overdue_sales_sum": round(overdue_sales, 2),
        "special_investment_eur": params.special_investment_eur,
        "target_cash_at_end_eur": params.target_cash_at_end_eur,
        "first_negative_projection_week": first_neg,
        "first_negative_projection_week_end": first_neg_date,
        "first_negative_projection_balance": first_neg_balance,
        "projection_week_1_balance": (
            cash.projection_from_open_invoices[0].projected_balance
            if cash.projection_from_open_invoices
            else None
        ),
        "projection_week_3_balance": next(
            (w.projected_balance for w in cash.projection_from_open_invoices if w.week == 3),
            None,
        ),
        "projection_weeks": [
            {
                "week": w.week,
                "week_end": w.week_end,
                "sales_inflow": w.sales_inflow,
                "purchase_outflow": w.purchase_outflow,
                "projected_balance": w.projected_balance,
            }
            for w in cash.projection_from_open_invoices
        ],
        "allowed_facts": [
            "All figures above are produced by code from parameters.",
            "Projection excludes payroll/tax/recurring costs; overdue sales assumed paid in week 1.",
            "Do not invent external causes (customers leaving, bank freezes, fraud, etc.).",
            "If cash dropped, cite history_change / mom_cash_change / largest weekly drops / investment.",
            "If asked when cash goes negative, use first_negative_projection_week (or say it does not).",
        ],
    }


@dataclass
class ChatDemoResult:
    question: str
    answer: str
    figures: dict[str, Any]
    preset: str | None
    llm_adapter: str
    fallback_note: str | None
    metrics: dict[str, Any] | None


def run_chat_demo(
    pack: ScenarioPack,
    *,
    question: str | None = None,
    preset: str | None = None,
    language: str = "fi",
    llm: str = "stub",
    adapter: LlmAdapter | None = None,
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    no_fallback_stub: bool = False,
) -> ChatDemoResult:
    """
    Ask a virtual-accountant question over a generated pack.

    Code builds `figures`; the adapter only interprets them.
    """
    q, preset_id = resolve_question(question=question, preset=preset, language=language)
    figures = build_chat_figures(pack)
    used = adapter or get_adapter(
        llm,
        fallback_stub=not no_fallback_stub,
        model=ollama_model or DEFAULT_OLLAMA_MODEL,
        host=ollama_host or DEFAULT_OLLAMA_HOST,
    )
    answer = used.interpret_figures(q, figures)
    fallback_note = None
    adapter_name = getattr(used, "name", llm)
    if isinstance(used, FallbackAdapter):
        if used.used_fallback:
            fallback_note = used.last_fallback_reason
            adapter_name = f"{used.primary.name}->stub"
        else:
            adapter_name = used.primary.name
    return ChatDemoResult(
        question=q,
        answer=answer,
        figures=figures,
        preset=preset_id,
        llm_adapter=adapter_name,
        fallback_note=fallback_note,
        metrics=getattr(used, "last_call_metrics", None),
    )


def list_demo_presets(language: str = "fi") -> list[dict[str, str]]:
    lang = language if language in {"fi", "en"} else "fi"
    return [{"id": pid, "question": texts[lang]} for pid, texts in DEMO_PRESETS.items()]
