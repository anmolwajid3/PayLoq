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

# Failures fixed by the stated inputs and the description. Redrawing generation
# noise cannot change them, so a later noise seed must not be used to pass.
_INPUT_DETERMINED_CODES = frozenset(
    {
        "behaviour_good_profit",
        "behaviour_weak_loss",
        "behaviour_weak_cash",
        "fidelity",
    }
)


def _failure_is_input_determined(result: ValidationResult) -> bool:
    errors = [issue for issue in result.issues if issue.severity == "error"]
    if not errors:
        return False
    return all(issue.code in _INPUT_DETERMINED_CODES for issue in errors)


def _triggering_input_facts(inp: GeneratorInput, result: ValidationResult) -> str:
    """Input facts that selected the failing rule. Assumed noise is not a fact."""
    params = inp.parameters_from_language_model
    sources = dict(params.field_sources or {})
    text = (inp.scenario_description.en or inp.scenario_description.fi or "").strip()
    parts = [
        f"scenario_id={inp.options.scenario_id}",
        f"scenario_shape={getattr(params, 'scenario_shape', None)}",
        f"description={text[:240]!r}",
    ]
    for key in (
        "monthly_revenue_start_eur",
        "monthly_revenue_growth",
        "starting_cash_eur",
        "target_cash_at_end_eur",
        "covenant_min_cash_eur",
    ):
        value = getattr(params, key, None)
        if value is None:
            continue
        parts.append(f"{key}={value} ({sources.get(key, 'unset')})")
    codes = [issue.code for issue in result.issues if issue.severity == "error"]
    if codes:
        parts.append("triggered_by=" + ",".join(codes))
    return "; ".join(parts)


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
    raw_llm_output: str | None = None,
    llm_name: str | None = None,
    clamp: bool = True,
) -> GenerationOutcome:
    """
    Full Task A pipeline.

    VR-30: on failure, do not write final data files (only run_log + optional raw LLM).
    VR-31: do not silently fix validation failures.
    VR-32: up to ``max_seed_attempts`` redraws of generation noise. The run seed
    stays the seed the caller passed. A rule the inputs determine is not
    retried: the outcome is status error, naming the rule and those facts.

    Special case: ``invoices_out_of_balance`` is deliberately broken (TEST_ONLY_BROKEN):
    validation MUST fail VR-05; files are still written and labelled.

    Pilot fix: no keyword NL repair; fidelity is blocking with consistency.
    """
    out_dir = Path(out_dir)
    working = inp.model_copy(deep=True)
    clips: list[dict[str, Any]] = []
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
    # Identity seed is the caller's seed. Noise redraws must not replace it.
    seed_used = seed

    for attempt_i in range(max_seed_attempts):
        noise_seed = seed + attempt_i
        pack = generate_pack(working, seed=seed, noise_seed=noise_seed)
        if deliberate_broken:
            pack = break_receivables_mismatch(pack)
        answer_key = build_answer_key(pack)
        # For deliberate broken, skip VR-11 mismatch noise: still validate data rules
        result = validate_pack(
            pack,
            answer_key=None if deliberate_broken else answer_key,
            check_fidelity=not deliberate_broken,
        )
        input_determined = _failure_is_input_determined(result)
        attempts.append(
            {
                "attempt": attempt_i + 1,
                "seed": seed,
                "noise_seed": noise_seed,
                "ok": result.ok,
                "input_determined": input_determined,
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
            # VR-05 did not fire. That miss can be noise; redraw unless the
            # remaining errors are fixed by the inputs.
            if input_determined:
                break
            continue

        if result.ok:
            write_pack(
                pack,
                out_dir,
                write_xlsx=write_xlsx,
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
        # A rule the inputs determine fails for every noise draw. Do not
        # shop for a later draw that happens to slip past it.
        if input_determined:
            break

    # All attempts failed — VR-30: do not write final data files
    if last_pack is not None:
        write_pack(
            last_pack,
            out_dir,
            write_xlsx=False,
            seed=seed_used,
            raw_llm_output=raw_llm_output,
            llm_name=llm_name,
            validation=last_result.as_dict(),
            seed_attempts=attempts,
            number_of_retries=max(0, len(attempts) - 1),
            param_clips=clips,
            test_only_broken=deliberate_broken,
            write_data_files=False,
        )

    rules = ", ".join(last_result.failing_rule_ids()) or "unknown"
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
            f"status error: {rules}; input facts: "
            f"{_triggering_input_facts(working, last_result)}"
        ),
    )
