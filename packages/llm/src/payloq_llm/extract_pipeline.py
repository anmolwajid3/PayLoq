"""NL → parameters pipeline: extract (B) → clean → value ground (C) → assume (D).

Code calculates; the LLM only returns stated values (null when unstated).
Grounding is value-based (numbers in the description), not quote-string matching.
"""

from __future__ import annotations

from typing import Any, Callable

from payloq_llm.assume import apply_assumed_defaults, drop_incomplete_one_off_events
from payloq_llm.nl_cash_intent import looks_cash_critical
from payloq_llm.stated_checks import (
    check_growth_bounds,
    check_one_off_events,
    check_stated_values,
    clean_extraction_output,
    enforce_required_one_offs,
    map_b_parameters_to_engine,
    normalize_stated_map,
    reject_ungrounded_one_offs,
)
from payloq_llm.stated_only import apply_derivations, prepare_stated_only_model
from payloq_schemas.field_map import b_to_engine_from_map
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
    Full post-extract path: B normalize → clean → C value ground → annual → D assume.

    Returns (params_dict, change_log, stated_check_result).
    When stated_check.ok is False, caller should retry the LLM once.
    """
    _ = require_starting_cash
    envelope = normalize_extraction_payload(raw_data)
    scenario_shape = str(envelope.get("scenario_shape") or "unspecified").strip().lower()
    scenario_shape_quote = envelope.get("scenario_shape_quote")
    # Code interprets cash-stress cues: upgrade under-classified shapes so the
    # generator profile can produce a falling projection (TC-A).
    # Keyword upgrade only fills an unspecified shape; an explicit model shape stands.
    if looks_cash_critical(description) and scenario_shape in {"unspecified", ""}:
        scenario_shape = "cash_critical"
    parameters = dict(envelope.get("parameters") or {})
    stated = normalize_stated_map(envelope.get("stated") or {}, parameters)

    # TC-ABC item 3: clean before validation.
    parameters, stated, clean_warnings = clean_extraction_output(
        parameters, stated, description
    )
    # Model output keeps only directly stated fields. Conversions are stripped
    # and reapplied below with source "derived".
    parameters, stated, stated_only_warnings = prepare_stated_only_model(
        parameters, stated, description
    )
    # Options fields echo request config in field_quotes (H8 stability) but their
    # stated values are kept in stated_values for generic field-map fidelity.
    option_stated_values: dict[str, Any] = {}
    for opt_key in ("industry", "company_size"):
        if opt_key in stated and parameters.get(opt_key) not in (None, ""):
            option_stated_values[opt_key] = parameters[opt_key]
        stated.pop(opt_key, None)

    stated_result = check_stated_values(
        description=description,
        stated=stated,
        parameters=parameters,
    )
    stated_result.warnings.extend(clean_warnings)
    stated_result.warnings.extend(stated_only_warnings)

    cleaned_events, _drop = drop_incomplete_one_off_events(parameters.get("one_off_events"))
    parameters["one_off_events"] = cleaned_events
    event_issues = check_one_off_events(
        parameters.get("one_off_events"), months=months
    )
    if event_issues:
        stated_result.issues.extend(event_issues)
        stated_result.ok = False

    # TC-ABC item 4: required one-offs from description must be present with
    # matching direction — never drop silently.
    one_off_req_issues = enforce_required_one_offs(
        parameters.get("one_off_events"), description
    )
    if one_off_req_issues:
        stated_result.issues.extend(one_off_req_issues)
        stated_result.ok = False

    # Invented one-offs: drop ungrounded events with a warning instead of aborting
    # the whole Generate run (models often mistype revenue as a one-off inflow).
    # Required stated one-offs still hard-fail above via enforce_required_one_offs.
    ungrounded_issues = reject_ungrounded_one_offs(parameters.get("one_off_events"), description)
    if ungrounded_issues:
        drop_fields = {issue.field for issue in ungrounded_issues}
        events = parameters.get("one_off_events") or []
        kept: list[Any] = []
        for i, ev in enumerate(events):
            field = f"one_off_events[{i}]"
            if field in drop_fields:
                continue
            kept.append(ev)
        parameters["one_off_events"] = kept
        for issue in ungrounded_issues:
            stated_result.warnings.append(f"dropped invented {issue.field}: {issue.message}")

    if not stated_result.ok:
        return {
            "scenario_shape": scenario_shape,
            "scenario_shape_quote": scenario_shape_quote,
            "stated": stated,
            "parameters": parameters,
            "warnings": list(stated_result.warnings),
        }, [], stated_result

    parameters, derived_records = apply_derivations(parameters)
    growth = parameters.get("growth_per_month_fraction")
    if growth is None:
        growth = parameters.get("monthly_revenue_growth")
    g_issue = check_growth_bounds(growth if growth is not None else None)
    if g_issue is not None and growth is not None:
        stated_result.issues.append(g_issue)
        stated_result.ok = False
        return {
            "scenario_shape": scenario_shape,
            "scenario_shape_quote": scenario_shape_quote,
            "stated": stated,
            "parameters": parameters,
            "warnings": list(stated_result.warnings),
        }, [], stated_result

    engine = map_b_parameters_to_engine(parameters)
    b_to_eng = b_to_engine_from_map()
    derived_keys = {
        str(key)
        for rec in derived_records
        for key in (rec.get("keys") or [rec["field"]])
    }

    stated_values: dict[str, Any] = dict(option_stated_values)
    for b_name in sorted(stated):
        if parameters.get(b_name) is None or parameters.get(b_name) == "":
            continue
        stated_values[b_name] = parameters[b_name]
        eng = b_to_eng.get(b_name, b_name)
        if eng in derived_keys:
            continue
        if eng != b_name and engine.get(eng) is not None:
            stated_values[eng] = engine[eng]
    if "one_off_events" in stated and parameters.get("one_off_events") is not None:
        stated_values["one_off_events"] = parameters.get("one_off_events")
        if engine.get("one_off_events") is not None:
            stated_values["one_off_events"] = engine.get("one_off_events")

    resolved_industry = parameters.get("industry") or industry
    resolved_size = parameters.get("company_size") or company_size

    sources: dict[str, str] = {key: "derived" for key in sorted(derived_keys)}
    for b_name in sorted(stated):
        if parameters.get(b_name) is None or parameters.get(b_name) == "":
            continue
        sources[b_name] = "stated"
        eng = b_to_eng.get(b_name, b_name)
        if eng not in derived_keys:
            sources[eng] = "stated"
    # Option fields stated in extraction: record provenance for Run summary.
    for opt_key in sorted(option_stated_values):
        opt_val = option_stated_values[opt_key]
        if opt_val is not None and opt_val != "":
            sources[opt_key] = "stated"
    engine["field_sources"] = dict(sorted(sources.items()))
    engine["field_quotes"] = {
        b_to_eng.get(k, k): v for k, v in sorted(stated.items())
    }
    engine["stated_values"] = {
        str(k): stated_values[k] for k in sorted(stated_values, key=str)
    }
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
    changes = list(derived_records) + list(assume_changes)
    for w in stated_result.warnings:
        changes.append(
            {
                "field": "_clean",
                "original": None,
                "clipped": None,
                "message": w,
                "source": "clean_output",
            }
        )
    filled.pop("_assume_meta", None)
    filled["derived_values"] = list(derived_records)
    filled["conversion_notes"] = list(derived_records)
    filled["llm_model_name"] = llm_model_name
    filled["extraction_seed"] = seed
    filled["field_quotes"] = dict(sorted(engine["field_quotes"].items()))
    filled["stated_values"] = dict(
        sorted(engine["stated_values"].items(), key=lambda kv: str(kv[0]))
    )
    filled["scenario_shape"] = scenario_shape
    filled["scenario_shape_quote"] = scenario_shape_quote
    if filled.get("revenue_annual_eur") is None and parameters.get("revenue_annual_eur") is not None:
        filled["revenue_annual_eur"] = parameters.get("revenue_annual_eur")

    params = ParametersFromLanguageModel.model_validate(filled)
    dumped = params.model_dump()
    # Re-sort provenance maps after pydantic round-trip (stable input.json bytes).
    for key in ("field_sources", "field_quotes", "stated_values"):
        raw = dumped.get(key)
        if isinstance(raw, dict):
            dumped[key] = dict(sorted(raw.items(), key=lambda kv: str(kv[0])))
    return dumped, changes, stated_result


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
