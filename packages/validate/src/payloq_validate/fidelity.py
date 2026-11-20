"""Fidelity check (blocking): every stated map-row value matches its output location.

Driven only by ``payloq_schemas.field_map`` — no fixed field list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from payloq_schemas.constants import (
    GROUNDING_ABSOLUTE_TOLERANCE_EUR,
    GROUNDING_RELATIVE_TOLERANCE,
)
from payloq_schemas.field_map import FieldMapRow, iter_field_map, read_output_location
from payloq_schemas.models import ParametersFromLanguageModel, ScenarioPack


@dataclass
class FidelityIssue:
    field: str
    expected: Any
    actual: Any
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "message": self.message,
            "severity": "error",
            "rule_id": "FIDELITY",
            "code": "fidelity",
        }


@dataclass
class FidelityResult:
    ok: bool
    issues: list[FidelityIssue] = field(default_factory=list)

    def error_text(self) -> str:
        return "; ".join(f"{i.field}: {i.message}" for i in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [i.as_dict() for i in self.issues],
        }


def _near(a: float, b: float) -> bool:
    if abs(a - b) <= GROUNDING_ABSOLUTE_TOLERANCE_EUR:
        return True
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= GROUNDING_RELATIVE_TOLERANCE


def _near_fraction(a: float, b: float) -> bool:
    if abs(a) < 1.0 and abs(b) < 1.0:
        return abs(a - b) <= max(1e-9, abs(b) * GROUNDING_RELATIVE_TOLERANCE)
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= GROUNDING_RELATIVE_TOLERANCE


def _as_params_dict(
    params: ParametersFromLanguageModel | dict[str, Any] | None,
) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, ParametersFromLanguageModel):
        return params.model_dump()
    return dict(params)


def _stated_for_row(
    row: FieldMapRow,
    *,
    sources: dict[str, str],
    quotes: dict[str, str],
    values: dict[str, Any],
) -> bool:
    # Primary keys only: input name + output key. Engine aliases beyond the
    # output key (e.g. special_investment_* for one_off_events) must not alone
    # mark the row stated — hand-authored packs often set special_investment
    # with an empty one_off_events list.
    keys = {row.input_name, row.output_key}
    for key in keys:
        if sources.get(key) == "stated":
            return True
        if key in quotes:
            return True
        if key in values and values.get(key) is not None:
            return True
    return False


def _expected_for_row(
    row: FieldMapRow,
    *,
    values: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    for key in (row.input_name, row.output_key, *row.engine_keys):
        if key in values and values[key] is not None:
            return values[key]
    if row.fidelity_rule == "one_off_events":
        return values.get("one_off_events") or params.get("one_off_events")
    if row.output_root == "parameters_from_language_model":
        return params.get(row.output_key)
    return values.get(row.input_name)


def _compare_numeric(
    row: FieldMapRow,
    expected: Any,
    actual: Any,
) -> FidelityIssue | None:
    if expected is None and actual is None:
        return None
    if actual is None:
        return FidelityIssue(
            field=row.input_name,
            expected=expected,
            actual=actual,
            message=(
                f"stated {row.input_name}={expected!r} has no value at "
                f"{row.output_location} (output={actual!r})"
            ),
        )
    if expected is None:
        return None
    try:
        exp_f = float(expected)
        act_f = float(actual)
    except (TypeError, ValueError):
        if expected != actual:
            return FidelityIssue(
                field=row.input_name,
                expected=expected,
                actual=actual,
                message=f"stated {expected!r} != output {actual!r}",
            )
        return None
    near = _near_fraction(exp_f, act_f) if row.format == "fraction" else _near(exp_f, act_f)
    if not near:
        return FidelityIssue(
            field=row.input_name,
            expected=exp_f,
            actual=act_f,
            message=f"stated {exp_f} != output {act_f}",
        )
    return None


def _normalize_one_off(ev: Any) -> dict[str, Any] | None:
    if isinstance(ev, dict):
        data = ev
    else:
        data = getattr(ev, "__dict__", None)
        if not isinstance(data, dict):
            return None
    direction = str(data.get("direction") or "").strip().lower()
    if direction in {"in", "inflow"}:
        direction = "inflow"
    elif direction in {"out", "outflow"}:
        direction = "outflow"
    try:
        amount = float(data.get("amount_eur"))
        month = int(data.get("month_index"))
    except (TypeError, ValueError):
        return None
    return {"amount_eur": amount, "month_index": month, "direction": direction}


def _compare_one_offs(
    row: FieldMapRow,
    expected: Any,
    actual: Any,
    params: dict[str, Any],
) -> list[FidelityIssue]:
    issues: list[FidelityIssue] = []
    exp_list = expected if isinstance(expected, list) else []
    act_list = actual if isinstance(actual, list) else []

    if not exp_list:
        # Stated empty list is fine when output is also empty/absent.
        if actual is None:
            issues.append(
                FidelityIssue(
                    field=row.input_name,
                    expected=expected,
                    actual=actual,
                    message=(
                        f"stated {row.input_name}={expected!r} has no value at "
                        f"{row.output_location} (output={actual!r})"
                    ),
                )
            )
        return issues

    exp_norm = [_normalize_one_off(e) for e in exp_list]
    exp_norm = [e for e in exp_norm if e is not None]
    act_norm = [_normalize_one_off(e) for e in act_list]
    act_norm = [e for e in act_norm if e is not None]

    for exp in exp_norm:
        match = next(
            (
                a
                for a in act_norm
                if a["direction"] == exp["direction"]
                and a["month_index"] == exp["month_index"]
                and _near(a["amount_eur"], exp["amount_eur"])
            ),
            None,
        )
        if match is None:
            # Fall back: outflow may live only as special_investment_* in older packs.
            if exp["direction"] == "outflow":
                inv = params.get("special_investment_eur")
                month = params.get("special_investment_month")
                if (
                    inv is not None
                    and _near(float(inv), exp["amount_eur"])
                    and month is not None
                    and int(month) == int(exp["month_index"])
                ):
                    continue
            issues.append(
                FidelityIssue(
                    field=row.input_name,
                    expected=exp,
                    actual=act_norm,
                    message=(
                        f"stated one_off amount={exp['amount_eur']} "
                        f"month={exp['month_index']} direction={exp['direction']} "
                        f"!= output {act_norm!r}"
                    ),
                )
            )
            continue
        # Also check special_investment mirror for outflows when present.
        if exp["direction"] == "outflow":
            inv = params.get("special_investment_eur")
            month = params.get("special_investment_month")
            if inv is not None and not _near(float(inv), exp["amount_eur"]):
                issues.append(
                    FidelityIssue(
                        field="special_investment_eur",
                        expected=exp["amount_eur"],
                        actual=inv,
                        message=f"stated {exp['amount_eur']} != output {inv}",
                    )
                )
            if month is not None and int(month) != int(exp["month_index"]):
                issues.append(
                    FidelityIssue(
                        field="special_investment_month",
                        expected=exp["month_index"],
                        actual=month,
                        message=f"stated {exp['month_index']} != output {month}",
                    )
                )
    return issues


def _compare_string(
    row: FieldMapRow,
    expected: Any,
    actual: Any,
) -> FidelityIssue | None:
    if expected is None:
        return None
    if actual is None:
        return FidelityIssue(
            field=row.input_name,
            expected=expected,
            actual=actual,
            message=(
                f"stated {row.input_name}={expected!r} has no value at "
                f"{row.output_location} (output={actual!r})"
            ),
        )
    if str(expected).strip().casefold() != str(actual).strip().casefold():
        return FidelityIssue(
            field=row.input_name,
            expected=expected,
            actual=actual,
            message=f"stated {expected!r} != output {actual!r}",
        )
    return None


def check_fidelity(
    pack: ScenarioPack | None = None,
    *,
    params: ParametersFromLanguageModel | dict[str, Any] | None = None,
    stated: dict[str, str] | None = None,
    stated_values: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> FidelityResult:
    """
    Blocking: for every field-map row marked stated, the value at that row's
    output_location matches the stated value (per the row's fidelity_rule).
    """
    issues: list[FidelityIssue] = []
    opts: dict[str, Any] = dict(options or {})

    if pack is not None:
        params = pack.input.parameters_from_language_model
        opts = pack.input.options.model_dump() if pack.input.options is not None else {}

    data = _as_params_dict(params)
    if not data and pack is None and not stated and not stated_values:
        return FidelityResult(ok=True, issues=[])

    sources = dict(data.get("field_sources") or {})
    quotes = dict(stated or data.get("field_quotes") or {})
    values = dict(stated_values or data.get("stated_values") or {})

    for row in iter_field_map():
        if not row.output_location:
            if _stated_for_row(row, sources=sources, quotes=quotes, values=values):
                issues.append(
                    FidelityIssue(
                        field=row.input_name,
                        expected=values.get(row.input_name),
                        actual=None,
                        message=(
                            f"stated {row.input_name}={values.get(row.input_name)!r} "
                            f"has no output location"
                        ),
                    )
                )
            continue

        if not _stated_for_row(row, sources=sources, quotes=quotes, values=values):
            continue

        actual = read_output_location(
            params=data, options=opts, location=row.output_location
        )
        expected = _expected_for_row(row, values=values, params=data)

        if row.fidelity_rule == "one_off_events":
            issues.extend(_compare_one_offs(row, expected, actual, data))
            continue

        if row.fidelity_rule == "exact_string":
            issue = _compare_string(row, expected, actual)
            if issue is not None:
                issues.append(issue)
            continue

        # Default / numeric_near
        issue = _compare_numeric(row, expected, actual)
        if issue is not None:
            issues.append(issue)

    return FidelityResult(ok=not issues, issues=issues)
