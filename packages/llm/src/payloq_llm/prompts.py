"""Prompt templates for NL → parameters and descriptive invoice texts."""

from __future__ import annotations

import json
from typing import Any

PARAM_SCHEMA_HINT = """
Return ONLY a JSON object matching this schema (no markdown, no commentary).
Every field the description does not state is null. NEVER use 0 for an unstated value.
The model returns only numbers written in the description.
The model never calculates, converts, annualises, or infers.
Code derives annual from monthly, the decimal from a percent, and days from weeks or months.
{
  "scenario_shape": "healthy" | "weak" | "cash_tight" | "cash_critical" | "unspecified",
  "scenario_shape_quote": "exact words from the description, or null",
  "stated": { "<field name>": "exact quote from the description" },
  "parameters": {
    "revenue_monthly_eur": number | null,
    "revenue_annual_eur": number | null,
    "growth_per_month_percent": number | null,
    "starting_cash_eur": number | null,
    "covenant_min_cash_eur": number | null,
    "dso_days": number | null,
    "dpo_days": number | null,
    "one_off_events": [
      {"type": string, "amount_eur": number, "month_index": integer,
       "direction": "inflow" | "outflow"}
    ],
    "industry": string | null,
    "company_size": string | null
  }
}
HARD RULES:
- Only list a field in "stated" if the description states it. Every other field is null.
- Return the number that is written. Do not multiply, divide, or change units.
- revenue_monthly_eur is the monthly figure only. Never annual/12. Null if only annual is written.
- revenue_annual_eur is the annual figure only. Never monthly*12. Null if only monthly is written.
- growth_per_month_percent is the percent as written (0.5 for "0.5%"), never the decimal 0.005.
- dso_days/dpo_days only when the text says days. Weeks go in dso_weeks/dpo_weeks.
  Months go in dso_months/dpo_months. Do not convert weeks or months into days.
- If starting_cash_eur is not stated, return null (code will assume it).
- CAPEX / investment one-offs use direction "outflow".
- When the description states a one-off with amount, month, and inflow/outflow,
  you MUST return that event (never an empty list).
- Do not invent absolute P&L or balance-sheet figures — code computes those.
""".strip()


TEXTS_SCHEMA_HINT = """
Return ONLY a JSON object with these keys (no markdown, no commentary):
{
  "sales_counterparties": ["…", …],   // at least 8 fictional Finnish company names (Oy)
  "purchase_counterparties": ["…", …], // at least 8 fictional Finnish suppliers (Oy)
  "sales_descriptions": ["…", …],      // at least 6 short invoice line descriptions
  "purchase_descriptions": ["…", …],   // at least 6 short invoice line descriptions
  "language": "fi" | "en",
  "notes": "<optional>"
}
Use ONLY synthetic / fictional names. Prefer Finnish (fi) company-style names unless language is en.
HARD RULES for every string:
- Do NOT write any digits (0-9), euro amounts (€ / EUR), room counts, day counts, or percentages.
- Do NOT copy or paste the company description text into counterparties or invoice lines.
- Keep each description short (a few words). Code owns all numbers (amounts, dates, IDs).
""".strip()


def parameter_extraction_prompt(
    description_fi: str,
    description_en: str,
    options: dict[str, Any],
) -> str:
    return (
        "You map a short company situation into structured generator parameters for PayLoq.\n"
        "Finnish support is required: read both FI and EN descriptions.\n"
        "Code calculates all financial figures; you only extract stated parameters.\n"
        "Return null for every field the description does not state.\n"
        "Never calculate, convert, annualise, or infer. Never use 0 for an unstated value.\n\n"
        f"Description (FI):\n{description_fi}\n\n"
        f"Description (EN):\n{description_en}\n\n"
        f"Options JSON:\n{json.dumps(options, ensure_ascii=False)}\n\n"
        f"{PARAM_SCHEMA_HINT}\n"
    )


def parameter_repair_prompt(previous: str, error: str) -> str:
    return (
        "Your previous JSON failed PayLoq parameter checks (schema and/or value grounding).\n"
        f"Error:\n{error}\n\n"
        f"Previous response:\n{previous}\n\n"
        "Return corrected JSON only (section B schema). Use null for every unstated field. "
        "Do not calculate, convert, annualise, or infer. "
        "Every stated number MUST appear in the description after parsing units "
        "(k, M, million, %, €). Return the written percent, not a decimal; "
        "do not turn monthly into annual or weeks into days. "
        "Quotes are optional — do not invent quote text. "
        "If the description states a one-off with amount, month, and direction, "
        "include that event. Do not invent defaults. Do not retry with the same wrong numbers.\n"
    )


def parameter_grounding_repair_prompt(previous: str, grounding_error: str) -> str:
    return (
        "Value grounding failed: stated numbers must appear in the description "
        "after parsing units (k, M, million, %, €). Quotes are optional.\n"
        f"{grounding_error}\n\n"
        f"Previous response:\n{previous}\n\n"
        "Return corrected JSON only. Fix the named fields. Use null when unstated.\n"
    )


def descriptive_texts_prompt(
    *,
    description_fi: str,
    description_en: str,
    industry: str,
    language: str,
) -> str:
    return (
        "You write fictional Finnish SME invoice counterparties and line descriptions for PayLoq.\n"
        "Numbers (amounts, dates, VAT, IDs) are produced by code — you supply text only.\n"
        "Use the descriptions only to infer industry flavour. "
        "Never paste description phrases that contain digits or € amounts into the JSON strings.\n\n"
        f"Industry: {industry}\n"
        f"Preferred language for texts: {language}\n"
        f"Description (FI):\n{description_fi}\n\n"
        f"Description (EN):\n{description_en}\n\n"
        f"{TEXTS_SCHEMA_HINT}\n"
    )


INTERPRETATION_SYSTEM = """
You are a careful virtual accountant for PayLoq.
Code already computed every number. You ONLY interpret the Figures JSON the user provides.
""".strip()


def interpretation_prompt(question: str, pack_summary: dict[str, Any]) -> str:
    return (
        "HARD RULES — follow all of them:\n"
        "1. Answer ONLY from the Figures JSON below. Do not use outside knowledge.\n"
        "2. NEVER define accounting terms or paraphrase field names as definitions "
        "(forbidden example: \"Cash goes negative when the balance history change is negative.\").\n"
        "3. Every answer must cite at least one concrete date or week number AND one euro (€ / EUR) "
        "amount taken from the figures.\n"
        "4. When asked when cash goes negative / milloin kassa menee negatiiviseksi: "
        "use first_negative_date and first_negative_balance (EUR). "
        "If those are null, also check first_negative_projection_week, "
        "first_negative_projection_week_end, and first_negative_projection_balance. "
        "If all are null, say the pack does not show cash going negative.\n"
        "5. When asked why cash dropped / miksi kassa laski: cite mom_cash_change and/or "
        "balance_history_change and/or largest_weekly_cash_drops (from_date → to_date, delta) "
        "and special_investment_eur when present — as numbers, not definitions.\n"
        "6. Do not invent causes (customers leaving, bank freezes, fraud, etc.).\n"
        "7. Reply in Finnish if the question is Finnish; otherwise English. Keep it short (2–4 sentences).\n\n"
        f"Figures JSON:\n{json.dumps(pack_summary, ensure_ascii=False)}\n\n"
        f"Question:\n{question}\n"
    )
