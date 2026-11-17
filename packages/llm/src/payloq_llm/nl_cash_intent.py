"""NL cash-stress intent + covenant / thin-cash amount hints (FI + EN).

Code calculates figures; this module only interprets description text so stub /
weak models do not invent healthy-cash defaults that contradict the story.
"""

from __future__ import annotations

import re
from typing import Any

# Strong cash-stress cues (EN + FI). Keep in sync with generator / validate heuristics.
CASH_CRITICAL_KEYWORDS: tuple[str, ...] = (
    "kriittinen",
    "critical",
    "negatiiv",
    "kolmen viikon",
    "three weeks",
    "cash tight",
    "cash critical",
    "tight cash",
    "tiukalla",
    "tiukka kassa",
    "kassa tiuk",
    "covenant",
    "kovenantti",
    "runs out of cash",
    "kassa loppuu",
    "winter cash",
    "ohut kassa",
    "thin cash",
    "thin winter",
    "cash stressed",
    "kassakriisi",
    "supplier bill cluster",
    "within weeks",
    "viikon päästä",
    "cash cliff",
    "kassa romaht",
)

# Softer cues that, together with a low cash figure or hotel/winter collapse, imply stress.
SOFT_CASH_STRESS_KEYWORDS: tuple[str, ...] = (
    "winter",
    "talvi",
    "off-season",
    "sesongin",
    "collapse",
    "romaht",
    "occupancy",
    "hotelli",
    "hotel",
    "bank",
    "pankki",
)

# Words near a euro amount that mark it as a cash / covenant target (not revenue/ADR).
CASH_AMOUNT_CONTEXT: tuple[str, ...] = (
    "covenant",
    "kovenantti",
    "cash",
    "kassa",
    "talvikassa",
    "winter cash",
    "talvi",
    "thin",
    "ohut",
    "bank",
    "pankki",
    "pankin",
    "target cash",
    "tavoitekassa",
    "ending cash",
    "supplier bill",
    "ostolask",
)

# Amounts that look like ADR / room rates / occupancy — not cash targets.
# Avoid bare "room" (matches "12-room" hotel size far from the cash figure).
_SKIP_NEAR: tuple[str, ...] = (
    "adr",
    "occupancy",
    "room rate",
    "per night",
    "per room",
    "/night",
    "huonehinta",
    "liikevaihto",
    "monthly revenue",
    "revenue €",
    "revenue ~",
)


def looks_cash_critical(text: str) -> bool:
    """True when the NL description is a cash-stressed / covenant story."""
    blob = (text or "").lower()
    if any(k in blob for k in CASH_CRITICAL_KEYWORDS):
        return True
    # Soft path: winter/hotel collapse + a low cash-like figure in the text
    soft = any(k in blob for k in SOFT_CASH_STRESS_KEYWORDS)
    if not soft:
        return False
    hints = extract_cash_target_hints(text)
    return bool(hints) and min(hints) <= 80_000


def extract_euro_amounts(text: str) -> list[tuple[float, int]]:
    """
    Parse euro-ish amounts from NL.

    Returns list of (amount_eur, start_index) for context windows.
    Supports: €25k, 25,000 €, ~€30k, 25000, 25 000 euroa.
    """
    blob = text or ""
    found: list[tuple[float, int]] = []
    patterns = [
        # €25,000 / €25.000 / €25000 / €25k / €25 k
        r"[€]\s*~?\s*(\d{1,3}(?:[.,\s]\d{3})*|\d+)(?:\s*[kK])?",
        # 25,000 € / 25k EUR / 25000 euroa (no \b after € — € is non-word)
        r"~?\s*(\d{1,3}(?:[.,\s]\d{3})*|\d+)\s*[kK]?\s*(?:€|euros?\b|euroa\b)",
        # bare 25k / 30k near cash words — handled with context filter later
        r"\b(\d{1,3})\s*[kK]\b",
        r"\b(\d{4,6})\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, blob, flags=re.IGNORECASE):
            raw = m.group(1)
            has_k = bool(re.search(r"[kK]\s*(?:€|eur|euroa)?\s*$", m.group(0))) or bool(
                re.search(r"[kK]\b", m.group(0))
            )
            # Normalize thousands separators
            digits = re.sub(r"[.\s]", "", raw.replace(",", ""))
            # European 25.000 → 25000 already stripped dots; 25,000 with comma-as-thousands:
            if "," in raw and "." not in raw and len(raw.split(",")[-1]) == 3:
                digits = raw.replace(",", "")
            elif "," in raw and "." not in raw:
                digits = raw.replace(",", "")
            try:
                val = float(re.sub(r"[^\d]", "", digits) or "0")
            except ValueError:
                continue
            if has_k and val < 1000:
                val *= 1000.0
            if val < 1_000 or val > 2_000_000:
                continue
            found.append((val, m.start()))
    # De-dupe by amount+nearby index
    uniq: list[tuple[float, int]] = []
    seen: set[tuple[float, int]] = set()
    for amt, idx in found:
        key = (round(amt, -2), idx // 8)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((amt, idx))
    return uniq


def extract_cash_target_hints(text: str) -> list[float]:
    """Euro amounts that sit near cash/covenant wording (not ADR/revenue)."""
    blob = (text or "").lower()
    hints: list[float] = []
    for amt, idx in extract_euro_amounts(text):
        window = blob[max(0, idx - 48) : idx + 56]
        has_cash_ctx = any(c in window for c in CASH_AMOUNT_CONTEXT)
        has_skip = any(s in window for s in _SKIP_NEAR)
        # Capex / roof figures are investments, not target cash.
        invest_keys = ("roof", "katto", "capex", "repair", "remont", "hvac", "invest")
        invest_hits = [window.rfind(k) for k in invest_keys if k in window]
        covenant_keys = ("covenant", "kovenantti", "target cash", "tavoitekassa", "talvikassa", "winter cash")
        cov_hits = [window.rfind(k) for k in covenant_keys if k in window]
        # Amount sits at ~48 chars into the window; prefer nearest label.
        amt_pos = min(48, len(window) - 1)
        if invest_hits and amt >= 50_000:
            nearest_invest = max(invest_hits)
            nearest_cov = max(cov_hits) if cov_hits else -999
            if abs(amt_pos - nearest_invest) <= abs(amt_pos - nearest_cov):
                continue
        # Prefer cash/covenant context; skip ADR/revenue-adjacent amounts.
        if has_cash_ctx:
            hints.append(amt)
    return hints


def suggested_target_cash_eur(text: str) -> float | None:
    """
    Best target_cash_at_end_eur hint from NL.

    Prefer covenant / winter-cash figures in the thin-cash band (~10k–80k).
    """
    hints = extract_cash_target_hints(text)
    if not hints:
        return None
    thin = [h for h in hints if 5_000 <= h <= 80_000]
    if thin:
        # Covenant is often the lower bound; winter cash ~30k — use the min thin hint
        return float(min(thin))
    if looks_cash_critical(text):
        return float(min(hints))
    return None


def repair_params_from_nl(
    text: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Soft-repair extracted parameters that contradict a cash-stressed description.

    - Pull target_cash toward covenant / winter-cash figures in the NL.
    - Mark partly_fixed_costs when cash-critical.
    - Do not invent revenue or investments that are absent from params/text.
    """
    data = dict(params)
    changes: list[dict[str, Any]] = []
    blob = text or ""
    critical = looks_cash_critical(blob)
    suggested = suggested_target_cash_eur(blob)

    try:
        cash = float(data.get("target_cash_at_end_eur") or 0)
    except (TypeError, ValueError):
        cash = 0.0

    if suggested is not None and (critical or cash > 80_000):
        # Only pull absurdly high targets down; never inflate a low model guess.
        if cash <= 0 or cash > suggested * 1.5 or (critical and cash > 80_000):
            new_cash = suggested
            if abs(new_cash - cash) > 1.0:
                changes.append(
                    {
                        "field": "target_cash_at_end_eur",
                        "original": cash,
                        "clipped": new_cash,
                        "message": (
                            f"target_cash_at_end_eur repaired from {cash} to {new_cash} "
                            "using NL covenant/winter-cash figure"
                        ),
                        "source": "nl_cash_intent",
                    }
                )
                data["target_cash_at_end_eur"] = new_cash
                cash = new_cash

    if critical and cash > 80_000 and suggested is None:
        # No parseable figure — still refuse healthy-cash default for stressed NL
        new_cash = 30_000.0
        changes.append(
            {
                "field": "target_cash_at_end_eur",
                "original": cash,
                "clipped": new_cash,
                "message": (
                    f"target_cash_at_end_eur repaired from {cash} to {new_cash} "
                    "(cash-critical NL without inventing a high target)"
                ),
                "source": "nl_cash_intent",
            }
        )
        data["target_cash_at_end_eur"] = new_cash

    if critical:
        if not data.get("partly_fixed_costs"):
            changes.append(
                {
                    "field": "partly_fixed_costs",
                    "original": data.get("partly_fixed_costs"),
                    "clipped": True,
                    "message": "partly_fixed_costs set true for cash-critical NL",
                    "source": "nl_cash_intent",
                }
            )
            data["partly_fixed_costs"] = True
        try:
            growth = float(data.get("monthly_revenue_growth") or 0)
        except (TypeError, ValueError):
            growth = 0.0
        # Do not keep a "healthy growth" default when the story is stressed winter cash
        if growth > 0.005 and any(
            k in blob.lower() for k in ("winter", "talvi", "collapse", "off-season", "critical", "kriittinen")
        ):
            changes.append(
                {
                    "field": "monthly_revenue_growth",
                    "original": growth,
                    "clipped": 0.0,
                    "message": "monthly_revenue_growth zeroed for cash-stressed / winter NL",
                    "source": "nl_cash_intent",
                }
            )
            data["monthly_revenue_growth"] = 0.0

    return data, changes
