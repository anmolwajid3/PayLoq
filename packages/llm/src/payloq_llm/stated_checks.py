"""Section C: code checks on model extraction (value grounding + conversions).

Principle: code calculates; the LM interprets. Grounding is value-based —
numbers must appear in the description after unit parsing. Model quotes are
optional and never cause rejection when formatting differs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from payloq_llm.nl_cash_intent import extract_euro_amounts
from payloq_schemas.constants import (
    GROUNDING_ABSOLUTE_TOLERANCE_EUR,
    GROUNDING_RELATIVE_TOLERANCE,
)

logger = logging.getLogger(__name__)

GROWTH_MIN = -0.2
GROWTH_MAX = 0.2

# Section B field → engine / fidelity field names.
B_TO_ENGINE: dict[str, str] = {
    "revenue_monthly_eur": "monthly_revenue_start_eur",
    "revenue_annual_eur": "revenue_annual_eur",
    "growth_per_month_fraction": "monthly_revenue_growth",
    "starting_cash_eur": "starting_cash_eur",
    "covenant_min_cash_eur": "covenant_min_cash_eur",
    "dso_days": "days_sales_outstanding",
    "dpo_days": "days_payables_outstanding",
}

ENGINE_TO_B: dict[str, str] = {v: k for k, v in B_TO_ENGINE.items() if k != "revenue_annual_eur"}

_NUMERIC_STATED_FIELDS: frozenset[str] = frozenset(
    {
        "revenue_monthly_eur",
        "revenue_annual_eur",
        "growth_per_month_fraction",
        "starting_cash_eur",
        "covenant_min_cash_eur",
        "dso_days",
        "dpo_days",
        "monthly_revenue_start_eur",
        "monthly_revenue_growth",
        "days_sales_outstanding",
        "days_payables_outstanding",
        "special_investment_eur",
        "special_investment_month",
        "target_cash_at_end_eur",
    }
)

_KNOWN_STATED_FIELDS: frozenset[str] = frozenset(
    set(_NUMERIC_STATED_FIELDS)
    | {
        "one_off_events",
        "industry",
        "company_size",
        "scenario_shape",
    }
)

_MONTH_PATTERNS: tuple[str, ...] = (
    r"(?:month|kuukaus(?:i|essa)?|kk)\s*(?P<m>\d{1,2})",
    r"(?P<m>\d{1,2})\.?\s*(?:month|kuukaus)",
)

_DIR_OUT: tuple[str, ...] = ("outflow", "out-flow", "out flow", "ulosvirtaus", "meno")
_DIR_IN: tuple[str, ...] = ("inflow", "in-flow", "in flow", "tulovirta", "tulo")


@dataclass
class StatedIssue:
    field: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "message": self.message}


@dataclass
class StatedCheckResult:
    ok: bool
    issues: list[StatedIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error_text(self) -> str:
        if not self.issues:
            return ""
        return "; ".join(f"{i.field}: {i.message}" for i in self.issues)


def _near(value: float, candidate: float) -> bool:
    """Near-match for euro-scale amounts (absolute ≤1 EUR or relative)."""
    if abs(value - candidate) <= GROUNDING_ABSOLUTE_TOLERANCE_EUR:
        return True
    denom = max(abs(candidate), abs(value), 1.0)
    return abs(value - candidate) / denom <= GROUNDING_RELATIVE_TOLERANCE


def _near_number(value: float, candidate: float) -> bool:
    """Near-match that keeps growth fractions distinct from percent figures."""
    # Sub-unit values (growth fractions, small percents): relative / tight absolute only.
    if abs(value) < 1.0 and abs(candidate) < 1.0:
        return abs(value - candidate) <= max(1e-9, abs(candidate) * GROUNDING_RELATIVE_TOLERANCE)
    if abs(value) < 1.0 or abs(candidate) < 1.0:
        # Do not treat 0.005 ≈ 0.5 via the €1 absolute band.
        denom = max(abs(candidate), abs(value), 1e-9)
        return abs(value - candidate) / denom <= GROUNDING_RELATIVE_TOLERANCE
    return _near(value, candidate)


def _parse_grouped_number(raw: str) -> float | None:
    """Parse 210,000 / 210.000 / 65 000 / 210000 into a float."""
    token = (raw or "").strip()
    if not token:
        return None
    if re.fullmatch(r"\d+[.,]\d{1,2}", token):
        try:
            return float(token.replace(",", "."))
        except ValueError:
            return None
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
        return float(re.sub(r"[^\d]", "", digits) or "0")
    except ValueError:
        return None


def scan_description_numbers(description: str) -> list[float]:
    """
    Scan the description for all numbers, including
    ``210,000``, ``210.000``, ``65 000``, ``50k``, ``2.4 million``, ``0.5%``.

    Returns normalized numeric values (percents as both percent and fraction).
    """
    blob = description or ""
    found: list[float] = []

    for amt, _idx in extract_euro_amounts(blob):
        found.append(float(amt))

    # Grouped / spaced thousands without requiring a currency word.
    for m in re.finditer(
        r"\b(\d{1,3}(?:[.,\s]\d{3})+)\b",
        blob,
    ):
        val = _parse_grouped_number(m.group(1))
        if val is not None and val >= 1_000:
            found.append(val)

    # 50k / 2.4M / 2.4 million / 2,4 miljoonaa
    for m in re.finditer(
        r"\b(\d+(?:[.,]\d+)?)\s*([kK]|[mM]|miljoon(?:aa|a)?|millions?)\b",
        blob,
    ):
        try:
            n = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit.startswith("m"):
            n *= 1_000_000.0
        elif unit.lower() == "k":
            n *= 1_000.0
        found.append(n)

    # Percentages: keep both the percent figure and the fraction.
    for m in re.finditer(r"([+-]?\d+(?:[.,]\d+)?)\s*%", blob):
        try:
            pct = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        found.append(pct)
        found.append(pct / 100.0)

    # Bare day-like / month-like integers (1–120) for DSO/DPO/month_index.
    for m in re.finditer(r"\b(\d{1,3})\b", blob):
        try:
            n = float(m.group(1))
        except ValueError:
            continue
        if 1 <= n <= 120:
            found.append(n)

    # De-dupe: EUR absolute tolerance only for large amounts; keep distinct fractions.
    uniq: list[float] = []
    for v in found:
        if abs(v) < 1.0:
            if any(abs(v - u) <= 1e-9 for u in uniq if abs(u) < 1.0):
                continue
        elif any(_near(v, u) for u in uniq if abs(u) >= 1.0):
            continue
        uniq.append(v)
    return uniq


def value_appears_in_description(
    value: float,
    description: str,
    *,
    field: str = "",
    numbers: list[float] | None = None,
) -> bool:
    """True when ``value`` appears in the description after unit parsing."""
    amounts = numbers if numbers is not None else scan_description_numbers(description)
    if field in {"growth_per_month_fraction", "monthly_revenue_growth"}:
        # Accept fraction or percent form.
        if any(_near_number(float(value), float(a)) for a in amounts):
            return True
        if any(_near_number(float(value) * 100.0, float(a)) for a in amounts):
            return True
        return False
    return any(_near_number(float(value), float(a)) for a in amounts)


def _value_in_quote(value: float, quote: str, *, field: str) -> bool:
    """Legacy helper kept for normalize_stated_map remapping of malformed keys."""
    return value_appears_in_description(value, quote or "", field=field)


def normalize_stated_map(
    stated: dict[str, str] | None,
    parameters: dict[str, Any] | None,
) -> dict[str, str]:
    """
    Remap malformed ``stated`` keys.

    Weak models sometimes use the quote text as the key. Map those back onto
    parameter field names by matching values inside the quote (or key text).
    """
    stated = dict(stated or {})
    parameters = parameters or {}
    out: dict[str, str] = {}
    for key, quote in stated.items():
        quote_s = str(quote or "")
        if key in _KNOWN_STATED_FIELDS:
            out[key] = quote_s
            continue
        matched: str | None = None
        for field_name, raw in parameters.items():
            if field_name in {"one_off_events", "industry", "company_size"}:
                continue
            if raw is None or raw == "":
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if _value_in_quote(val, quote_s or key, field=field_name):
                matched = field_name
                break
        if matched is None:
            events = parameters.get("one_off_events") or []
            if isinstance(events, list) and events:
                try:
                    amt = float(events[0].get("amount_eur"))  # type: ignore[union-attr]
                except (TypeError, ValueError, AttributeError):
                    amt = None
                if amt is not None and _value_in_quote(amt, quote_s or key, field="amount_eur"):
                    matched = "one_off_events"
        if matched:
            out[matched] = quote_s or str(key)
        elif key in _KNOWN_STATED_FIELDS:
            out[key] = quote_s
    return out


def _resolve_param_value(parameters: dict[str, Any], field_name: str) -> Any:
    raw = parameters.get(field_name)
    if raw is None and field_name in B_TO_ENGINE:
        raw = parameters.get(B_TO_ENGINE[field_name])
    if raw is None and field_name in ENGINE_TO_B:
        raw = parameters.get(ENGINE_TO_B[field_name])
    return raw


def check_stated_values(
    *,
    description: str,
    stated: dict[str, str] | None,
    parameters: dict[str, Any] | None,
) -> StatedCheckResult:
    """
    Value-based grounding: every stated numeric field's value must appear in
    the description after unit parsing. Quotes are optional — never reject
    because a quote text differs in formatting.
    """
    issues: list[StatedIssue] = []
    stated = stated or {}
    parameters = parameters or {}
    numbers = scan_description_numbers(description)

    skip_numeric = {
        "scenario_shape",
        "industry",
        "company_size",
        "scenario_shape_quote",
    }

    for field_name in stated:
        if field_name in skip_numeric:
            continue

        if field_name == "one_off_events" or field_name.startswith("one_off"):
            events = parameters.get("one_off_events") or []
            if isinstance(events, list):
                for i, ev in enumerate(events):
                    if not isinstance(ev, dict):
                        continue
                    try:
                        amt = float(ev.get("amount_eur"))
                    except (TypeError, ValueError):
                        continue
                    if not value_appears_in_description(
                        amt, description, field="amount_eur", numbers=numbers
                    ):
                        issues.append(
                            StatedIssue(
                                field=f"one_off_events[{i}].amount_eur",
                                message=(
                                    f"value {amt} does not appear in the description "
                                    f"after parsing units (k, M, %, €); sample="
                                    f"{sorted(set(round(a, 2) for a in numbers))[:12]}"
                                ),
                            )
                        )
            continue

        raw = _resolve_param_value(parameters, field_name)
        if raw is None or raw == "":
            # Cleaned upstream: stated+null is a warning, not a fail.
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if not value_appears_in_description(
            val, description, field=field_name, numbers=numbers
        ):
            issues.append(
                StatedIssue(
                    field=field_name,
                    message=(
                        f"value {val} does not appear in the description after "
                        f"parsing units (k, M, %, €); description amounts sample="
                        f"{sorted(set(round(a, 2) for a in numbers))[:12]}"
                    ),
                )
            )

    # Unstated non-null invents are cleaned to null upstream; only fields listed
    # in ``stated`` (or aliases resolved above) are hard-grounded here.

    return StatedCheckResult(ok=not issues, issues=issues)


# Back-compat alias used by older call sites / tests.
check_stated_quotes = check_stated_values


def _contains_brackets(value: Any) -> bool:
    if isinstance(value, str) and ("[" in value or "]" in value):
        return True
    return False


def clean_extraction_output(
    parameters: dict[str, Any],
    stated: dict[str, str],
    description: str,
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """
    Clean model output before validation (TC-ABC item 3).

    - Any value containing ``[`` or ``]`` (e.g. ``€[0]``) → null.
    - A value of ``0`` for a field the description does not mention → null.
    - Field listed in ``stated`` but value null → remove from stated + warn (no fail).
    """
    out = dict(parameters or {})
    stated_out = dict(stated or {})
    warnings: list[str] = []
    numbers = scan_description_numbers(description)

    for key in list(out.keys()):
        if key in {"one_off_events", "industry", "company_size", "stated", "field_sources"}:
            continue
        raw = out.get(key)
        if _contains_brackets(raw):
            warnings.append(f"{key}: bracketed value {raw!r} cleaned to null")
            out[key] = None
            continue
        # Nested cost shares etc. skipped; only scalars here.
        if isinstance(raw, (dict, list)):
            continue
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        appears = value_appears_in_description(
            val, description, field=key, numbers=numbers
        )
        listed = key in stated_out or any(
            B_TO_ENGINE.get(s) == key or ENGINE_TO_B.get(s) == key or s == key
            for s in stated_out
        )
        if abs(val) < 1e-12:
            # Zero for a field the description does not mention → null.
            has_literal_zero = bool(
                re.search(r"(?<![\d.,])0(?:\.0+)?(?![\d])", description or "")
            )
            if not has_literal_zero and not appears:
                warnings.append(f"{key}: unmentioned zero cleaned to null")
                out[key] = None
            continue
        # Invented non-zero not listed in stated and absent from description → null
        # (do not fail the run; code will assume). Values listed in stated are
        # grounded separately and may fail.
        if not listed and not appears and key in _NUMERIC_STATED_FIELDS:
            warnings.append(
                f"{key}: value {val} not in description and not stated — cleaned to null"
            )
            out[key] = None

    # one_off_events: clean bracketed amount strings
    events = out.get("one_off_events")
    if isinstance(events, list):
        cleaned_events: list[Any] = []
        for ev in events:
            if not isinstance(ev, dict):
                cleaned_events.append(ev)
                continue
            ev2 = dict(ev)
            for ek in ("amount_eur", "month_index", "direction", "type", "label"):
                if _contains_brackets(ev2.get(ek)):
                    warnings.append(
                        f"one_off_events.{ek}: bracketed value cleaned to null"
                    )
                    ev2[ek] = None
            cleaned_events.append(ev2)
        out["one_off_events"] = cleaned_events

    for key in list(stated_out.keys()):
        if key in {"scenario_shape", "industry", "company_size", "scenario_shape_quote"}:
            continue
        if key == "one_off_events" or key.startswith("one_off"):
            events = out.get("one_off_events") or []
            if not events:
                warnings.append(
                    f"{key}: listed in stated but value is null/empty — removed from stated"
                )
                logger.warning(
                    "%s listed in stated but value is null/empty — removed from stated",
                    key,
                )
                stated_out.pop(key, None)
            continue
        raw = _resolve_param_value(out, key)
        if raw is None or raw == "":
            warnings.append(
                f"{key}: listed in stated but value is null — removed from stated"
            )
            logger.warning(
                "%s listed in stated but value is null — removed from stated",
                key,
            )
            stated_out.pop(key, None)

    return out, stated_out, warnings


def extract_required_one_offs(description: str) -> list[dict[str, Any]]:
    """
    Parse one-offs that the description states with amount + direction + month.

    Example: ``One-off equipment outflow of 95,000 euro in month 5.``
    """
    blob = description or ""
    low = blob.lower()
    required: list[dict[str, Any]] = []

    # Strong event cues must sit near the amount (not a later sentence's outflow).
    event_cues = (
        "one-off",
        "one off",
        "capex",
        "equipment",
        "investment",
        "investointi",
        "kertaluonteinen",
        "grant",
        "korjaus",
        "repair",
    )
    # Cash labels that mean the amount is NOT a one-off.
    cash_labels = (
        "starting cash",
        "opening cash",
        "alkukassa",
        "monthly revenue",
        "revenue",
        "liikevaihto",
        "bank minimum",
        "minimum cash",
        "covenant",
        "kovenantti",
        "target cash",
    )

    for amt, idx in extract_euro_amounts(blob):
        if amt < 1_000:
            continue
        left = max(0, idx - 48)
        right = min(len(low), idx + 56)
        window = low[left:right]
        amt_pos = idx - left

        # Immediate left phrase only — do not let a prior sentence's "bank minimum"
        # suppress a later one-off amount.
        immediate_left = window[max(0, amt_pos - 28) : amt_pos]
        if any(lab in immediate_left for lab in cash_labels):
            continue

        direction: str | None = None
        # Direction must be close to the amount (same phrase).
        for d in _DIR_OUT:
            pos = window.find(d)
            if pos >= 0 and abs(pos - amt_pos) <= 40:
                direction = "outflow"
                break
        if direction is None:
            for d in _DIR_IN:
                pos = window.find(d)
                if pos >= 0 and abs(pos - amt_pos) <= 40:
                    direction = "inflow"
                    break
        if direction is None:
            continue

        month: int | None = None
        for pat in _MONTH_PATTERNS:
            m = re.search(pat, window, flags=re.IGNORECASE)
            if m:
                try:
                    month = int(m.group("m"))
                except (TypeError, ValueError, IndexError):
                    continue
                break
        if month is None or not (1 <= month <= 24):
            continue

        near_phrase = window[max(0, amt_pos - 40) : min(len(window), amt_pos + 24)]
        if not any(c in near_phrase for c in event_cues) and not any(
            d in near_phrase for d in ("outflow", "inflow")
        ):
            continue

        required.append(
            {
                "amount_eur": float(amt),
                "month_index": int(month),
                "direction": direction,
            }
        )

    # De-dupe by amount+month+direction
    uniq: list[dict[str, Any]] = []
    for req in required:
        if any(
            _near(float(req["amount_eur"]), float(u["amount_eur"]))
            and int(req["month_index"]) == int(u["month_index"])
            and req["direction"] == u["direction"]
            for u in uniq
        ):
            continue
        uniq.append(req)
    return uniq


def enforce_required_one_offs(
    events: Any,
    description: str,
) -> list[StatedIssue]:
    """
    If the description states amount + inflow/outflow + month, the extracted
    one-off list must include that amount, month, and direction. Empty list or
    wrong direction → error naming the missing one-off. Never drop silently.
    """
    required = extract_required_one_offs(description)
    if not required:
        return []

    issues: list[StatedIssue] = []
    event_list = events if isinstance(events, list) else []

    def _norm_dir(raw: Any) -> str:
        s = str(raw or "").strip().lower()
        if s in {"in", "inflow"}:
            return "inflow"
        if s in {"out", "outflow"}:
            return "outflow"
        return s

    for req in required:
        matched = False
        direction_mismatch = False
        for ev in event_list:
            if not isinstance(ev, dict):
                continue
            try:
                amt = float(ev.get("amount_eur") or 0)
                month = int(ev.get("month_index") or 0)
            except (TypeError, ValueError):
                continue
            if not _near(amt, float(req["amount_eur"])):
                continue
            if month != int(req["month_index"]):
                continue
            if _norm_dir(ev.get("direction")) != req["direction"]:
                direction_mismatch = True
                continue
            matched = True
            break
        if matched:
            continue
        label = (
            f"one-off {req['direction']} of {req['amount_eur']:g} euro "
            f"in month {req['month_index']}"
        )
        if direction_mismatch:
            issues.append(
                StatedIssue(
                    field="one_off_events",
                    message=(
                        f"missing required one-off (wrong direction): {label}"
                    ),
                )
            )
        elif not event_list:
            issues.append(
                StatedIssue(
                    field="one_off_events",
                    message=f"missing required one-off (empty list): {label}",
                )
            )
        else:
            issues.append(
                StatedIssue(
                    field="one_off_events",
                    message=f"missing required one-off: {label}",
                )
            )
    return issues


def apply_annual_to_monthly(parameters: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """If annual set and monthly null: monthly = annual / 12. Record conversion."""
    out = dict(parameters)
    changes: list[dict[str, Any]] = []
    monthly = out.get("revenue_monthly_eur")
    if monthly is None:
        monthly = out.get("monthly_revenue_start_eur")
    annual = out.get("revenue_annual_eur")
    if (monthly is None or monthly == "") and annual not in (None, ""):
        try:
            annual_f = float(annual)
        except (TypeError, ValueError):
            return out, changes
        monthly_f = round(annual_f / 12.0, 2)
        out["revenue_monthly_eur"] = monthly_f
        out["monthly_revenue_start_eur"] = monthly_f
        changes.append(
            {
                "field": "revenue_monthly_eur",
                "original": None,
                "clipped": monthly_f,
                "message": f"converted revenue_annual_eur={annual_f} / 12 → {monthly_f}",
                "source": "code_conversion",
            }
        )
    return out, changes


def check_growth_bounds(growth: float | None) -> StatedIssue | None:
    if growth is None:
        return None
    try:
        g = float(growth)
    except (TypeError, ValueError):
        return StatedIssue(field="growth_per_month_fraction", message="not a number")
    if g < GROWTH_MIN or g > GROWTH_MAX:
        return StatedIssue(
            field="growth_per_month_fraction",
            message=f"growth {g} outside [{GROWTH_MIN}, {GROWTH_MAX}]",
        )
    return None


def check_one_off_events(
    events: Any,
    *,
    months: int,
) -> list[StatedIssue]:
    issues: list[StatedIssue] = []
    if events is None:
        return issues
    if not isinstance(events, list):
        return [
            StatedIssue(field="one_off_events", message="must be an array"),
        ]
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            issues.append(StatedIssue(field=f"one_off_events[{i}]", message="must be object"))
            continue
        try:
            month = int(ev.get("month_index"))
        except (TypeError, ValueError):
            issues.append(
                StatedIssue(
                    field=f"one_off_events[{i}].month_index",
                    message="month_index required",
                )
            )
            continue
        if month < 1 or month > int(months):
            issues.append(
                StatedIssue(
                    field=f"one_off_events[{i}].month_index",
                    message=f"month_index {month} not in 1..{months}",
                )
            )
        direction = str(ev.get("direction") or "").strip().lower()
        if direction in {"in", "out"}:
            direction = "inflow" if direction == "in" else "outflow"
        if direction not in {"inflow", "outflow"}:
            issues.append(
                StatedIssue(
                    field=f"one_off_events[{i}].direction",
                    message="direction must be inflow or outflow",
                )
            )
    return issues


def map_b_parameters_to_engine(parameters: dict[str, Any]) -> dict[str, Any]:
    """Map section-B parameter names onto engine ``ParametersFromLanguageModel`` keys."""
    p = dict(parameters or {})
    out: dict[str, Any] = {}

    monthly = p.get("revenue_monthly_eur")
    if monthly is None:
        monthly = p.get("monthly_revenue_start_eur")
    if monthly is not None:
        out["monthly_revenue_start_eur"] = monthly

    growth = p.get("growth_per_month_fraction")
    if growth is None:
        growth = p.get("monthly_revenue_growth")
    if growth is not None:
        out["monthly_revenue_growth"] = growth

    if p.get("starting_cash_eur") is not None:
        out["starting_cash_eur"] = p["starting_cash_eur"]

    cov = p.get("covenant_min_cash_eur")
    if cov is not None:
        out["covenant_min_cash_eur"] = cov
        # Do not copy covenant into target_cash — assume fills target when null.

    dso = p.get("dso_days")
    if dso is None:
        dso = p.get("days_sales_outstanding")
    if dso is not None:
        out["days_sales_outstanding"] = dso

    dpo = p.get("dpo_days")
    if dpo is None:
        dpo = p.get("days_payables_outstanding")
    if dpo is not None:
        out["days_payables_outstanding"] = dpo

    events = p.get("one_off_events")
    if events:
        mapped: list[dict[str, Any]] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            direction = str(ev.get("direction") or "outflow").strip().lower()
            if direction in {"out", "outflow"}:
                direction = "outflow"
            elif direction in {"in", "inflow"}:
                direction = "inflow"
            mapped.append(
                {
                    "type": ev.get("type") or "other",
                    "amount_eur": ev.get("amount_eur"),
                    "month_index": ev.get("month_index"),
                    "direction": direction,
                    "label": ev.get("label"),
                }
            )
        out["one_off_events"] = mapped
        for ev in mapped:
            if ev.get("direction") == "outflow" and ev.get("amount_eur"):
                out["special_investment_eur"] = float(ev["amount_eur"])
                out["special_investment_month"] = int(ev.get("month_index") or 2)
                break

    if "revenue_annual_eur" in p:
        out["revenue_annual_eur"] = p.get("revenue_annual_eur")

    return out
