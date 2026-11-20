"""Prompt templates for NL → parameters and descriptive invoice texts."""

from __future__ import annotations

import json
from typing import Any

PARAM_SCHEMA_HINT = """
Return ONLY a JSON object matching this schema (no markdown, no commentary).
null if the description does not state the value. NEVER use 0 for an unstated value.
Never put one number in two fields. Do not calculate. Do not convert annual to monthly.
{
  "scenario_shape": "healthy" | "weak" | "cash_tight" | "cash_critical" | "unspecified",
  "scenario_shape_quote": "exact words from the description, or null",
  "stated": { "<field name>": "exact quote from the description" },
  "parameters": {
    "revenue_monthly_eur": number | null,
    "revenue_annual_eur": number | null,
    "growth_per_month_fraction": number | null,
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
- Only list a field in "stated" if the description states it; give the exact quote.
- Extract ONLY numbers that appear in the description (after k/M/million/%/€ parsing).
- If starting_cash_eur is not stated, return null (code will assume it).
- CAPEX / investment one-offs use direction "outflow".
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
        "Return null for unstated fields. Never invent defaults or company-specific guesses.\n"
        "Never use 0 for an unstated value.\n\n"
        f"Description (FI):\n{description_fi}\n\n"
        f"Description (EN):\n{description_en}\n\n"
        f"Options JSON:\n{json.dumps(options, ensure_ascii=False)}\n\n"
        f"{PARAM_SCHEMA_HINT}\n"
    )


def parameter_repair_prompt(previous: str, error: str) -> str:
    return (
        "Your previous JSON failed PayLoq parameter checks (schema and/or stated-quote).\n"
        f"Error:\n{error}\n\n"
        f"Previous response:\n{previous}\n\n"
        "Return corrected JSON only (section B schema). Use null for unstated fields. "
        "Every field in stated must have an exact quote from the description, and the "
        "value must appear in that quote after parsing units (k, M, million, %, €). "
        "Do not invent defaults. Do not retry with the same wrong numbers.\n"
    )


def parameter_grounding_repair_prompt(previous: str, grounding_error: str) -> str:
    return (
        "Stated-quote check failed: quotes must appear in the description and values "
        "must appear in those quotes.\n"
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
