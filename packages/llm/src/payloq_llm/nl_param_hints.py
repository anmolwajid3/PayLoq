"""NL hints for revenue scale, growth, and one-off investments (FI + EN).

Code calculates figures; this only interprets description text so stub / weak
models do not invent oversized SME revenue or crush mid-market millions.
"""

from __future__ import annotations

import re
from typing import Any

from payloq_llm.nl_cash_intent import extract_euro_amounts
from payloq_schemas.constants import PARAM_RANGES
from payloq_schemas.company_size import scale_defaults_for_size

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
    # Mid-market manufacturing — size band still scales this further.
    "steel": 1_200_000.0,
    "teräs": 1_200_000.0,
    "teras": 1_200_000.0,
    "fabricat": 1_200_000.0,
    "valmistus": 1_200_000.0,
    "manufactur": 1_200_000.0,
}

_SMALL_KEYS = ("small", "pieni", "pieno", "micro", "mikro")
_MEDIUM_KEYS = ("medium", "mid-size", "midmarket", "mid-market", "keskisuuri", "keski")
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
    "line",
    "production line",
    "tuotantolinja",
    "press",
    "puristin",
    "one-off",
    "kertaluonteinen",
)

_MONTH_PATTERNS: tuple[str, ...] = (
    r"month\s*(?P<m>\d{1,2})",
    r"kuukaudessa\s*(?P<m>\d{1,2})",
    r"kuukausi(?:ssa)?\s*(?P<m>\d{1,2})",
    r"kk\s*(?P<m>\d{1,2})",
    r"in\s+month\s*(?P<m>\d{1,2})",
)

_REV_LO, _REV_HI = PARAM_RANGES["monthly_revenue_start_eur"]
_INV_LO, _INV_HI = PARAM_RANGES["special_investment_eur"]


def _blob_industry(text: str, industry: str | None = None) -> str:
    return f"{text or ''} {industry or ''}".lower()


def looks_bakery(text: str, industry: str | None = None) -> bool:
    blob = _blob_industry(text, industry)
    return any(k in blob for k in ("bakery", "leipomo", "leipuri", "baker", "pastry", "leivon"))


def looks_steel_or_manufacturing(text: str, industry: str | None = None) -> bool:
    blob = _blob_industry(text, industry)
    return any(
        k in blob
        for k in (
            "steel",
            "teräs",
            "teras",
            "fabricat",
            "konepaja",
            "metal",
            "manufactur",
            "valmistus",
            "workshop",
        )
    )


def company_size_scale(text: str, company_size: str | None = None) -> float:
    """Multiplier on industry revenue default from size wording."""
    blob = f"{text or ''} {company_size or ''}".lower()
    if any(k in blob for k in _SMALL_KEYS):
        return 0.85
    if any(k in blob for k in _LARGE_KEYS) or re.search(r"\b([3-9]\d{2}|\d{4,})\b", blob):
        # Explicit large label or 300+ headcount → mid-market scale
        return 1.6
    if any(k in blob for k in _MEDIUM_KEYS):
        return 1.15
    return 1.0


def extract_growth_rate(text: str) -> float | None:
    """
    Parse monthly revenue growth from NL.

    Examples: 'growth ~0.3%/month', 'kasvu 0,3 %', '0.3 percent moM'.
    Returns a fraction (0.003 for 0.3%), clamped to PARAM_RANGES.
    """
    blob = text or ""
    patterns = [
        r"(?:growth|kasvu|revenue growth|liikevaihdon kasvu)\s*[~≈:]?\s*"
        r"(-?\d+[.,]?\d*)\s*%",
        r"(-?\d+[.,]?\d*)\s*%\s*(?:/\s*month|per month|/kk|kuukaudessa|mom|mo\b)",
        r"(-?\d+[.,]?\d*)\s*(?:percent|prosenttia)\s*"
        r"(?:/\s*month|per month|kuukaudessa|mom)?",
    ]
    lo, hi = PARAM_RANGES["monthly_revenue_growth"]
    for pat in patterns:
        m = re.search(pat, blob, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            pct = float(m.group(1).replace(",", "."))
        except (TypeError, ValueError):
            continue
        # Values like 0.3 mean 0.3%; values like 0.003 already fraction-like near %
        if abs(pct) <= 0.05 and "%" not in m.group(0):
            growth = pct
        else:
            growth = pct / 100.0
        return float(min(hi, max(lo, growth)))
    return None


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
        "revenue ~€",
        "turnover",
        "myynti",
        "kuukausimyynti",
        "kuukausittainen",
        "kuukausiliikevaihto",
    )
    for amt, idx in extract_euro_amounts(text):
        window = blob[max(0, idx - 48) : idx + 56]
        if any(c in window for c in rev_ctx) and _REV_LO <= amt <= _REV_HI:
            return float(amt)

    # No explicit euro revenue — only invent industry defaults where SME scale
    # matters (bakery). Workshop/steel without figures defer to size-band stub defaults
    # so large/420 stays on scale_defaults_for_size (and small konepaja stays 200k).
    if looks_bakery(text, industry):
        base = 32_000.0
        scaled = base * company_size_scale(text, company_size)
        return float(max(_REV_LO, min(_REV_HI, round(scaled, -3))))

    industry_blob = _blob_industry(text, industry)
    cafe_keys = ("cafe", "kahvila", "restaurant", "ravintola")
    for key in cafe_keys:
        if key in industry_blob:
            base = _INDUSTRY_REV_DEFAULTS[key]
            scaled = base * company_size_scale(text, company_size)
            return float(max(_REV_LO, min(_REV_HI, round(scaled, -3))))

    # Hotel without explicit revenue: mild size-aware default
    if any(k in industry_blob for k in ("hotel", "hotelli", "boutique")):
        try:
            band_defaults = scale_defaults_for_size(company_size or "small")
            base = float(band_defaults["monthly_revenue_start_eur"])
            if band_defaults.get("band") == "small":
                base = max(base, 180_000.0)
        except Exception:
            base = 180_000.0
        return float(max(_REV_LO, min(_REV_HI, round(base, -3))))

    return None


_REVENUE_CONTEXT: tuple[str, ...] = (
    "revenue",
    "liikevaihto",
    "turnover",
    "myynti",
    "sales",
    "monthly revenue",
    "kuukausiliikevaihto",
)

# Strong one-off markers — prefer these over weak tokens like "line" / "invest".
_STRONG_INVEST: tuple[str, ...] = (
    "capex",
    "one-off",
    "one off",
    "kertaluonteinen",
    "oven",
    "uuni",
    "uunikorj",
    "roof",
    "katto",
    "kattoremont",
    "hvac",
    "production line",
    "tuotantolinja",
)

_CASHISH_CONTEXT: tuple[str, ...] = (
    "covenant",
    "kovenantti",
    "winter cash",
    "talvikassa",
    "target cash",
    "tavoitekassa",
    "trough",
    "talvipohja",
    "kassapohja",
    "starting cash",
    "alkukassa",
    "minimum cash",
    "cash ~",
    "cash trough",
)

# Short tokens that appear inside unrelated words (oven⊂covenant, line⊂airline).
_WHOLE_WORD_INVEST: frozenset[str] = frozenset(
    {"oven", "uuni", "line", "press", "machine", "invest", "repair"}
)


def _keyword_positions(window: str, keywords: tuple[str, ...]) -> list[tuple[str, int]]:
    """Return (keyword, start_index) hits; short ambiguous tokens need word boundaries."""
    hits: list[tuple[str, int]] = []
    for k in keywords:
        if k in _WHOLE_WORD_INVEST:
            for m in re.finditer(rf"(?<![a-zäöå]){re.escape(k)}(?![a-zäöå])", window):
                hits.append((k, m.start()))
            continue
        start = 0
        while True:
            found = window.find(k, start)
            if found < 0:
                break
            hits.append((k, found))
            start = found + 1
    return hits


def _nearest_keyword_distance(window: str, amt_pos: int, keywords: tuple[str, ...]) -> int | None:
    """Distance from amount position to the nearest keyword occurrence in window."""
    best: int | None = None
    for _k, found in _keyword_positions(window, keywords):
        dist = abs(found - amt_pos)
        if best is None or dist < best:
            best = dist
    return best


def _nearest_left_distance(window: str, amt_pos: int, keywords: tuple[str, ...]) -> int | None:
    """Distance to the nearest keyword that starts at or before the amount."""
    best: int | None = None
    for _k, found in _keyword_positions(window, keywords):
        if found > amt_pos:
            continue
        dist = amt_pos - found
        if best is None or dist < best:
            best = dist
    return best


def _window_has_invest(window: str) -> bool:
    return bool(_keyword_positions(window, _INVEST_CONTEXT))


# Opening / starting cash wording (EN + FI). Distinct from covenant / winter trough.
_STARTING_CASH_CONTEXT: tuple[str, ...] = (
    "starting cash",
    "opening cash",
    "initial cash",
    "cash at start",
    "cash at opening",
    "beginning cash",
    "alkukassa",
    "aloituskassa",
    "avauskassa",
    "alkusaldo",
    "kassa alussa",
    "kassa alussa on",
)

# Labels that mark covenant / trough / target — never treat as starting cash.
_NOT_STARTING_CASH_CONTEXT: tuple[str, ...] = (
    "covenant",
    "kovenantti",
    "minimum cash",
    "min cash",
    "winter cash",
    "talvikassa",
    "target cash",
    "tavoitekassa",
    "ending cash",
    "trough",
    "talvipohja",
    "kassapohja",
    "capex",
    "invest",
    "investointi",
    "repair",
    "korjaus",
    "monthly revenue",
    "liikevaihto",
    "revenue",
)


def extract_starting_cash_eur(text: str) -> float | None:
    """
    Parse ``starting_cash_eur`` from NL when explicitly labeled.

    Matches EN/FI: Starting cash / opening cash / alkukassa / aloituskassa, etc.
    Does not invent a figure and does not treat covenant / CAPEX / revenue amounts
    as opening cash.

    Examples:
      'Starting cash €45,000' → 45000
      'Alkukassa 45 000 €' → 45000
      'Opening cash €1.3M' → 1300000
    """
    blob = text or ""
    low = blob.lower()
    best: tuple[float, float] | None = None  # amount, score (higher better)

    for amt, idx in extract_euro_amounts(text):
        if amt < 1_000:
            continue
        left = max(0, idx - 64)
        window = low[left : idx + 48]
        amt_pos = idx - left

        start_left = _nearest_left_distance(window, amt_pos, _STARTING_CASH_CONTEXT)
        start_dist = _nearest_keyword_distance(window, amt_pos, _STARTING_CASH_CONTEXT)
        if start_left is None and start_dist is None:
            continue

        # Prefer labels immediately before the amount (Starting cash €45k).
        not_left = _nearest_left_distance(window, amt_pos, _NOT_STARTING_CASH_CONTEXT)
        if not_left is not None and (start_left is None or not_left < start_left):
            continue

        score = 2.0 if start_left is not None else 1.0
        if start_left is not None:
            score += max(0.0, 1.5 - (start_left / 40.0))
        elif start_dist is not None:
            score += max(0.0, 0.8 - (start_dist / 50.0))
        if best is None or score > best[1] or (score == best[1] and amt > best[0]):
            best = (float(amt), score)

    return None if best is None else best[0]


def repair_starting_cash_from_nl(
    text: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    If LLM omitted ``starting_cash_eur`` but NL states it, fill with source=stated.

    Does not invent a value when the description has no starting-cash figure.
    """
    data = dict(params)
    changes: list[dict[str, Any]] = []
    cur = data.get("starting_cash_eur")
    if cur not in (None, ""):
        return data, changes

    parsed = extract_starting_cash_eur(text or "")
    if parsed is None:
        return data, changes

    data["starting_cash_eur"] = parsed
    sources = dict(data.get("field_sources") or {})
    sources["starting_cash_eur"] = "stated"
    data["field_sources"] = sources
    changes.append(
        {
            "field": "starting_cash_eur",
            "original": None,
            "clipped": parsed,
            "message": (
                f"starting_cash_eur repaired from null to {parsed} "
                "using NL starting/opening cash / alkukassa figure"
            ),
            "source": "nl_param_hints",
        }
    )
    return data, changes


def extract_special_investment(text: str) -> tuple[float, int] | None:
    """
    Parse one-off capex/repair amount + 1-based month from NL.

    Examples:
      'Oven repair €42,000 in month 3' → (42000, 3)
      'Capex: €95,000 roof repair in month 2' → (95000, 2)
      'Uunikorjaus 42 000 € kuukaudessa 3' → (42000, 3)
      'One-off CAPEX €2.8M in month 4' → (2800000, 4)

    Prefer the amount nearest to CAPEX/one-off wording. Do not treat monthly
    revenue (e.g. €180k) as investment when a real CAPEX (e.g. €80k month 3)
    is stated — including when FI+EN copies are concatenated (Run #19).
    """
    blob = text or ""
    low = blob.lower()
    # amount, month, score, left_proximity (lower better)
    best: tuple[float, int, float, int] | None = None

    for amt, idx in extract_euro_amounts(text):
        if amt < 5_000 or amt > _INV_HI:
            continue
        left = max(0, idx - 56)
        window = low[left : idx + 72]
        amt_pos = idx - left
        if not _window_has_invest(window):
            continue

        strong_left = _nearest_left_distance(window, amt_pos, _STRONG_INVEST)
        strong_dist = _nearest_keyword_distance(window, amt_pos, _STRONG_INVEST)
        invest_dist = _nearest_keyword_distance(window, amt_pos, _INVEST_CONTEXT)
        rev_left = _nearest_left_distance(window, amt_pos, _REVENUE_CONTEXT)
        cash_left = _nearest_left_distance(window, amt_pos, _CASHISH_CONTEXT)

        # Skip revenue / turnover figures (left-context) even when a CAPEX phrase
        # from the next sentence falls inside the right side of the window.
        if rev_left is not None and (strong_left is None or rev_left < strong_left):
            continue

        # Skip covenant / winter-cash figures: cash wording immediately before the
        # amount beats a following CAPEX phrase ("…€8k. Oven repair €42k…").
        if cash_left is not None and cash_left <= 28 and (
            strong_left is None or cash_left <= strong_left
        ):
            continue

        # Require a strong one-off marker to the left of the amount (same phrase).
        # Weak tokens alone ("invest", "line") are too noisy next to covenants.
        if strong_left is None or strong_left > 40:
            continue

        month = 2
        month_found = False
        # Prefer a month pattern near the amount / after the invest keyword.
        month_window = window[max(0, amt_pos - 10) : amt_pos + 72]
        for pat in _MONTH_PATTERNS:
            m = re.search(pat, month_window, flags=re.IGNORECASE)
            if m:
                try:
                    month = int(m.group("m"))
                    month_found = True
                    break
                except (TypeError, ValueError, IndexError):
                    continue
        if not month_found:
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

        # Score: left-side strong invest proximity + explicit month.
        score = 3.0
        proximity = strong_left
        if month_found:
            score += 2.0
        if strong_left <= 24:
            score += 2.0
        if strong_dist is not None and strong_dist <= 12:
            score += 0.5
        if invest_dist is not None and invest_dist <= 16:
            score += 0.25
        if amt >= 1_000_000:
            score += 0.5

        candidate = (amt, month, score, proximity)
        if best is None:
            best = candidate
            continue
        if score > best[2]:
            best = candidate
        elif score == best[2]:
            if proximity < best[3]:
                best = candidate
            elif proximity == best[3] and amt < best[0]:
                best = candidate

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
        # Replace default-ish invents (0, 70k, 80k) or large mismatches either way
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
        label = "special_investment"
        low_blob = blob.lower()
        # Word-boundary match: bare "oven" must not hit "covenant".
        if looks_bakery(blob, industry) or re.search(r"(?<![a-z])(oven|uuni)\b", low_blob):
            label = "oven_repair"
        elif any(k in low_blob for k in ("roof", "katto", "hvac")):
            label = "roof_repair"
        elif any(
            k in low_blob
            for k in ("production line", "tuotantolinja", "capex", "steel", "teräs")
        ):
            label = "capex_line"
        matched = False
        for ev in events:
            if not isinstance(ev, dict):
                continue
            if str(ev.get("label") or "") in {
                label,
                "special_investment",
                "roof_repair",
                "oven_repair",
                "capex_line",
            }:
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
        # Undersized SME invents for mid-market / steel NL stating millions
        undersized = suggested_rev >= 1_000_000 and (
            cur_rev <= 0 or cur_rev < suggested_rev * 0.5
        )
        if oversized or mild_over or undersized:
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

    nl_growth = extract_growth_rate(blob)
    if nl_growth is not None:
        try:
            cur_g = float(data.get("monthly_revenue_growth") or 0)
        except (TypeError, ValueError):
            cur_g = 0.0
        if abs(cur_g - nl_growth) > 1e-6:
            changes.append(
                {
                    "field": "monthly_revenue_growth",
                    "original": cur_g,
                    "clipped": nl_growth,
                    "message": (
                        f"monthly_revenue_growth repaired from {cur_g} to {nl_growth} "
                        "using NL growth figure"
                    ),
                    "source": "nl_param_hints",
                }
            )
            data["monthly_revenue_growth"] = nl_growth

    return data, changes
