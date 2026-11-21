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
    "winter trough",
    "talvipohja",
    "kassapohja",
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
    "trough",
    "pohja",
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
    "trough",
    "winter trough",
    "talvipohja",
    "kassapohja",
    "pohja",
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

# Euro parse ceiling (must stay ≥ PARAM_RANGES special/revenue ceilings).
_EURO_AMOUNT_MAX = 20_000_000.0
# SME "thin cash" band used by hotel/bakery heuristics.
_THIN_CASH_MAX = 80_000.0
# Mid-market / large manufacturing cash targets live above this.
_MIDMARKET_CASH_MIN = 200_000.0


def looks_cash_critical(text: str) -> bool:
    """True when the NL description is a cash-stressed / covenant story."""
    blob = (text or "").lower()
    if any(k in blob for k in CASH_CRITICAL_KEYWORDS):
        return True
    # Soft path: winter/hotel collapse + a cash-like figure in the text
    soft = any(k in blob for k in SOFT_CASH_STRESS_KEYWORDS)
    if not soft:
        return False
    hints = extract_cash_target_hints(text)
    if not hints:
        return False
    # Thin SME winter cash OR an explicit mid-market trough/covenant figure
    return min(hints) <= _THIN_CASH_MAX or max(hints) >= _MIDMARKET_CASH_MIN


def _parse_amount_token(raw: str, *, has_k: bool, has_m: bool) -> float | None:
    """Normalize a numeric token + optional k/m suffix into EUR."""
    token = (raw or "").strip()
    if not token:
        return None
    # Decimal millions / fractions: 4.2 / 4,2 (1–2 fraction digits, not thousands groups)
    if re.fullmatch(r"\d+[.,]\d{1,2}", token):
        try:
            val = float(token.replace(",", "."))
        except ValueError:
            return None
        if has_m:
            return val * 1_000_000.0
        if has_k:
            return val * 1_000.0
        return val
    # Thousands separators: 42,000 / 4,200,000 / 4.200.000 / 4 200 000
    if "," in token and "." not in token:
        parts = token.split(",")
        if all(len(p) == 3 for p in parts[1:]):
            digits = token.replace(",", "")
        else:
            digits = re.sub(r"[^\d]", "", token)
    elif "." in token and "," not in token:
        parts = token.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            digits = token.replace(".", "")
        else:
            digits = re.sub(r"[^\d]", "", token)
    else:
        digits = re.sub(r"[.\s,]", "", token)
    try:
        val = float(re.sub(r"[^\d]", "", digits) or "0")
    except ValueError:
        return None
    if has_m and val < 1_000_000:
        val *= 1_000_000.0
    elif has_k and val < 1_000:
        val *= 1_000.0
    return val


def extract_euro_amounts(text: str) -> list[tuple[float, int]]:
    """
    Parse euro-ish amounts from NL.

    Returns list of (amount_eur, start_index) for context windows.
    Supports: €25k, 25,000 €, ~€30k, 25000, 25 000 euroa, €4.2M, 4.2 million, 4,2 miljoonaa.
    """
    blob = text or ""
    found: list[tuple[float, int]] = []
    patterns = [
        # Prefer thousands groups before decimal fragments so €1,300,000 ≠ 1300.
        # €4.2M / €4,2M / €1,300,000 / €4200000
        r"[€]\s*~?\s*(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?|\d+)\s*([mM]|[kK])?\b",
        # 4.2M € / 4,2 miljoonaa euroa / 2.8 million EUR
        # [mM] must not be the start of "month"/"months" (DSO "2 months" is not €2M).
        r"~?\s*(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?|\d+)\s*"
        r"([mM](?!onth)|[kK]|miljoon(?:aa|a)?|millions?)\s*(?:€|euros?\b|euroa\b)?",
        # 25,000 € / 25k EUR / 25000 euroa (no \b after € — € is non-word)
        r"~?\s*(\d{1,3}(?:[.,\s]\d{3})+|\d+)\s*([kK])?\s*(?:€|euros?\b|euroa\b)",
        # bare 25k / 30k near cash words — handled with context filter later
        r"\b(\d{1,3})\s*([kK])\b",
        r"\b(\d{4,7})\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, blob, flags=re.IGNORECASE):
            raw = m.group(1)
            suffix = ""
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                suffix = m.group(2)
            full = m.group(0)
            has_m = bool(
                re.search(r"[mM]\b|miljoon|million", suffix, flags=re.IGNORECASE)
            ) or bool(re.search(r"(?<![A-Za-z])[mM](?![A-Za-z])", full))
            # Avoid treating month "m4" noise: require million-ish when M alone
            if has_m and suffix.lower() in {"m"} and not re.search(
                r"[€]|eur|euro|miljoon|million", full, flags=re.IGNORECASE
            ):
                # Bare "4.2M" without currency still counts as millions in finance NL
                if not re.search(r"\d+[.,]?\d*\s*[mM]\b", full):
                    has_m = False
            has_k = (not has_m) and (
                bool(re.search(r"[kK]", suffix))
                or bool(re.search(r"[kK]\s*(?:€|eur|euroa)?\s*$", full))
            )
            val = _parse_amount_token(raw, has_k=has_k, has_m=has_m)
            if val is None:
                continue
            if val < 1_000 or val > _EURO_AMOUNT_MAX:
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
        # Capex / roof / line figures are investments, not target cash.
        invest_keys = (
            "roof",
            "katto",
            "capex",
            "repair",
            "remont",
            "hvac",
            "invest",
            "investointi",
            "line",
            "production line",
            "tuotantolinja",
            "oven",
            "uuni",
        )
        invest_hits = [window.rfind(k) for k in invest_keys if k in window]
        covenant_keys = (
            "covenant",
            "kovenantti",
            "target cash",
            "tavoitekassa",
            "talvikassa",
            "winter cash",
            "trough",
            "talvipohja",
            "kassapohja",
        )
        cov_hits = [window.rfind(k) for k in covenant_keys if k in window]
        # Amount sits at ~48 chars into the window; prefer nearest label.
        amt_pos = min(48, len(window) - 1)
        if invest_hits and amt >= 50_000:
            nearest_invest = max(invest_hits)
            nearest_cov = max(cov_hits) if cov_hits else -999
            if abs(amt_pos - nearest_invest) <= abs(amt_pos - nearest_cov):
                continue
        # Prefer cash/covenant context; skip ADR/revenue-adjacent amounts.
        if has_cash_ctx and not any(s in window for s in _SKIP_NEAR):
            hints.append(amt)
        elif has_cash_ctx:
            # Revenue words nearby — still accept clear covenant/trough labels.
            if any(k in window for k in covenant_keys):
                hints.append(amt)
    return hints


def suggested_target_cash_eur(text: str) -> float | None:
    """
    Best target_cash_at_end_eur hint from NL.

    Prefer thin SME covenant / winter-cash (~5k–80k). For mid-market NL, use
    trough / covenant figures in the hundreds-of-thousands to millions band.
    """
    hints = extract_cash_target_hints(text)
    if not hints:
        return None
    thin = [h for h in hints if 5_000 <= h <= _THIN_CASH_MAX]
    if thin:
        # Covenant is often the lower bound; winter cash ~30k — use the min thin hint
        return float(min(thin))
    mid = [h for h in hints if h >= _MIDMARKET_CASH_MIN]
    if mid:
        # Winter trough is usually the lower of trough/covenant pair
        return float(min(mid))
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

    if suggested is not None and (critical or cash > _THIN_CASH_MAX or suggested >= _MIDMARKET_CASH_MIN):
        far_high = cash > suggested * 1.5
        # Mid-market: stub/LLM often invents SME €200–500k while NL states millions.
        far_low = suggested >= _MIDMARKET_CASH_MIN and (cash <= 0 or cash < suggested * 0.6)
        # SME cash-critical: refuse healthy defaults above the thin band.
        sme_crush = critical and suggested <= _THIN_CASH_MAX and cash > _THIN_CASH_MAX
        if cash <= 0 or far_high or far_low or sme_crush:
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

    if critical and suggested is None and cash >= 300_000:
        # No parseable figure — refuse classic healthy invent (~330k), but keep
        # size-scaled cash_critical baselines (e.g. 45k × large mult ≈ 225k).
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
        # — but keep an explicit low positive growth stated in mid-market NL (e.g. 0.3%).
        from payloq_llm.nl_param_hints import extract_growth_rate

        nl_growth = extract_growth_rate(blob)
        if nl_growth is not None:
            if abs(growth - nl_growth) > 1e-6:
                changes.append(
                    {
                        "field": "monthly_revenue_growth",
                        "original": growth,
                        "clipped": nl_growth,
                        "message": (
                            f"monthly_revenue_growth repaired from {growth} to {nl_growth} "
                            "using NL growth figure"
                        ),
                        "source": "nl_cash_intent",
                    }
                )
                data["monthly_revenue_growth"] = nl_growth
        elif growth > 0.005 and any(
            k in blob.lower()
            for k in ("winter", "talvi", "collapse", "off-season", "critical", "kriittinen")
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
