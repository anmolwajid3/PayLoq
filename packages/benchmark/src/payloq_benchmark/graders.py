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
# Use stems so Finnish inflections (konkurssissa, petoksen, …) still match.
INVENTED_CAUSE_PATTERNS = [
    r"\bfraud\b",
    r"\bpetok",  # petos / petoksen / …
    r"\bpetos\b",
    r"\bbankruptcy\b",
    r"\bkonkurss",  # konkurssi / konkurssissa
    r"\bcustomer(?:s)? (?:left|leaving|churn)\b",
    r"\basiakka(?:at|iden|ita)?\s+(?:lähti|lähtivät|kadon)",
    r"\bbank (?:froze|freeze|blocked)\b",
    r"\bpankki (?:jäädytti|sulki|jäädyt)",
    r"\bembezzl",
    r"\bveropetos\b",
    r"\bunion strike\b",
    r"\blakko\b",
    r"\bcovid\b",
    r"\bpandemic\b",
    r"\bhack(?:ed|er|ing)?\b",
    r"\bhakker",
    r"\binsurance\s+payout\b",
    r"\bvakuutuskorvaus\b",
]

# Claims that cash / projection is already (or always) negative.
_CASH_ALREADY_NEGATIVE = re.compile(
    r"(?:"
    r"kassa\s+(?:on\s+)?(?:jo\s+)?negatiiv|"
    r"kassa\s+menee\s+negatiiviseksi\s+joka|"
    r"negatiivinen\s+joka\s+viikko|"
    r"cash\s+(?:is\s+)?(?:already\s+)?negativ|"
    r"cash\s+(?:goes|went)\s+negative\s+(?:every|each|all)|"
    r"always\s+negative"
    r")",
    re.I,
)
_CASH_NEVER_NEGATIVE = re.compile(
    r"(?:"
    r"ei\s+mene\s+negatiiv|"
    r"ei\s+negatiiv|"
    r"stays?\s+non[- ]?negative|"
    r"does\s+not\s+go\s+negative|"
    r"never\s+goes\s+negative|"
    r"projection\s+stays\s+non[- ]?negative"
    r")",
    re.I,
)
_PROJECTION_WEEK_CLAIM = re.compile(
    r"(?:viikolla|viikko|week)\s*(\d{1,2})",
    re.I,
)

# Money-like literals in free text must match pack figures (grounding).
_MONEY_NUMBER_RE = re.compile(
    r"(-?\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|-?\d+[.,]\d+|-?\d{3,})"
)

# Stub reading/interpretation can score 1.0 by echoing pack_summary — that only
# proves harness wiring, not model understanding (see docs/evaluation.md).
STUB_PERFECT_SCORE_MEANS_WIRING_ONLY = True


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


def grade_parameters_binary(
    predicted: dict[str, Any],
    key: dict[str, Any],
    *,
    rel_tol: float = 0.05,
    growth_abs_tol: float = 0.01,
) -> GradeDetail:
    """
    FR-B-11 / FR-B-12: each field correct (1) or wrong (0); score = share correct.
    """
    per_field: dict[str, float] = {}
    correct = 0
    total = 0

    def _mark(name: str, ok: bool) -> None:
        nonlocal correct, total
        total += 1
        per_field[name] = 1.0 if ok else 0.0
        if ok:
            correct += 1

    for k in PARAM_NUMERIC_KEYS:
        if k not in key:
            continue
        if k not in predicted:
            _mark(k, False)
            continue
        try:
            p, t = float(predicted[k]), float(key[k])
        except (TypeError, ValueError):
            _mark(k, False)
            continue
        if k == "monthly_revenue_growth":
            _mark(k, abs(p - t) <= growth_abs_tol)
        else:
            denom = max(abs(t), 1e-6)
            _mark(k, abs(p - t) / denom <= rel_tol)

    pred_shares = predicted.get("cost_shares_of_revenue") or {}
    key_shares = key.get("cost_shares_of_revenue") or {}
    if isinstance(key_shares, dict):
        for k in COST_SHARE_KEYS:
            if k not in key_shares:
                continue
            if not isinstance(pred_shares, dict) or k not in pred_shares:
                _mark(f"cost_shares.{k}", False)
                continue
            t = float(key_shares[k])
            p = float(pred_shares[k])
            denom = max(abs(t), 1e-6)
            _mark(f"cost_shares.{k}", abs(p - t) / denom <= rel_tol)

    if "partly_fixed_costs" in key:
        ok = bool(predicted.get("partly_fixed_costs")) == bool(key["partly_fixed_costs"])
        _mark("partly_fixed_costs", ok)

    share = correct / total if total else 0.0
    return GradeDetail(
        score=round(share, 4),
        notes=f"{correct} of {total} fields correct (binary, rel_tol={rel_tol})",
        per_field=per_field,
    )


def _parse_number_token(raw: str) -> float | None:
    cleaned = raw.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_first_number(text: str) -> float | None:
    """Pull the first numeric literal from free text (handles FI/EN decimals)."""
    if not text:
        return None
    # Prefer JSON-ish "value": 123.4
    m = re.search(r'"value"\s*:\s*(-?\d+(?:[.,]\d+)?)', text, re.I)
    if m:
        return _parse_number_token(m.group(1))
    m = re.search(r"(-?\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|-?\d+[.,]\d+|-?\d+)", text)
    if not m:
        return None
    return _parse_number_token(m.group(1))


def extract_money_like_numbers(text: str) -> list[float]:
    """
    Money-scale literals (≥100 abs, or thousand-grouped / decimal) from free text.

    Used to catch invented € amounts that are not present in the pack summary.
    Small week indices (1–52) are ignored here — they are checked separately.
    """
    if not text:
        return []
    found: list[float] = []
    for m in _MONEY_NUMBER_RE.finditer(text):
        val = _parse_number_token(m.group(1))
        if val is None:
            continue
        if abs(val) < 100:
            continue
        found.append(val)
    return found


def _pack_numeric_values(pack_summary: dict[str, Any]) -> list[float]:
    """Flatten numeric scalars (and drop deltas) from the figure pack."""
    numbers: list[float] = []
    for _k, v in pack_summary.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            numbers.append(float(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for _ik, iv in item.items():
                        if isinstance(iv, (int, float)) and not isinstance(iv, bool):
                            numbers.append(float(iv))
                elif isinstance(item, (int, float)) and not isinstance(item, bool):
                    numbers.append(float(item))
    return numbers


def _number_in_pack(n: float, pack_numbers: list[float], *, rel_tol: float = 0.05) -> bool:
    for p in pack_numbers:
        if abs(p) < 1e-9:
            if abs(n) < 1e-6:
                return True
            continue
        if abs(n - p) / max(abs(p), 1.0) <= rel_tol:
            return True
        # Absolute band for small indices (week numbers).
        if abs(p) <= 52 and abs(n - p) <= 0.15:
            return True
    return False


def _cites_pack_figure(text: str, pack_summary: dict[str, Any]) -> bool:
    """True when the answer mentions ≥1 figure present in pack_summary."""
    numbers_in_pack = _pack_numeric_values(pack_summary)
    for n in numbers_in_pack:
        variants = {str(n), f"{n:.0f}", f"{n:.2f}", f"{int(n):,}".replace(",", " ")}
        if any(v and v in text.replace(",", ".") for v in variants):
            return True
    extracted = extract_first_number(text)
    if extracted is not None:
        for n in numbers_in_pack:
            if abs(n) < 1e-9:
                continue
            if abs(extracted - n) / max(abs(n), 1.0) < 0.05:
                return True
    week = pack_summary.get("first_negative_projection_week")
    if week is not None:
        if re.search(rf"\b(?:viikko|week)\s*{week}\b", text, re.I) or str(week) in text:
            return True
    return False


def _grounding_score(text: str, pack_summary: dict[str, Any]) -> tuple[float, list[float]]:
    """
    Score how well money-like numbers in the answer are grounded in the pack.

    Returns (score 0..1, list of ungrounded amounts). Keyword fluff that only
    drops one lucky pack figure still fails if it invents other € amounts.
    """
    pack_numbers = _pack_numeric_values(pack_summary)
    money = extract_money_like_numbers(text)
    if not money:
        # No money literals: not grounded in figures (unless pack itself has none).
        if not any(abs(n) >= 100 for n in pack_numbers):
            return 1.0, []
        return 0.0, []
    ungrounded = [n for n in money if not _number_in_pack(n, pack_numbers)]
    if not ungrounded:
        return 1.0, []
    # Partial credit only when a majority of money literals still match the pack.
    matched = len(money) - len(ungrounded)
    return max(0.0, matched / len(money)), ungrounded


def _contradiction_score(text: str, pack_summary: dict[str, Any]) -> tuple[float, str]:
    """
    Detect cash / projection claims that contradict the pack figures.

    Returns (1.0 if consistent, 0.0 if contradictory, note).
    """
    cash_end = pack_summary.get("cash_end")
    neg_week = pack_summary.get("first_negative_projection_week")
    has_neg_key = "first_negative_projection_week" in pack_summary
    pack_shows_negative = neg_week is not None or (
        isinstance(cash_end, (int, float)) and float(cash_end) < 0
    )
    pack_shows_non_negative = has_neg_key and neg_week is None and (
        cash_end is None or (isinstance(cash_end, (int, float)) and float(cash_end) >= 0)
    )

    if pack_shows_non_negative and _CASH_ALREADY_NEGATIVE.search(text):
        return 0.0, "claims cash already/always negative while pack is non-negative"

    if pack_shows_negative and _CASH_NEVER_NEGATIVE.search(text):
        return 0.0, "claims cash/projection never negative while pack shows a negative"

    if has_neg_key and neg_week is None:
        # "viikolla N" / "week N" as a first-negative claim contradicts null week.
        for m in _PROJECTION_WEEK_CLAIM.finditer(text):
            claimed = int(m.group(1))
            # Ignore year-like / large values; weeks are 1–52.
            if 1 <= claimed <= 52 and _CASH_ALREADY_NEGATIVE.search(text) is None:
                # Only flag when the surrounding claim implies a negative crossing.
                window = text[max(0, m.start() - 40) : m.end() + 40].lower()
                if any(
                    tok in window
                    for tok in (
                        "negatiiv",
                        "negative",
                        "menee",
                        "goes",
                        "turns",
                        "ennuste",
                        "projection",
                    )
                ):
                    return 0.0, f"claims negative in week {claimed} but pack has none"

    if neg_week is not None:
        for m in _PROJECTION_WEEK_CLAIM.finditer(text):
            claimed = int(m.group(1))
            if 1 <= claimed <= 52 and claimed != int(neg_week):
                window = text[max(0, m.start() - 40) : m.end() + 40].lower()
                if any(tok in window for tok in ("negatiiv", "negative", "menee", "goes", "turns")):
                    return 0.0, f"claims negative week {claimed} vs pack week {neg_week}"

    return 1.0, ""


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
    Rubric (code heuristics) — five fields, mean overall:

    - understandable: non-trivial length
    - factual: cites ≥1 number present in pack_summary
    - grounded: money-like literals in the answer match pack figures (no invented €)
    - no_invented_causes: avoids unsupported causal tropes (stem-matched)
    - no_contradiction: cash / projection claims agree with pack signs & weeks

    Keyword stubs that echo pack_summary can still score 1.0 by construction;
    that only proves pipeline wiring (``STUB_PERFECT_SCORE_MEANS_WIRING_ONLY``).
    Deliberately wrong / invented / contradictory answers must score well below 1.0.

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
    factual = 1.0 if _cites_pack_figure(text, pack_summary) else 0.0
    per_field["factual"] = factual

    # Grounded: money-like amounts must appear in the pack (catches wrong figures)
    grounded, ungrounded = _grounding_score(text, pack_summary)
    per_field["grounded"] = round(grounded, 4)

    # No invented causes
    low = text.lower()
    invented_hits = [p for p in INVENTED_CAUSE_PATTERNS if re.search(p, low)]
    no_invent = 0.0 if invented_hits else 1.0
    per_field["no_invented_causes"] = no_invent

    # No contradictory cash / projection claims
    no_contra, contra_note = _contradiction_score(text, pack_summary)
    per_field["no_contradiction"] = no_contra

    # Attach FI band detail for callers (does not affect main score)
    fi_g = grade_fi_quality(text, expected_language=language)
    per_field["fi_quality"] = fi_g.score

    dims = (understand, factual, grounded, no_invent, no_contra)
    overall = sum(dims) / len(dims)
    notes = "ok"
    if invented_hits:
        notes = f"invented-cause patterns: {invented_hits[:3]}"
    elif no_contra < 1.0 and contra_note:
        notes = contra_note
    elif grounded < 1.0 and ungrounded:
        notes = f"ungrounded amounts: {ungrounded[:5]}"
    elif factual < 1.0:
        notes = "did not cite pack figures"
    return GradeDetail(score=round(overall, 4), notes=notes, per_field=per_field)
