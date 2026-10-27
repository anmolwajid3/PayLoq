"""Prompt templates for NL → parameters and descriptive invoice texts."""

from __future__ import annotations

import json
from typing import Any

PARAM_SCHEMA_HINT = """
Return ONLY a JSON object with these keys (no markdown, no commentary):
{
  "monthly_revenue_start_eur": <positive number>,
  "monthly_revenue_growth": <monthly growth rate, e.g. 0.008 or -0.012>,
  "cost_shares_of_revenue": {
    "materials": <0-1>,
    "services": <0-1>,
    "personnel": <0-1>,
    "other": <0-1>
  },
  "days_sales_outstanding": <positive number, typical 30-50>,
  "days_payables_outstanding": <positive number, typical 25-40>,
  "target_cash_at_end_eur": <number, can be low for cash-critical>,
  "special_investment_eur": <number, 0 if none>,
  "notes": "<short English or Finnish note>",
  "partly_fixed_costs": <true|false — true when costs stay high while revenue falls or cash is critical>
}
Cost shares should sum roughly to 0.85–0.95. Do not invent absolute P&L or balance-sheet figures —
code will compute those from these parameters.
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
Do NOT include amounts, dates, VAT, or IDs — code owns all numbers.
""".strip()


def parameter_extraction_prompt(
    description_fi: str,
    description_en: str,
    options: dict[str, Any],
) -> str:
    return (
        "You map a short company situation into structured generator parameters for PayLoq.\n"
        "Finnish support is required: read both FI and EN descriptions.\n"
        "Code calculates all financial figures; you only choose parameters.\n\n"
        f"Description (FI):\n{description_fi}\n\n"
        f"Description (EN):\n{description_en}\n\n"
        f"Options JSON:\n{json.dumps(options, ensure_ascii=False)}\n\n"
        f"{PARAM_SCHEMA_HINT}\n"
    )


def parameter_repair_prompt(previous: str, error: str) -> str:
    return (
        "Your previous JSON was invalid for PayLoq parameters.\n"
        f"Validation error:\n{error}\n\n"
        f"Previous response:\n{previous}\n\n"
        "Return corrected JSON only, matching the required schema.\n"
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
        "Numbers (amounts, dates, VAT) are produced by code — you supply text only.\n\n"
        f"Industry: {industry}\n"
        f"Preferred language for texts: {language}\n"
        f"Description (FI):\n{description_fi}\n\n"
        f"Description (EN):\n{description_en}\n\n"
        f"{TEXTS_SCHEMA_HINT}\n"
    )


def interpretation_prompt(question: str, pack_summary: dict[str, Any]) -> str:
    return (
        "Answer as a careful virtual accountant. Use ONLY the provided figures.\n"
        "Do not invent causes that are not supported by the numbers.\n"
        "Reply in Finnish if the question is Finnish; otherwise English. Keep it short.\n\n"
        f"Figures JSON:\n{json.dumps(pack_summary, ensure_ascii=False)}\n\n"
        f"Question:\n{question}\n"
    )
