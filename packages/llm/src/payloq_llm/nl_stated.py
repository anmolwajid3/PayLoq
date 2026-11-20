"""Code-first deterministic NL extraction of stated parameters (work order A).

Weak Ollama models often omit or invent numbers. Parse only explicitly labeled
figures from the description, mark ``source=stated``, then merge with LLM JSON
so code-stated values win. Unstated fields stay null for industry×size assume.
"""

from __future__ import annotations

import re
from typing import Any

from payloq_llm.nl_cash_intent import extract_cash_target_hints, extract_euro_amounts
from payloq_llm.nl_param_hints import (
    extract_growth_rate,
    extract_special_investment,
    extract_starting_cash_eur,
)
from payloq_schemas.constants import PARAM_RANGES

_REV_LO, _REV_HI = PARAM_RANGES["monthly_revenue_start_eur"]

_REV_CONTEXT: tuple[str, ...] = (
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

_COVENANT_CONTEXT: tuple[str, ...] = (
    "covenant",
    "kovenantti",
    "minimum cash",
    "min cash",
    "vähimmäiskassa",
    "vahimmaiskassa",
    "bank covenant",
    "pankin kovenantti",
    "target cash",
    "tavoitekassa",
    "winter cash",
    "talvikassa",
    "winter trough",
    "talvipohja",
    "kassapohja",
)

_NOT_COVENANT_CONTEXT: tuple[str, ...] = (
    "starting cash",
    "opening cash",
    "alkukassa",
    "aloituskassa",
    "avauskassa",
    "capex",
    "invest",
    "investointi",
    "repair",
    "korjaus",
    "monthly revenue",
    "liikevaihto",
    "revenue",
)


def extract_stated_revenue_eur(text: str) -> float | None:
    """Explicit monthly revenue / turnover only — never invent industry defaults."""
    blob = (text or "").lower()
    best: float | None = None
    for amt, idx in extract_euro_amounts(text):
        if not (_REV_LO <= amt <= _REV_HI):
            continue
        window = blob[max(0, idx - 48) : idx + 56]
        if any(c in window for c in _REV_CONTEXT):
            # Prefer the first clear revenue figure (descriptions usually lead with it).
            if best is None or amt > best:
                best = float(amt)
    return best


def extract_covenant_min_cash_eur(text: str) -> float | None:
    """
    Parse covenant / minimum / target cash when explicitly labeled.

    Distinct from starting cash. Prefers amounts near covenant wording.
    """
    blob = text or ""
    low = blob.lower()
    best: tuple[float, float] | None = None  # amount, score

    for amt, idx in extract_euro_amounts(text):
        if amt < 1_000:
            continue
        left = max(0, idx - 64)
        window = low[left : idx + 48]
        amt_pos = idx - left

        cov_left = _nearest_left(window, amt_pos, _COVENANT_CONTEXT)
        cov_dist = _nearest_any(window, amt_pos, _COVENANT_CONTEXT)
        if cov_left is None and cov_dist is None:
            continue

        not_left = _nearest_left(window, amt_pos, _NOT_COVENANT_CONTEXT)
        if not_left is not None and (cov_left is None or not_left < cov_left):
            continue

        score = 2.0 if cov_left is not None else 1.0
        if cov_left is not None:
            score += max(0.0, 1.5 - (cov_left / 40.0))
        elif cov_dist is not None:
            score += max(0.0, 0.8 - (cov_dist / 50.0))
        if best is None or score > best[1] or (score == best[1] and amt < best[0]):
            best = (float(amt), score)

    if best is not None:
        return best[0]

    # Soft fallback: cash-target hints that are not starting cash.
    start = extract_starting_cash_eur(text)
    hints = extract_cash_target_hints(text)
    for h in sorted(hints):
        if start is not None and abs(h - start) < 1.0:
            continue
        return float(h)
    return None


def extract_dso_days(text: str) -> float | None:
    """Parse DSO / days sales outstanding when labeled."""
    return _extract_days_metric(
        text,
        labels=(
            r"dso",
            r"days?\s*sales?\s*outstanding",
            r"myyntisaamis(?:ten)?(?:\s+kiertoaika)?",
            r"saamisten\s+kierto",
        ),
    )


def extract_dpo_days(text: str) -> float | None:
    """Parse DPO / days payables outstanding when labeled."""
    return _extract_days_metric(
        text,
        labels=(
            r"dpo",
            r"days?\s*payables?\s*outstanding",
            r"ostovelkojen(?:\s+kiertoaika)?",
            r"velkojen\s+kierto",
        ),
    )


def _extract_days_metric(text: str, *, labels: tuple[str, ...]) -> float | None:
    blob = text or ""
    label_alt = "|".join(f"(?:{p})" for p in labels)
    patterns = [
        # DSO 35 days / DSO: 35 / DSO 35
        rf"(?:{label_alt})\s*[:=]?\s*(\d{{1,3}})\s*(?:days?|pv|päivää|paivaa)?\b",
        # 35 days DSO / 35 pv DSO
        rf"(\d{{1,3}})\s*(?:days?|pv|päivää|paivaa)\s+(?:{label_alt})\b",
    ]
    for pat in patterns:
        m = re.search(pat, blob, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            days = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if 5 <= days <= 120:
            return days
    return None


def _nearest_left(window: str, amt_pos: int, keywords: tuple[str, ...]) -> int | None:
    best: int | None = None
    for k in keywords:
        start = 0
        while True:
            found = window.find(k, start)
            if found < 0:
                break
            if found <= amt_pos:
                dist = amt_pos - found
                if best is None or dist < best:
                    best = dist
            start = found + 1
    return best


def _nearest_any(window: str, amt_pos: int, keywords: tuple[str, ...]) -> int | None:
    best: int | None = None
    for k in keywords:
        start = 0
        while True:
            found = window.find(k, start)
            if found < 0:
                break
            dist = abs(found - amt_pos)
            if best is None or dist < best:
                best = dist
            start = found + 1
    return best


def extract_stated_params_from_nl(text: str) -> dict[str, Any]:
    """
    Deterministic parse of stated numeric fields from NL.

    Returns a partial parameters dict (nulls omitted) plus ``field_sources``
    marking every filled key as ``stated``. CAPEX becomes a complete one-off
    outflow event when amount + month are present.
    """
    out: dict[str, Any] = {}
    sources: dict[str, str] = {}
    blob = text or ""

    start = extract_starting_cash_eur(blob)
    if start is not None:
        out["starting_cash_eur"] = float(start)
        sources["starting_cash_eur"] = "stated"

    # Explicit revenue only (no industry invent — bakery/hotel defaults stay assumed).
    rev = extract_stated_revenue_eur(blob)
    if rev is not None:
        out["monthly_revenue_start_eur"] = float(rev)
        sources["monthly_revenue_start_eur"] = "stated"

    growth = extract_growth_rate(blob)
    if growth is not None:
        out["monthly_revenue_growth"] = float(growth)
        sources["monthly_revenue_growth"] = "stated"

    covenant = extract_covenant_min_cash_eur(blob)
    if covenant is not None:
        out["covenant_min_cash_eur"] = float(covenant)
        out["target_cash_at_end_eur"] = float(covenant)
        sources["covenant_min_cash_eur"] = "stated"
        sources["target_cash_at_end_eur"] = "stated"

    dso = extract_dso_days(blob)
    if dso is not None:
        out["days_sales_outstanding"] = float(dso)
        sources["days_sales_outstanding"] = "stated"

    dpo = extract_dpo_days(blob)
    if dpo is not None:
        out["days_payables_outstanding"] = float(dpo)
        sources["days_payables_outstanding"] = "stated"

    inv = extract_special_investment(blob)
    if inv is not None:
        amt, month = inv
        out["special_investment_eur"] = float(amt)
        out["special_investment_month"] = int(month)
        sources["special_investment_eur"] = "stated"
        sources["special_investment_month"] = "stated"
        label = "capex_line"
        low = blob.lower()
        if re.search(r"(?<![a-z])(oven|uuni)\b", low):
            label = "oven_repair"
        elif any(k in low for k in ("roof", "katto", "hvac")):
            label = "roof_repair"
        out["one_off_events"] = [
            {
                "type": "capex",
                "amount_eur": float(amt),
                "month_index": int(month),
                "direction": "out",
                "label": label,
            }
        ]
        sources["one_off_events"] = "stated"

    out["field_sources"] = sources
    return out


def merge_llm_with_code_stated(
    llm_data: dict[str, Any] | None,
    code_stated: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Union of code-stated NL parse and LLM JSON.

    Code-stated numbers always win (prevent €420k vs €4.2M and similar).
    LLM may fill nulls that code did not parse. Sources stay ``stated`` for
    code-locked fields.
    """
    llm = dict(llm_data or {})
    code = dict(code_stated or {})
    code_sources = dict(code.pop("field_sources", None) or {})
    llm_sources = dict(llm.get("field_sources") or {})
    changes: list[dict[str, Any]] = []

    merged = dict(llm)
    # Start from LLM, overlay code-stated scalars / events.
    lock_keys = (
        "starting_cash_eur",
        "monthly_revenue_start_eur",
        "monthly_revenue_growth",
        "covenant_min_cash_eur",
        "target_cash_at_end_eur",
        "days_sales_outstanding",
        "days_payables_outstanding",
        "special_investment_eur",
        "special_investment_month",
    )
    for key in lock_keys:
        if key not in code or code[key] in (None, ""):
            continue
        code_val = code[key]
        llm_val = merged.get(key)
        if llm_val in (None, ""):
            merged[key] = code_val
            changes.append(
                {
                    "field": key,
                    "original": llm_val,
                    "clipped": code_val,
                    "message": f"{key} filled from code-first NL parse ({code_val})",
                    "source": "nl_stated",
                }
            )
        else:
            try:
                same = abs(float(llm_val) - float(code_val)) <= max(
                    1.0, abs(float(code_val)) * 0.01
                )
            except (TypeError, ValueError):
                same = llm_val == code_val
            if not same:
                changes.append(
                    {
                        "field": key,
                        "original": llm_val,
                        "clipped": code_val,
                        "message": (
                            f"{key} locked to code-stated NL value {code_val} "
                            f"(LLM had {llm_val})"
                        ),
                        "source": "nl_stated",
                    }
                )
            merged[key] = code_val
        llm_sources[key] = "stated"

    if code.get("one_off_events"):
        # Prefer complete code-stated CAPEX over incomplete / wrong LLM events.
        code_events = list(code["one_off_events"])
        llm_events = merged.get("one_off_events")
        replace = False
        if not llm_events:
            replace = True
        else:
            # Replace when LLM events lack amount/month or disagree on CAPEX amount.
            for ce in code_events:
                c_amt = float(ce.get("amount_eur") or 0)
                c_month = int(ce.get("month_index") or 0)
                matched = False
                for le in llm_events if isinstance(llm_events, list) else []:
                    if not isinstance(le, dict):
                        continue
                    try:
                        l_amt = float(le.get("amount_eur") or 0)
                        l_month = int(le.get("month_index") or 0)
                    except (TypeError, ValueError):
                        continue
                    if abs(l_amt - c_amt) <= 1.0 and l_month == c_month:
                        matched = True
                        break
                if not matched:
                    replace = True
                    break
        if replace:
            changes.append(
                {
                    "field": "one_off_events",
                    "original": llm_events,
                    "clipped": code_events,
                    "message": "one_off_events locked to code-stated CAPEX from NL",
                    "source": "nl_stated",
                }
            )
            merged["one_off_events"] = code_events
            llm_sources["one_off_events"] = "stated"
            if "special_investment_eur" in code:
                merged["special_investment_eur"] = code["special_investment_eur"]
                merged["special_investment_month"] = code["special_investment_month"]
                llm_sources["special_investment_eur"] = "stated"
                llm_sources["special_investment_month"] = "stated"

    for k, v in code_sources.items():
        llm_sources[k] = v
    merged["field_sources"] = llm_sources
    return merged, changes


def build_hybrid_params_from_nl(
    description: str,
    *,
    industry: str | None,
    company_size: str | None,
    seed: int,
    require_starting_cash: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Code-stated NL ∪ assumed defaults when Ollama JSON fails entirely.

    Labels notes as hybrid/code-nl. Raises MissingRequiredParameterError only
    when a required figure is absent from the description entirely.
    """
    from payloq_llm.extract_pipeline import finalize_extracted_parameters

    code = extract_stated_params_from_nl(description)
    # Empty LLM payload — finalize merges code-stated then assumes the rest.
    raw: dict[str, Any] = {
        "monthly_revenue_start_eur": None,
        "monthly_revenue_growth": None,
        "cost_shares_of_revenue": None,
        "days_sales_outstanding": None,
        "days_payables_outstanding": None,
        "target_cash_at_end_eur": None,
        "starting_cash_eur": None,
        "covenant_min_cash_eur": None,
        "special_investment_eur": None,
        "special_investment_month": None,
        "one_off_events": None,
        "partly_fixed_costs": None,
        "notes": "hybrid/code-nl: stated figures from deterministic NL parse",
    }
    # Pre-merge so finalize sees stated values even before its own code parse.
    merged, merge_changes = merge_llm_with_code_stated(raw, code)
    params, changes, grounding = finalize_extracted_parameters(
        merged,
        description,
        industry=industry,
        company_size=company_size,
        seed=seed,
        require_starting_cash=require_starting_cash,
    )
    if not grounding.ok:
        raise ValueError(grounding.error_text())
    all_changes = merge_changes + changes
    notes = params.get("notes") or ""
    if "hybrid/code-nl" not in notes:
        params["notes"] = (
            f"hybrid/code-nl: stated figures from deterministic NL parse; {notes}".strip(
                "; "
            )
        )
    # Provenance marker for sticky labeling / UI.
    params["_extraction_mode"] = "hybrid_code_nl"
    return params, all_changes
