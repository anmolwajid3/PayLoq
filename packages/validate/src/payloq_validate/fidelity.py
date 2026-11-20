"""Fidelity check (blocking): every stated value appears in the matching output field."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from payloq_llm.stated_checks import B_TO_ENGINE, ENGINE_TO_B
from payloq_schemas.constants import (
    GROUNDING_ABSOLUTE_TOLERANCE_EUR,
    GROUNDING_RELATIVE_TOLERANCE,
)
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


def _param_value(params: ParametersFromLanguageModel | dict[str, Any], field: str) -> Any:
    data = params.model_dump() if isinstance(params, ParametersFromLanguageModel) else dict(params)
    engine = B_TO_ENGINE.get(field, field)
    if engine in data and data[engine] is not None:
        return data[engine]
    if field in data and data[field] is not None:
        return data[field]
    # one_off mirror
    if field in {"special_investment_eur", "one_off_events"} or "investment" in field or "capex" in field.casefold():
        if data.get("special_investment_eur"):
            return data.get("special_investment_eur")
        events = data.get("one_off_events") or []
        if events and isinstance(events, list) and isinstance(events[0], dict):
            return events[0].get("amount_eur")
    return data.get(engine)


def check_fidelity(
    pack: ScenarioPack | None = None,
    *,
    params: ParametersFromLanguageModel | dict[str, Any] | None = None,
    stated: dict[str, str] | None = None,
    stated_values: dict[str, Any] | None = None,
) -> FidelityResult:
    """
    Blocking: for every key in ``stated``, the matching output parameter equals the
    stated numeric value (from ``stated_values`` or params field_sources == stated).
    """
    issues: list[FidelityIssue] = []
    if pack is not None:
        params = pack.input.parameters_from_language_model
    if params is None:
        return FidelityResult(ok=True, issues=[])

    data = params.model_dump() if isinstance(params, ParametersFromLanguageModel) else dict(params)
    sources = dict(data.get("field_sources") or {})
    quotes = dict(stated or data.get("field_quotes") or {})
    values = dict(stated_values or data.get("stated_values") or {})

    # Fields to check: explicit stated map keys, else every source=stated scalar.
    fields: list[str] = list(quotes.keys()) if quotes else [
        k for k, v in sources.items() if v == "stated" and not k.startswith("cost_shares")
    ]

    for field_name in fields:
        if field_name in {"industry", "company_size", "scenario_shape"}:
            continue
        expected = values.get(field_name)
        if expected is None:
            expected = values.get(B_TO_ENGINE.get(field_name, field_name))
        if expected is None:
            # Fall back to the parameter itself when it is marked stated.
            expected = _param_value(data, field_name)
        actual = _param_value(data, field_name)

        if field_name == "one_off_events" or field_name.startswith("one_off"):
            events = data.get("one_off_events") or []
            exp_events = values.get("one_off_events")
            if exp_events is None and isinstance(events, list) and events:
                # Fidelity: special_investment mirrors first outflow.
                inv = data.get("special_investment_eur")
                month = data.get("special_investment_month")
                if inv and events:
                    ev0 = events[0] if isinstance(events[0], dict) else getattr(events[0], "__dict__", {})
                    try:
                        amt = float(ev0.get("amount_eur") if isinstance(ev0, dict) else events[0].amount_eur)
                        m_i = int(ev0.get("month_index") if isinstance(ev0, dict) else events[0].month_index)
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if inv is not None and not _near(float(inv), amt):
                        issues.append(
                            FidelityIssue(
                                field="special_investment_eur",
                                expected=amt,
                                actual=inv,
                                message=f"stated investment {amt} != output {inv}",
                            )
                        )
                    if month is not None and int(month) != m_i:
                        issues.append(
                            FidelityIssue(
                                field="special_investment_month",
                                expected=m_i,
                                actual=month,
                                message=f"stated month {m_i} != output {month}",
                            )
                        )
            continue

        if expected is None or actual is None:
            if sources.get(field_name) == "stated" or sources.get(
                B_TO_ENGINE.get(field_name, field_name)
            ) == "stated":
                if expected is not None and actual is None:
                    issues.append(
                        FidelityIssue(
                            field=field_name,
                            expected=expected,
                            actual=actual,
                            message=f"stated {field_name} missing from output",
                        )
                    )
            continue

        try:
            exp_f = float(expected)
            act_f = float(actual)
        except (TypeError, ValueError):
            if expected != actual:
                issues.append(
                    FidelityIssue(
                        field=field_name,
                        expected=expected,
                        actual=actual,
                        message=f"stated {expected!r} != output {actual!r}",
                    )
                )
            continue

        if not _near(exp_f, act_f):
            issues.append(
                FidelityIssue(
                    field=field_name,
                    expected=exp_f,
                    actual=act_f,
                    message=f"stated {exp_f} != output {act_f}",
                )
            )

    # Always verify engine fields marked stated match stated_values when provided.
    for eng_field, src in sources.items():
        if src != "stated":
            continue
        if eng_field.startswith("cost_shares") or eng_field in {
            "partly_fixed_costs",
            "one_off_events",
            "monthly_revenue_factors",
        }:
            continue
        b_name = ENGINE_TO_B.get(eng_field, eng_field)
        if b_name in fields or eng_field in fields:
            continue
        if b_name in values or eng_field in values:
            expected = values.get(b_name, values.get(eng_field))
            actual = data.get(eng_field)
            try:
                if expected is not None and actual is not None and not _near(
                    float(expected), float(actual)
                ):
                    issues.append(
                        FidelityIssue(
                            field=eng_field,
                            expected=expected,
                            actual=actual,
                            message=f"stated {expected} != output {actual}",
                        )
                    )
            except (TypeError, ValueError):
                pass

    return FidelityResult(ok=not issues, issues=issues)
