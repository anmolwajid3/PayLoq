"""NL hints for revenue scale and one-off investments (FI + EN).

Code calculates figures; this only interprets description text so stub / weak
models do not invent oversized revenue or wrong capex amounts.
"""

from __future__ import annotations

import re
from typing import Any

from payloq_llm.nl_cash_intent import extract_euro_amounts

# Industry size → default monthly revenue start (EUR). Kept ≥ PARAM_RANGES floor (20k).
_INDUSTRY_REV_DEFAULTS: dict[str, float] = {
    "bakery": 32_000.0,
    "leipomo": 32_000.0,
    "leipuri": 32_000.0,
    "cafe": 28_000.0,
    "kahvila": 28_000.0,
    "restaurant": 55_000.0,
    "ravintola": 55_000.0,
    "hotel": 180_000.0,
    "hotelli": 180_000.0,
    "boutique": 180_000.0,
    "workshop": 200_000.0,
    "konepaja": 200_000.0,
    "metal": 200_000.0,
}

_SMALL_KEYS = ("small", "pieni", "pieno", "micro", "mikro")
_MEDIUM_KEYS = ("medium", "mid-size", "keskisuuri", "keski")
_LARGE_KEYS = ("large", "iso", "suuri")

_INVEST_CONTEXT: tuple[str, ...] = (
    "oven",
    "uuni",
    "uunikorj",
    "roof",
    "katto",
    "hvac",
    "repair",
    "remont",
    "korjaus",
    "capex",
    "invest",
    "investointi",
    "equipment",
    "laitteisto",
    "machine",
    "kone",
)

_MONTH_PATTERNS: tuple[str, ...] = (
    r"month\s*(?P<m>\d{1,2})",
    r"kuukaudessa\s*(?P<m>\d{1,2})",
    r"kuukausi(?:ssa)?\s*(?P<m>\d{1,2})",
    r"kk\s*(?P<m>\d{1,2})",
    r"in\s+month\s*(?P<m>\d{1,2})",
)


def _blob_industry(text: str, industry: str | None = None) -> str:
    return f"{text or ''} {industry or ''}".lower()


def looks_bakery(text: str, industry: str | None = None) -> bool:
    blob = _blob_industry(text, industry)
    return any(k in blob for k in ("bakery", "leipomo", "leipuri", "baker", "pastry", "leivon"))


def company_size_scale(text: str, company_size: str | None = None) -> float:
    """Multiplier on industry revenue default from size wording."""
    blob = f"{text or ''} {company_size or ''}".lower()
    if any(k in blob for k in _SMALL_KEYS):
        return 0.85
    if any(k in blob for k in _LARGE_KEYS):
        return 1.6
    if any(k in blob for k in _MEDIUM_KEYS):
        return 1.15
    return 1.0


def suggest_revenue_start_eur(
    text: str,
    *,
    industry: str | None = None,
    company_size: str | None = None,
) -> float | None:
    """
    Suggest monthly_revenue_start_eur from NL / industry.

    Prefer an explicit revenue figure in the text; else industry + size defaults.
    """
    blob = (text or "").lower()
    # Explicit revenue near liikevaihto / monthly revenue / turnover
    rev_ctx = (
        "liikevaihto",
        "monthly revenue",
        "revenue ~",
        "revenue €",
        "turnover",
        "myynti",
        "kuukausimyynti",
        "kuukausittainen",
    )
    for amt, idx in extract_euro_amounts(text):
        window = blob[max(0, idx - 40) : idx + 48]
        if any(c in window for c in rev_ctx) and 15_000 <= amt <= 500_000:
            return float(amt)

    industry_blob = _blob_industry(text, industry)
    base: float | None = None
    for key, default in _INDUSTRY_REV_DEFAULTS.items():
        if key in industry_blob:
            base = default
            break
    if base is None:
        if looks_bakery(text, industry):
            base = 32_000.0
        else:
            return None
    scaled = base * company_size_scale(text, company_size)
    # Stay inside typical PARAM_RANGES floor/ceiling without inventing tiny shops
    return float(max(20_000.0, min(500_000.0, round(scaled, -3))))


def extract_special_investment(text: str) -> tuple[float, int] | None:
    """
    Parse one-off capex/repair amount + 1-based month from NL.

    Examples:
      'Oven repair €42,000 in month 3' → (42000, 3)
      'Capex: €95,000 roof repair in month 2' → (95000, 2)
      'Uunikorjaus 42 000 € kuukaudessa 3' → (42000, 3)
    """
    blob = text or ""
    low = blob.lower()
    best: tuple[float, int, float] | None = None  # amount, month, score

    for amt, idx in extract_euro_amounts(text):
        if amt < 5_000 or amt > 2_000_000:
            continue
        window = low[max(0, idx - 56) : idx + 72]
        if not any(k in window for k in _INVEST_CONTEXT):
            continue
        # Skip thin cash / covenant figures even if "repair" is far away
        cashish = ("covenant", "kovenantti", "winter cash", "talvikassa", "target cash", "tavoitekassa")
        if any(c in window for c in cashish) and amt <= 40_000:
            # Prefer investment label proximity
            invest_pos = max((window.rfind(k) for k in _INVEST_CONTEXT if k in window), default=-1)
            cash_pos = max((window.rfind(k) for k in cashish if k in window), default=-1)
            amt_pos = min(56, len(window) - 1)
            if cash_pos >= 0 and abs(amt_pos - cash_pos) < abs(amt_pos - invest_pos):
                continue

        month = 2
        month_found = False
        for pat in _MONTH_PATTERNS:
            m = re.search(pat, window, flags=re.IGNORECASE)
            if m:
                try:
                    month = int(m.group("m"))
                    month_found = True
                    break
                except (TypeError, ValueError, IndexError):
                    continue
        if not (1 <= month <= 24):
            month = 2
        # Score: prefer amounts with explicit month + stronger invest words
        score = 1.0
        if month_found:
            score += 2.0
        if any(k in window for k in ("oven", "uuni", "roof", "katto", "hvac", "capex")):
            score += 1.5
        if best is None or score > best[2] or (score == best[2] and amt > best[0]):
            best = (amt, month, score)

    if best is None:
        return None
    return best[0], best[1]


def repair_investment_and_revenue_from_nl(
    text: str,
    params: dict[str, Any],
    *,
    industry: str | None = None,
    company_size: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pull special investment + revenue start toward NL when stub/LLM invents wrong scale."""
    data = dict(params)
    changes: list[dict[str, Any]] = []
    blob = text or ""

    inv = extract_special_investment(blob)
    if inv is not None:
        amt, month = inv
        try:
            cur = float(data.get("special_investment_eur") or 0)
        except (TypeError, ValueError):
            cur = 0.0
        # Replace default-ish invents (0, 70k, 80k) or large mismatches
        if cur <= 0 or abs(cur - amt) / max(amt, 1.0) > 0.15:
            changes.append(
                {
                    "field": "special_investment_eur",
                    "original": cur,
                    "clipped": amt,
                    "message": (
                        f"special_investment_eur repaired from {cur} to {amt} "
                        "using NL one-off / repair figure"
                    ),
                    "source": "nl_param_hints",
                }
            )
            data["special_investment_eur"] = amt
        try:
            cur_m = int(data.get("special_investment_month") or 2)
        except (TypeError, ValueError):
            cur_m = 2
        if cur_m != month:
            changes.append(
                {
                    "field": "special_investment_month",
                    "original": cur_m,
                    "clipped": month,
                    "message": (
                        f"special_investment_month repaired from {cur_m} to {month} "
                        "using NL month hint"
                    ),
                    "source": "nl_param_hints",
                }
            )
            data["special_investment_month"] = month
        # Keep one_off_events aligned when present / empty
        events = list(data.get("one_off_events") or [])
        label = "oven_repair" if looks_bakery(blob, industry) else "special_investment"
        if looks_bakery(blob, industry) or any(
            k in blob.lower() for k in ("oven", "uuni")
        ):
            label = "oven_repair"
        elif any(k in blob.lower() for k in ("roof", "katto", "hvac")):
            label = "roof_repair"
        matched = False
        for ev in events:
            if not isinstance(ev, dict):
                continue
            if str(ev.get("label") or "") in {label, "special_investment", "roof_repair", "oven_repair"}:
                ev["amount_eur"] = amt
                ev["month_index"] = month
                ev["direction"] = "out"
                ev["label"] = label
                matched = True
                break
        if not matched and amt > 0:
            events.append(
                {
                    "amount_eur": amt,
                    "month_index": month,
                    "direction": "out",
                    "label": label,
                }
            )
        data["one_off_events"] = events

    suggested_rev = suggest_revenue_start_eur(
        blob, industry=industry, company_size=company_size
    )
    if suggested_rev is not None:
        try:
            cur_rev = float(data.get("monthly_revenue_start_eur") or 0)
        except (TypeError, ValueError):
            cur_rev = 0.0
        # Oversized generic defaults (200k / 180k) for small bakery / small SME
        oversized = cur_rev <= 0 or (
            looks_bakery(blob, industry)
            and cur_rev >= 100_000
            and suggested_rev < 80_000
        )
        mild_over = cur_rev > suggested_rev * 2.5 and suggested_rev < 80_000
        if oversized or mild_over:
            changes.append(
                {
                    "field": "monthly_revenue_start_eur",
                    "original": cur_rev,
                    "clipped": suggested_rev,
                    "message": (
                        f"monthly_revenue_start_eur repaired from {cur_rev} to "
                        f"{suggested_rev} using NL / industry size hint"
                    ),
                    "source": "nl_param_hints",
                }
            )
            data["monthly_revenue_start_eur"] = suggested_rev

    return data, changes
