"""Code graders: parameters vs key, numeric reading / MoM, interpretation rubric."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


# Relative tolerance bands for parameter scoring (score decays to 0 beyond ~10× tol).
PARAM_NUMERIC_KEYS = [
    "monthly_revenue_start_eur",
    "monthly_revenue_growth",
    "days_sales_outstanding",
    "days_payables_outstanding",
    "target_cash_at_end_eur",
    "special_investment_eur",
]
COST_SHARE_KEYS = ["materials", "services", "personnel", "other"]

# Heuristic phrases that suggest invented causes (not supported by figures alone).
INVENTED_CAUSE_PATTERNS = [
    r"\bfraud\b",
    r"\bpetos\b",
    r"\bbankruptcy\b",
    r"\bkonkurssi\b",
    r"\bcustomer(?:s)? (?:left|lefting|churn)\b",
    r"\basiakkaat? (?:lähti|lähtivät|kadonneet)\b",
    r"\bbank (?:froze|freeze|blocked)\b",
    r"\bpankki (?:jäädytti|sulki)\b",
    r"\bembezzl",
    r"\bveropetos\b",
    r"\bunion strike\b",
    r"\blakko\b",
    r"\bcovid\b",
    r"\bpandemic\b",
]


@dataclass
class GradeDetail:
    score: float  # 0..1
    notes: str = ""
    per_field: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rel_score(predicted: float, truth: float, *, tol: float) -> float:
    denom = max(abs(truth), 1e-6)
    err = abs(predicted - truth) / denom
    # Full credit within tol; linear decay to 0 at ~10× tol
    return max(0.0, min(1.0, 1.0 - err / max(tol * 10, 1e-6)))


def grade_parameters(
    predicted: dict[str, Any],
    key: dict[str, Any],
    *,
    tol: float = 0.05,
) -> GradeDetail:
    """Relative-error grader for numeric parameters (0..1)."""
    per_field: dict[str, float] = {}
    scores: list[float] = []

    for k in PARAM_NUMERIC_KEYS:
        if k not in predicted or k not in key:
            continue
        try:
            p, t = float(predicted[k]), float(key[k])
        except (TypeError, ValueError):
            per_field[k] = 0.0
            scores.append(0.0)
            continue
        # Growth rates near zero: use absolute band
        if k == "monthly_revenue_growth":
            abs_err = abs(p - t)
            s = max(0.0, min(1.0, 1.0 - abs_err / max(tol, 1e-6)))
        else:
            s = _rel_score(p, t, tol=tol)
        per_field[k] = round(s, 4)
        scores.append(s)

    pred_shares = predicted.get("cost_shares_of_revenue") or {}
    key_shares = key.get("cost_shares_of_revenue") or {}
    if isinstance(pred_shares, dict) and isinstance(key_shares, dict):
        for k in COST_SHARE_KEYS:
            if k not in pred_shares or k not in key_shares:
                continue
            s = _rel_score(float(pred_shares[k]), float(key_shares[k]), tol=tol)
            per_field[f"cost_shares.{k}"] = round(s, 4)
            scores.append(s)

    if "partly_fixed_costs" in predicted and "partly_fixed_costs" in key:
        s = 1.0 if bool(predicted["partly_fixed_costs"]) == bool(key["partly_fixed_costs"]) else 0.0
        per_field["partly_fixed_costs"] = s
        scores.append(s)

    overall = sum(scores) / len(scores) if scores else 0.0
    return GradeDetail(
        score=round(overall, 4),
        notes=f"{len(scores)} fields graded (tol={tol})",
        per_field=per_field,
    )


def extract_first_number(text: str) -> float | None:
    """Pull the first numeric literal from free text (handles FI/EN decimals)."""
    if not text:
        return None
    # Prefer JSON-ish "value": 123.4
    m = re.search(r'"value"\s*:\s*(-?\d+(?:[.,]\d+)?)', text, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(-?\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|-?\d+[.,]\d+|-?\d+)", text)
    if not m:
        return None
    raw = m.group(1).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def grade_numeric_reading(
    answer_text: str,
    expected: float | int | None,
    *,
    tol: float = 0.02,
    absolute_tol: float | None = None,
) -> GradeDetail:
    """Code-check a model's numeric reading of a figure."""
    if expected is None:
        return GradeDetail(score=0.0, notes="no expected value in key")
    got = extract_first_number(answer_text)
    if got is None:
        return GradeDetail(score=0.0, notes="no number found in answer", per_field={"expected": float(expected)})
    exp = float(expected)
    if absolute_tol is not None:
        ok = abs(got - exp) <= absolute_tol
        score = 1.0 if ok else max(0.0, 1.0 - abs(got - exp) / max(absolute_tol * 10, 1e-6))
    else:
        score = _rel_score(got, exp, tol=tol)
    return GradeDetail(
        score=round(score, 4),
        notes=f"got={got} expected={exp}",
        per_field={"got": got, "expected": exp},
    )


@dataclass
class ProbeSpec:
    id: str
    key: str  # path in pack_summary
    question_fi: str
    question_en: str
    absolute_tol: float | None = None  # e.g. week index
    tol: float = 0.02


DEFAULT_PROBES: list[ProbeSpec] = [
    ProbeSpec(
        id="cash_end",
        key="cash_end",
        question_fi='Mikä on kassasaldo kauden lopussa? Vastaa JSON: {"value": <luku>}',
        question_en='What is cash at period end? Reply JSON: {"value": <number>}',
    ),
    ProbeSpec(
        id="revenue_last",
        key="revenue_last",
        question_fi='Mikä on viimeisimmän kuukauden liikevaihto? Vastaa JSON: {"value": <luku>}',
        question_en='What is revenue in the last month? Reply JSON: {"value": <number>}',
    ),
    ProbeSpec(
        id="mom_revenue_change",
        key="mom_revenue_change",
        question_fi='Mikä on liikevaihdon muutos kuukausitasolla (viimeinen − edellinen)? Vastaa JSON: {"value": <luku>}',
        question_en='What is the month-over-month revenue change (last − previous)? Reply JSON: {"value": <number>}',
    ),
    ProbeSpec(
        id="first_negative_projection_week",
        key="first_negative_projection_week",
        question_fi='Millä viikolla avointen laskujen ennuste menee ensimmäisen kerran negatiiviseksi? Jos ei mene, vastaa {"value": null}. Muuten {"value": <viikko>}.',
        question_en='In which week does the open-invoice projection first go negative? If never, {"value": null}. Else {"value": <week>}.',
        absolute_tol=0.1,
    ),
]


def grade_probes(
    answers: dict[str, str],
    pack_summary: dict[str, Any],
    probes: list[ProbeSpec] | None = None,
) -> GradeDetail:
    """Average score across reading / MoM probes. Separates MoM into notes."""
    probes = probes or DEFAULT_PROBES
    per_field: dict[str, float] = {}
    reading_scores: list[float] = []
    mom_scores: list[float] = []

    for probe in probes:
        expected = pack_summary.get(probe.key)
        text = answers.get(probe.id, "")
        if expected is None and probe.key == "first_negative_projection_week":
            # Never negative: accept null / none / ei / never
            low = text.lower()
            ok = any(tok in low for tok in ("null", "none", "ei mene", "never", "ei negatiiv"))
            # Also accept if model says no number / N/A
            got = extract_first_number(text)
            if ok and got is None:
                s = 1.0
            elif got is None and ("null" in low or "none" in low):
                s = 1.0
            else:
                s = 0.0 if got is not None else 0.5
            detail = GradeDetail(score=s, notes="no negative week expected")
        else:
            detail = grade_numeric_reading(
                text,
                expected,
                tol=probe.tol,
                absolute_tol=probe.absolute_tol,
            )
        per_field[probe.id] = detail.score
        if "mom" in probe.id:
            mom_scores.append(detail.score)
        else:
            reading_scores.append(detail.score)

    all_scores = list(per_field.values())
    overall = sum(all_scores) / len(all_scores) if all_scores else 0.0
    reading = sum(reading_scores) / len(reading_scores) if reading_scores else overall
    mom = sum(mom_scores) / len(mom_scores) if mom_scores else overall
    return GradeDetail(
        score=round(overall, 4),
        notes=f"reading={reading:.3f}; mom={mom:.3f}",
        per_field={**per_field, "_reading": round(reading, 4), "_mom": round(mom, 4)},
    )


# Finnish lexical markers for the separate FI quality band (EN-only models OK).
_FI_CHARS = re.compile(r"[äöåÄÖÅ]")
_FI_FINANCE_WORDS = re.compile(
    r"\b("
    r"kassa|kassasaldo|liikevaihto|ennuste|viikko|lasku|laskut|myynti|osto|"
    r"saaminen|saamiset|velka|velat|tulos|kate|kasvu|negatiivinen|positiivinen|"
    r"kuukausi|euroa|eur|miksi|koska|muuttuu|annetuilla|luvuilla"
    r")\b",
    re.I,
)
_EN_ONLY_MARKERS = re.compile(
    r"\b(the|and|cash|revenue|projection|week|because|invoice|balance)\b",
    re.I,
)


def grade_fi_quality(
    text: str,
    *,
    expected_language: str = "fi",
) -> GradeDetail:
    """
    Separate Finnish quality band for FI prompts.

    EN-only finance models are **not failed** on the main interpretation score;
    they receive a low FI band instead. Bands (see scorecard.fi_band_label):
      high ≥ 0.75 · mid ≥ 0.40 · low < 0.40 · n/a when prompt is EN.
    """
    if expected_language != "fi":
        return GradeDetail(
            score=1.0,
            notes="EN prompt; FI band not applicable",
            per_field={"applicable": 0.0, "fi_markers": 1.0},
        )

    text = (text or "").strip()
    if not text:
        return GradeDetail(
            score=0.0,
            notes="empty answer on FI prompt",
            per_field={"applicable": 1.0, "fi_markers": 0.0, "en_only": 1.0},
        )

    has_fi_chars = bool(_FI_CHARS.search(text))
    fi_word_hits = len(_FI_FINANCE_WORDS.findall(text))
    en_hits = len(_EN_ONLY_MARKERS.findall(text))

    # Marker score: diacritics + Finnish finance lexicon
    # ~3 FI finance terms → high band even without ä/ö/å (ASCII FI is common).
    marker = min(1.0, 0.25 * fi_word_hits)
    if has_fi_chars:
        marker = min(1.0, marker + 0.25)

    # Soft penalty when answer looks EN-only on a FI question
    en_only = 1.0 if (en_hits >= 3 and fi_word_hits == 0 and not has_fi_chars) else 0.0
    if en_only:
        marker = min(marker, 0.25)

    return GradeDetail(
        score=round(marker, 4),
        notes=(
            "en-only on FI prompt"
            if en_only
            else f"fi_chars={has_fi_chars}; fi_words={fi_word_hits}"
        ),
        per_field={
            "applicable": 1.0,
            "fi_markers": round(marker, 4),
            "en_only": en_only,
            "fi_word_hits": float(fi_word_hits),
        },
    )


def grade_interpretation(
    text: str,
    pack_summary: dict[str, Any],
    *,
    language: str = "fi",
) -> GradeDetail:
    """
    Rubric (code heuristics):
    - factual: mentions ≥1 number present in pack_summary
    - understandable: non-trivial length, not empty
    - no invented causes: avoids unsupported causal tropes

    Finnish quality is scored separately via ``grade_fi_quality`` (not folded in).
    """
    text = (text or "").strip()
    per_field: dict[str, float] = {}

    # Understandable
    length = len(text)
    if length < 20:
        understand = 0.0
    elif length < 60:
        understand = 0.5
    else:
        understand = 1.0
    per_field["understandable"] = understand

    # Factual: cite at least one figure from the summary
    numbers_in_pack: list[float] = []
    for k, v in pack_summary.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            numbers_in_pack.append(float(v))
    cited = 0
    for n in numbers_in_pack:
        # Allow integer formatting / rounding
        variants = {str(n), f"{n:.0f}", f"{n:.2f}", f"{int(n):,}".replace(",", " ")}
        if any(v and v in text.replace(",", ".") for v in variants):
            cited += 1
            break
        # Fuzzy: extracted numbers close to pack values
    extracted = extract_first_number(text)
    if cited == 0 and extracted is not None:
        for n in numbers_in_pack:
            if abs(n) < 1e-9:
                continue
            if abs(extracted - n) / max(abs(n), 1.0) < 0.05:
                cited = 1
                break
    # Also credit explicit mention of week index / projection language when relevant
    if cited == 0 and pack_summary.get("first_negative_projection_week") is not None:
        week = pack_summary["first_negative_projection_week"]
        if re.search(rf"\b(?:viikko|week)\s*{week}\b", text, re.I) or str(week) in text:
            cited = 1
    factual = 1.0 if cited else 0.0
    per_field["factual"] = factual

    # No invented causes
    low = text.lower()
    invented_hits = [p for p in INVENTED_CAUSE_PATTERNS if re.search(p, low)]
    no_invent = 0.0 if invented_hits else 1.0
    per_field["no_invented_causes"] = no_invent

    # Attach FI band detail for callers (does not affect main score)
    fi_g = grade_fi_quality(text, expected_language=language)
    per_field["fi_quality"] = fi_g.score

    overall = (understand + factual + no_invent) / 3.0
    notes = "ok"
    if invented_hits:
        notes = f"invented-cause patterns: {invented_hits[:3]}"
    elif factual < 1.0:
        notes = "did not cite pack figures"
    return GradeDetail(score=round(overall, 4), notes=notes, per_field=per_field)
