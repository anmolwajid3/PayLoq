"""NL → parameters pipeline: extract → ground → assume (work order A/B).

Code calculates; the LLM only returns stated values (null when unstated).
Code-first NL parse runs before/alongside LLM JSON so weak models cannot
omit required stated figures or override grounded numbers.
"""

from __future__ import annotations

from typing import Any, Callable

from payloq_llm.assume import MissingRequiredParameterError, apply_assumed_defaults
from payloq_llm.grounding import (
    GroundingResult,
    ground_stated_parameters,
    mark_stated_sources,
)
from payloq_llm.nl_stated import extract_stated_params_from_nl, merge_llm_with_code_stated
from payloq_llm.params_coerce import normalize_monthly_revenue_factors
from payloq_schemas.models import ExtractedParameters, ParametersFromLanguageModel


def normalize_aliases(data: dict[str, Any]) -> dict[str, Any]:
    """Apply WO ↔ legacy field aliases without inventing values."""
    return dict(ParametersFromLanguageModel._accept_wo_aliases(dict(data or {})))


def prepare_extracted_dict(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize aliases + seasonality factors only (no default fills)."""
    out = normalize_aliases(data)
    changes: list[dict[str, Any]] = []
    if "monthly_revenue_factors" in out and out.get("monthly_revenue_factors") is not None:
        try:
            start = out.get("monthly_revenue_start_eur")
            start_eur = float(start) if start not in (None, "") else None
        except (TypeError, ValueError):
            start_eur = None
        factors, fchg = normalize_monthly_revenue_factors(
            out.get("monthly_revenue_factors"), start_eur=start_eur
        )
        changes.extend(fchg)
        out["monthly_revenue_factors"] = factors
    return out, changes


def finalize_extracted_parameters(
    raw_data: dict[str, Any],
    description: str,
    *,
    industry: str | None,
    company_size: str | None,
    seed: int,
    require_starting_cash: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]], GroundingResult]:
    """
    Full post-extract path: code-NL ∪ LLM → normalize → ground → assume.

    Returns (params_dict, change_log, grounding_result).
    Raises MissingRequiredParameterError when starting_cash_eur is required and
    absent from both the description and the LLM payload.
    When grounding.ok is False, caller should retry the LLM once with the error text.
    """
    code_stated = extract_stated_params_from_nl(description)
    merged_raw, merge_changes = merge_llm_with_code_stated(raw_data, code_stated)

    data, changes = prepare_extracted_dict(merged_raw)
    changes = merge_changes + changes
    extracted = ExtractedParameters.model_validate(data)
    data = extracted.model_dump()
    # Preserve code-stated provenance through Pydantic round-trip.
    sources = mark_stated_sources(data)
    for key, src in (merged_raw.get("field_sources") or {}).items():
        if src == "stated":
            sources[key] = "stated"
    data["field_sources"] = sources

    grounding = ground_stated_parameters(data, description, field_sources=sources)
    if not grounding.ok:
        return data, changes, grounding

    filled, assume_changes = apply_assumed_defaults(
        data,
        industry=industry,
        company_size=company_size,
        seed=seed,
        description=description,
        require_starting_cash=require_starting_cash,
    )
    changes.extend(assume_changes)

    filled.pop("_assume_meta", None)
    # Drop internal hybrid marker before schema validate if present on raw path.
    filled.pop("_extraction_mode", None)
    params = ParametersFromLanguageModel.model_validate(filled)
    return params.model_dump(), changes, grounding


def extract_with_grounding_retry(
    *,
    description: str,
    industry: str | None,
    company_size: str | None,
    seed: int,
    initial_raw: str,
    parse_raw: Callable[[str], dict[str, Any]],
    repair_raw: Callable[[str, str], str],
    require_starting_cash: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """
    Parse → finalize; on grounding failure retry once with the error listed in the prompt.

    Returns (params, changes, last_raw). Assume seed stays fixed across the LLM retry.
    """
    raw = initial_raw
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            data = parse_raw(raw)
            params, changes, grounding = finalize_extracted_parameters(
                data,
                description,
                industry=industry,
                company_size=company_size,
                seed=seed,
                require_starting_cash=require_starting_cash,
            )
            if not grounding.ok:
                raise ValueError(grounding.error_text())
            return params, changes, raw
        except MissingRequiredParameterError:
            raise
        except Exception as exc:  # noqa: BLE001 — grounding / parse / validate
            last_err = exc
            if attempt >= 1:
                break
            raw = repair_raw(raw, str(exc))
    raise ValueError(f"parameter extraction failed after grounding retry: {last_err}")
