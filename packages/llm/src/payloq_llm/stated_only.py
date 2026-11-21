"""Stated-only model output and code-side derivations.

The model returns only numbers written in the description. Annual totals,
percent-to-decimal growth, and day counts from weeks or months are computed
here and recorded with source ``derived`` and the formula. No description-specific
branches — one formula table applied to whatever the model actually returned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from payloq_llm.extraction_schema import EXTRACTION_JSON_SCHEMA
from payloq_llm.stated_checks import _near_number, scan_description_numbers

_PERCENT_RE = re.compile(
    r"([+-]?\d+(?:[.,]\d+)?)\s*(?:%|percent\b|prosenttia\b)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Derivation:
    """One generic conversion. ``formula`` is ``<input> * factor`` or ``/ factor``."""

    field: str
    formula: str
    inputs: tuple[str, ...]
    also_set: tuple[str, ...] = ()


# Fixed order. Inputs are read from the pre-derivation snapshot so results do not chain
# (annual is not recomputed from a monthly that was itself derived from annual).
DERIVATIONS: tuple[Derivation, ...] = (
    Derivation(
        "revenue_annual_eur",
        "revenue_monthly_eur * 12",
        ("revenue_monthly_eur",),
    ),
    Derivation(
        "revenue_monthly_eur",
        "revenue_annual_eur / 12",
        ("revenue_annual_eur",),
        ("monthly_revenue_start_eur",),
    ),
    Derivation(
        "growth_per_month_fraction",
        "growth_per_month_percent / 100",
        ("growth_per_month_percent",),
        ("monthly_revenue_growth",),
    ),
    Derivation(
        "dso_days",
        "dso_weeks * 7",
        ("dso_weeks",),
        ("days_sales_outstanding",),
    ),
    Derivation(
        "dso_days",
        "dso_months * 30",
        ("dso_months",),
        ("days_sales_outstanding",),
    ),
    Derivation(
        "dpo_days",
        "dpo_weeks * 7",
        ("dpo_weeks",),
        ("days_payables_outstanding",),
    ),
    Derivation(
        "dpo_days",
        "dpo_months * 30",
        ("dpo_months",),
        ("days_payables_outstanding",),
    ),
)


def percent_literals(description: str) -> list[float]:
    """Percent figures as written (0.5 for ``0.5%``), not the decimal."""
    found: list[float] = []
    for match in _PERCENT_RE.finditer(description or ""):
        try:
            found.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return found


def literal_stated_numbers(description: str) -> list[float]:
    """Numbers written in the description. Does not add percent/100 or thousands fragments."""
    return scan_description_numbers(
        description,
        include_converted_fraction=False,
        skip_grouped_fragments=True,
    )


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _as_float(value: Any) -> float | None:
    if not _present(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_formula(formula: str, values: dict[str, Any]) -> float:
    """Apply a ``name * factor`` or ``name / factor`` formula. Same rounding every call."""
    match = re.fullmatch(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*([*/])\s*([0-9]+(?:\.[0-9]+)?)",
        (formula or "").strip(),
    )
    if match is None:
        raise ValueError(f"unsupported derivation formula: {formula!r}")
    name, op, factor_s = match.group(1), match.group(2), match.group(3)
    base = _as_float(values.get(name))
    if base is None:
        raise ValueError(f"formula {formula} missing input {name}")
    factor = float(factor_s)
    raw = base * factor if op == "*" else base / factor
    # Percent→decimal keeps extra digits; money and day counts round to cents.
    digits = 10 if factor == 100.0 else 2
    return round(raw, digits)


def _values_match(left: float, right: float) -> bool:
    if abs(left) < 1.0 and abs(right) < 1.0:
        return abs(left - right) <= 1e-8
    return abs(left - right) <= 0.02


def _type_names(spec: object) -> set[str]:
    found: set[str] = set()
    if isinstance(spec, dict):
        raw = spec.get("type")
        if isinstance(raw, str):
            found.add(raw)
        for item in spec.get("anyOf") or []:
            found |= _type_names(item)
    return found


def _schema_fields() -> tuple[list[str], list[str]]:
    """Numeric model fields, then string model fields, from the extraction schema."""
    props = (
        EXTRACTION_JSON_SCHEMA.get("properties", {})
        .get("parameters", {})
        .get("properties", {})
    )
    numeric: list[str] = []
    strings: list[str] = []
    for name, spec in props.items():
        if name == "one_off_events":
            continue
        types = _type_names(spec)
        if "string" in types and "number" not in types and "integer" not in types:
            strings.append(name)
        else:
            numeric.append(name)
    return numeric, strings


def _move_stated_key(stated: dict[str, str], old: str, new: str) -> None:
    if old in stated and new not in stated:
        stated[new] = stated.pop(old)
    else:
        stated.pop(old, None)


def normalize_growth_to_stated_percent(
    parameters: dict[str, Any],
    stated: dict[str, str],
    description: str,
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """
    Put the percent figure in ``growth_per_month_percent``.

    A model that already divided by 100 (or copied the percent into the fraction
    field) does not get to keep that conversion. Code derives the decimal later.
    A fraction that is itself written in the description, with no percent sign,
    stays as a direct statement.
    """
    out = dict(parameters)
    stated_out = dict(stated)
    warnings: list[str] = []
    percent = _as_float(out.get("growth_per_month_percent"))
    fraction = _as_float(out.get("growth_per_month_fraction"))
    if fraction is None:
        fraction = _as_float(out.get("monthly_revenue_growth"))
    percents = percent_literals(description)

    if percent is None and fraction is not None and percents:
        for figure in percents:
            if _values_match(fraction, figure / 100.0) or _values_match(fraction, figure):
                out["growth_per_month_percent"] = figure
                warnings.append(
                    "growth model value moved to growth_per_month_percent; "
                    "decimal is derived as growth_per_month_percent / 100"
                )
                for old in ("growth_per_month_fraction", "monthly_revenue_growth"):
                    _move_stated_key(stated_out, old, "growth_per_month_percent")
                break

    if _present(out.get("growth_per_month_percent")):
        # The decimal is never part of the model output when a percent was stated.
        if _present(out.get("growth_per_month_fraction")) or _present(
            out.get("monthly_revenue_growth")
        ):
            warnings.append(
                "dropped model growth fraction; code derives growth_per_month_percent / 100"
            )
        out["growth_per_month_fraction"] = None
        out["monthly_revenue_growth"] = None
        stated_out.pop("growth_per_month_fraction", None)
        stated_out.pop("monthly_revenue_growth", None)
    elif fraction is not None and not percents:
        literal = literal_stated_numbers(description)
        if not any(_near_number(fraction, n) for n in literal):
            out["growth_per_month_fraction"] = None
            out["monthly_revenue_growth"] = None
            stated_out.pop("growth_per_month_fraction", None)
            stated_out.pop("monthly_revenue_growth", None)
            warnings.append("unstated growth fraction removed from model output")
    return out, stated_out, warnings


def _null_formula_outputs_not_stated(
    parameters: dict[str, Any],
    stated: dict[str, str],
) -> list[str]:
    """Drop model-supplied conversions so code can record them as derived."""
    warnings: list[str] = []
    base = dict(parameters)
    claimed = set(stated)
    for spec in DERIVATIONS:
        if spec.field in claimed or any(alias in claimed for alias in spec.also_set):
            continue
        if any(not _present(base.get(name)) for name in spec.inputs):
            continue
        try:
            expected = evaluate_formula(spec.formula, base)
        except ValueError:
            continue
        current = _as_float(base.get(spec.field))
        alias_hit: str | None = None
        if current is None:
            for alias in spec.also_set:
                alias_val = _as_float(base.get(alias))
                if alias_val is not None and _values_match(alias_val, expected):
                    current = alias_val
                    alias_hit = alias
                    break
        if current is None or not _values_match(current, expected):
            continue
        parameters[spec.field] = None
        for alias in spec.also_set:
            parameters[alias] = None
        warnings.append(
            f"removed model conversion {alias_hit or spec.field}={current}; "
            f"code derives {spec.formula}"
        )
    return warnings


def prepare_stated_only_model(
    parameters: dict[str, Any],
    stated: dict[str, str] | None,
    description: str,
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """
    Model output contract: only directly stated fields are non-null.

    Calculated annual, decimal growth, and converted day counts are removed
    here. ``apply_derivations`` writes them back with source ``derived``.
    """
    stated_out = dict(stated or {})
    out, stated_out, warnings = normalize_growth_to_stated_percent(
        dict(parameters or {}), stated_out, description
    )
    numeric, strings = _schema_fields()
    numbers = literal_stated_numbers(description)
    # Keep a number when the model marked the field stated, or when that number
    # is written in the description (code-parsed NL uses the second path).
    # Drop every other model value — including conversions, which the formula
    # pass removes even if the converted figure happens to be written.
    for name in numeric:
        if name in stated_out:
            continue
        val = _as_float(out.get(name))
        if val is None:
            continue
        if any(_near_number(val, n) for n in numbers):
            continue
        out[name] = None
        warnings.append(f"{name}: unstated model value {val} set to null")

    for name in strings:
        if name in stated_out:
            continue
        if _present(out.get(name)):
            out[name] = None
            warnings.append(f"{name}: unstated model value set to null")

    warnings.extend(_null_formula_outputs_not_stated(out, stated_out))
    return out, stated_out, warnings


def apply_derivations(
    parameters: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Fill null outputs from the formula table.

    Each record has source ``derived``, the formula, and the value. Records are
    sorted by field then formula so output bytes do not depend on dict order.
    """
    out = dict(parameters or {})
    base = dict(out)
    records: list[dict[str, Any]] = []
    for spec in DERIVATIONS:
        if _present(out.get(spec.field)):
            continue
        if any(not _present(base.get(name)) for name in spec.inputs):
            continue
        try:
            value = evaluate_formula(spec.formula, base)
        except ValueError:
            continue
        keys = tuple(sorted({spec.field, *spec.also_set}))
        out[spec.field] = value
        for alias in spec.also_set:
            if not _present(out.get(alias)):
                out[alias] = value
        records.append(
            {
                "field": spec.field,
                "formula": spec.formula,
                "source": "derived",
                "value": value,
                "keys": list(keys),
            }
        )
    records.sort(key=lambda rec: (str(rec["field"]), str(rec["formula"])))
    return out, records
