"""Generate → validate → (retry seeds) → write artifacts (VR-30..32)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from payloq_generator.answer_key import build_answer_key
from payloq_generator.engine import break_receivables_mismatch, generate_pack, write_pack
from payloq_generator.params_clamp import clamp_parameters
from payloq_schemas.models import GeneratorInput, ScenarioPack
from payloq_validate.checks import ValidationResult, validate_pack


@dataclass
class GenerationOutcome:
    ok: bool
    pack: ScenarioPack | None
    out_dir: Path
    validation: ValidationResult
    seed_used: int
    seed_attempts: list[dict[str, Any]] = field(default_factory=list)
    param_clips: list[dict[str, Any]] = field(default_factory=list)
    answer_key: dict[str, Any] | None = None
    test_only_broken: bool = False
    error_message: str | None = None


def run_generation(
    inp: GeneratorInput,
    out_dir: Path,
    *,
    seed: int = 42,
    max_seed_attempts: int = 3,
    write_xlsx: bool = True,
    write_journal: bool = True,
    raw_llm_output: str | None = None,
    llm_name: str | None = None,
    clamp: bool = True,
) -> GenerationOutcome:
    """
    Full Task A pipeline.

    VR-30: on failure, do not write final data files (only run_log + optional raw LLM).
    VR-31: do not silently fix validation failures.
    VR-32: try up to ``max_seed_attempts`` seeds (seed, seed+1, …), log each attempt.

    Special case: ``invoices_out_of_balance`` is deliberately broken (TEST_ONLY_BROKEN):
    validation MUST fail VR-05; files are still written and labelled.
    """
    out_dir = Path(out_dir)
    working = inp.model_copy(deep=True)
    clips: list[dict[str, Any]] = []
    # NL covenant / winter-cash / one-off / size repair before numeric clamp.
    try:
        from payloq_llm.nl_cash_intent import repair_params_from_nl
        from payloq_llm.nl_param_hints import repair_investment_and_revenue_from_nl

        desc = (
            f"{working.scenario_description.fi} {working.scenario_description.en}"
        ).strip()
        if desc:
            repaired, nl_clips = repair_params_from_nl(
                desc, working.parameters_from_language_model.model_dump()
            )
            repaired, inv_clips = repair_investment_and_revenue_from_nl(
                desc,
                repaired,
                industry=str(working.options.industry or ""),
                company_size=str(getattr(working.options, "company_size", "") or ""),
            )
            nl_clips = list(nl_clips) + list(inv_clips)
            if nl_clips:
                from payloq_schemas.models import ParametersFromLanguageModel as _Params

                working.parameters_from_language_model = _Params.model_validate(repaired)
                clips.extend(nl_clips)
    except ImportError:  # pragma: no cover
        pass
    if clamp:
        clamped, clamp_clips = clamp_parameters(working.parameters_from_language_model)
        working.parameters_from_language_model = clamped
        clips.extend(clamp_clips)
    # Work order B: reject inconsistent parameters before generation.
    from payloq_generator.consistency import require_consistent

    require_consistent(working.parameters_from_language_model)

    sid = (working.options.scenario_id or working.meta.scenario or "").lower()
    deliberate_broken = sid in {"invoices_out_of_balance", "test_only_broken"}

    attempts: list[dict[str, Any]] = []
    last_pack: ScenarioPack | None = None
    last_result = ValidationResult(ok=False)
    seed_used = seed

    for attempt_i in range(max_seed_attempts):
        seed_used = seed + attempt_i
        pack = generate_pack(working, seed=seed_used)
        if deliberate_broken:
            pack = break_receivables_mismatch(pack)
        answer_key = build_answer_key(pack)
        # For deliberate broken, skip VR-11 mismatch noise: still validate data rules
        result = validate_pack(pack, answer_key=None if deliberate_broken else answer_key)
        attempts.append(
            {
                "attempt": attempt_i + 1,
                "seed": seed_used,
                "ok": result.ok,
                "failing_rules": result.failing_rule_ids(),
                "issues": [i.as_dict() for i in result.issues if i.severity == "error"],
            }
        )
        last_pack = pack
        last_result = result

        if deliberate_broken:
            # Success criterion for this scenario: VR-05 fails (AC-07)
            vr05 = any((i.rule_id or i.code) == "VR-05" for i in result.issues)
            if vr05:
                write_pack(
                    pack,
                    out_dir,
                    write_xlsx=write_xlsx,
                    write_journal=write_journal,
                    seed=seed_used,
                    raw_llm_output=raw_llm_output,
                    llm_name=llm_name,
                    validation=result.as_dict(),
                    seed_attempts=attempts,
                    number_of_retries=attempt_i,
                    param_clips=clips,
                    test_only_broken=True,
                    write_data_files=True,
                )
                return GenerationOutcome(
                    ok=True,  # test scenario fulfilled its purpose
                    pack=pack,
                    out_dir=out_dir,
                    validation=result,
                    seed_used=seed_used,
                    seed_attempts=attempts,
                    param_clips=clips,
                    answer_key=answer_key,
                    test_only_broken=True,
                )
            # VR-05 did not fire — try next seed
            continue

        if result.ok:
            write_pack(
                pack,
                out_dir,
                write_xlsx=write_xlsx,
                write_journal=write_journal,
                seed=seed_used,
                raw_llm_output=raw_llm_output,
                llm_name=llm_name,
                validation=result.as_dict(),
                seed_attempts=attempts,
                number_of_retries=attempt_i,
                param_clips=clips,
                write_data_files=True,
            )
            return GenerationOutcome(
                ok=True,
                pack=pack,
                out_dir=out_dir,
                validation=result,
                seed_used=seed_used,
                seed_attempts=attempts,
                param_clips=clips,
                answer_key=answer_key,
            )

    # All attempts failed — VR-30: do not write final data files
    if last_pack is not None:
        write_pack(
            last_pack,
            out_dir,
            write_xlsx=False,
            write_journal=False,
            seed=seed_used,
            raw_llm_output=raw_llm_output,
            llm_name=llm_name,
            validation=last_result.as_dict(),
            seed_attempts=attempts,
            number_of_retries=max(0, max_seed_attempts - 1),
            param_clips=clips,
            test_only_broken=deliberate_broken,
            write_data_files=False,
        )

    return GenerationOutcome(
        ok=False,
        pack=last_pack,
        out_dir=out_dir,
        validation=last_result,
        seed_used=seed_used,
        seed_attempts=attempts,
        param_clips=clips,
        test_only_broken=deliberate_broken,
        error_message=(
            "Validation failed after seed retries: "
            + ", ".join(last_result.failing_rule_ids())
        ),
    )
