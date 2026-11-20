"""NL → parameters pipeline: extract (B) → stated checks (C) → assume (D).

Code calculates; the LLM only returns stated values (null when unstated).
"""

from __future__ import annotations

from typing import Any, Callable

from payloq_llm.assume import apply_assumed_defaults, drop_incomplete_one_off_events
from payloq_llm.stated_checks import (
    apply_annual_to_monthly,
    check_growth_bounds,
    check_one_off_events,
    check_stated_quotes,
    map_b_parameters_to_engine,
    normalize_stated_map,
)
from payloq_schemas.models import ParametersFromLanguageModel
from payloq_schemas.scenario_shape_ranges import profile_for_shape



def normalize_aliases(data: dict[str, Any]) -> dict[str, Any]:
    """Apply WO ↔ legacy field aliases without inventing values."""
    return dict(ParametersFromLanguageModel._accept_wo_aliases(dict(data or {})))


def prepare_extracted_dict(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize aliases only (legacy helper for tests)."""
    return normalize_aliases(data), []


def normalize_extraction_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept section-B envelope or flat legacy params dict."""
    data = dict(raw or {})
    if "parameters" in data and isinstance(data["parameters"], dict):
        return data
    return {
        "scenario_shape": data.get("scenario_shape") or "unspecified",
        "scenario_shape_quote": data.get("scenario_shape_quote"),
        "stated": dict(data.get("stated") or data.get("field_quotes") or {}),
        "parameters": data,
    }


def finalize_extracted_parameters(
    raw_data: dict[str, Any],
    description: str,
    *,
    industry: str | None,
    company_size: str | None,
    seed: int,
    months: int = 12,
    require_starting_cash: bool = False,
    llm_model_name: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    """
    Full post-extract path: B normalize → C stated checks → annual convert → D assume.

    Returns (params_dict, change_log, stated_check_result).
    When stated_check.ok is False, caller should retry the LLM once.
    """
    _ = require_starting_cash
    envelope = normalize_extraction_payload(raw_data)
    scenario_shape = envelope.get("scenario_shape") or "unspecified"
    scenario_shape_quote = envelope.get("scenario_shape_quote")
    parameters = dict(envelope.get("parameters") or {})
    stated = normalize_stated_map(envelope.get("stated") or {}, parameters)
    # Options fields often echo config, not the NL description — drop if quote absent.
    desc_l = (description or "").casefold()
    for opt_key in ("industry", "company_size"):
        q = stated.get(opt_key)
        if q is not None and str(q).casefold() not in desc_l:
            stated.pop(opt_key, None)

    for key in list(parameters.keys()):
        if key in {"one_off_events", "industry", "company_size"}:
            continue
        if key not in stated and parameters.get(key) == 0:
            parameters[key] = None

    stated_result = check_stated_quotes(
        description=description,
        stated=stated,
        parameters=parameters,
    )

    growth = parameters.get("growth_per_month_fraction")
    if growth is None:
        growth = parameters.get("monthly_revenue_growth")
    g_issue = check_growth_bounds(growth if growth is not None else None)
    if g_issue is not None and growth is not None:
        stated_result.issues.append(g_issue)
        stated_result.ok = False

    cleaned_events, _drop = drop_incomplete_one_off_events(parameters.get("one_off_events"))
    parameters["one_off_events"] = cleaned_events
    event_issues = check_one_off_events(
        parameters.get("one_off_events"), months=months
    )
    if event_issues:
        stated_result.issues.extend(event_issues)
        stated_result.ok = False

    if not stated_result.ok:
        return {
            "scenario_shape": scenario_shape,
            "scenario_shape_quote": scenario_shape_quote,
            "stated": stated,
            "parameters": parameters,
        }, [], stated_result

    parameters, conv_changes = apply_annual_to_monthly(parameters)
    engine = map_b_parameters_to_engine(parameters)

    stated_values: dict[str, Any] = {}
    b_to_eng = {
        "revenue_monthly_eur": "monthly_revenue_start_eur",
        "growth_per_month_fraction": "monthly_revenue_growth",
        "dso_days": "days_sales_outstanding",
        "dpo_days": "days_payables_outstanding",
        "covenant_min_cash_eur": "covenant_min_cash_eur",
        "starting_cash_eur": "starting_cash_eur",
    }
    for b_name in stated:
        if b_name in parameters and parameters[b_name] is not None:
            stated_values[b_name] = parameters[b_name]
        eng = b_to_eng.get(b_name, b_name)
        if eng in engine and engine[eng] is not None:
            stated_values[eng] = engine[eng]
            stated_values[b_name] = engine[eng]

    resolved_industry = parameters.get("industry") or industry
    resolved_size = parameters.get("company_size") or company_size

    sources = {k: "stated" for k in engine if engine.get(k) is not None}
    engine["field_sources"] = sources
    engine["field_quotes"] = {
        b_to_eng.get(k, k): v for k, v in stated.items()
    }
    engine["stated_values"] = stated_values
    engine["scenario_shape"] = scenario_shape
    engine["scenario_shape_quote"] = scenario_shape_quote

    filled, assume_changes = apply_assumed_defaults(
        engine,
        industry=resolved_industry,
        company_size=resolved_size,
        seed=seed,
        description=description,
        require_starting_cash=False,
        scenario_shape=scenario_shape,
    )
    changes = list(conv_changes) + list(assume_changes)
    filled.pop("_assume_meta", None)
    filled["conversion_notes"] = list(conv_changes)
    filled["llm_model_name"] = llm_model_name
    filled["extraction_seed"] = seed
    filled["field_quotes"] = engine["field_quotes"]
    filled["stated_values"] = stated_values
    filled["scenario_shape"] = scenario_shape
    filled["scenario_shape_quote"] = scenario_shape_quote
    if filled.get("revenue_annual_eur") is None and parameters.get("revenue_annual_eur") is not None:
        filled["revenue_annual_eur"] = parameters.get("revenue_annual_eur")

    params = ParametersFromLanguageModel.model_validate(filled)
    return params.model_dump(), changes, stated_result


def extract_with_grounding_retry(
    *,
    description: str,
    industry: str | None,
    company_size: str | None,
    seed: int,
    initial_raw: str,
    parse_raw: Callable[[str], dict[str, Any]],
    repair_raw: Callable[[str, str], str],
    require_starting_cash: bool = False,
    months: int = 12,
    llm_model_name: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Parse → finalize; on stated-check failure retry once."""
    _ = require_starting_cash
    raw = initial_raw
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            data = parse_raw(raw)
            params, changes, stated_check = finalize_extracted_parameters(
                data,
                description,
                industry=industry,
                company_size=company_size,
                seed=seed,
                months=months,
                require_starting_cash=False,
                llm_model_name=llm_model_name,
            )
            if not stated_check.ok:
                raise ValueError(stated_check.error_text())
            return params, changes, raw
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt >= 1:
                break
            raw = repair_raw(raw, str(exc))
    raise ValueError(f"parameter extraction failed after stated-check retry: {last_err}")


def scenario_id_from_shape(scenario_shape: str | None) -> str:
    return profile_for_shape(scenario_shape)
