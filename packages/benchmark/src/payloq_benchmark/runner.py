"""Model-matrix benchmark runner: params + reading/MoM + interpretation + metrics."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from payloq_generator.engine import generate_pack, load_input
from payloq_llm.adapters import FallbackAdapter, LlmAdapter, OllamaAdapter, get_adapter
from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

from payloq_benchmark.config import BenchmarkConfig, ModelSpec  # noqa: F401 — re-exported
from payloq_benchmark.graders import (
    DEFAULT_PROBES,
    GradeDetail,
    grade_fi_quality,
    grade_interpretation,
    grade_parameters,
    grade_probes,
)
from payloq_benchmark.judge import run_llm_judge
from payloq_benchmark.metrics import (
    CallMetrics,
    HardwareNotes,
    estimate_cost_eur,
)
from payloq_benchmark.pack_summary import build_pack_summary
from payloq_benchmark.scorecard import (
    fi_band_label,
    write_runs_csv,
    write_scorecard_csv,
    write_scorecard_json,
)
from payloq_benchmark.spotcheck import write_spotcheck_csv, write_spotcheck_readme
from payloq_benchmark.store import MetricsStore


@dataclass
class ModelRunMetrics:
    model: str
    scenario_id: str
    adapter: str = "stub"
    status: str = "ok"  # ok | skipped
    latency_ms: float = 0.0
    tokens_in: int | None = None
    tokens_out: int | None = None
    hardware: str = "cpu"
    parameter_score: float | None = None
    reading_score: float | None = None
    mom_score: float | None = None
    interpretation_score: float | None = None
    fi_quality_score: float | None = None
    judge_score: float | None = None
    rough_cost_eur: float | None = None
    notes: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    batch_id: str
    runs: list[ModelRunMetrics]
    summary: dict[str, Any]
    out_dir: Path

    def write(self, path: Path | None = None) -> Path:
        path = Path(path or (self.out_dir / "results.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "batch_id": self.batch_id,
            "runs": [
                {**{k: v for k, v in asdict(r).items() if k != "detail"}, "detail": r.detail}
                for r in self.runs
            ],
            "summary": self.summary,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


def _resolve_adapter(spec: ModelSpec) -> LlmAdapter:
    if spec.adapter == "stub":
        return get_adapter("stub")
    if spec.adapter == "ollama":
        # When skip_unavailable handles missing hosts, still wrap with fallback
        # only if the caller wants stub contamination on hard call failures.
        return get_adapter(
            "ollama",
            fallback_stub=spec.fallback_stub,
            model=spec.model or DEFAULT_OLLAMA_MODEL,
            host=spec.host or DEFAULT_OLLAMA_HOST,
        )
    raise ValueError(f"Unknown adapter '{spec.adapter}' for model id '{spec.id}'")


def _ollama_host_available(spec: ModelSpec) -> bool:
    host = spec.host or DEFAULT_OLLAMA_HOST
    probe = OllamaAdapter(model=spec.model or DEFAULT_OLLAMA_MODEL, host=host)
    return probe.is_available()


def _pop_adapter_metrics(adapter: LlmAdapter) -> CallMetrics | None:
    raw = getattr(adapter, "last_call_metrics", None)
    if raw is None and isinstance(adapter, FallbackAdapter):
        raw = getattr(adapter.primary, "last_call_metrics", None) or getattr(
            adapter.fallback, "last_call_metrics", None
        )
    if raw is None:
        return None
    if isinstance(raw, CallMetrics):
        return raw
    if isinstance(raw, dict):
        return CallMetrics(
            latency_ms=float(raw.get("latency_ms") or 0.0),
            tokens_in=raw.get("tokens_in"),
            tokens_out=raw.get("tokens_out"),
            model=raw.get("model"),
            adapter=raw.get("adapter"),
            error=raw.get("error"),
        )
    return None


def _scenario_input_path(root: Path, sid: str) -> Path:
    p = root / "scenarios" / sid / "input.json"
    if p.exists():
        return p
    alt = Path("scenarios") / sid / "input.json"
    if alt.exists():
        return alt
    raise FileNotFoundError(f"Scenario input not found for '{sid}' (looked in {p})")


def _ask_probe(adapter: LlmAdapter, probe_id: str, question: str, summary: dict[str, Any]) -> str:
    if hasattr(adapter, "answer_numeric_probe"):
        return adapter.answer_numeric_probe(probe_id, question, summary)  # type: ignore[attr-defined]
    return adapter.interpret_figures(question, summary)


def _run_one(
    *,
    spec: ModelSpec,
    adapter: LlmAdapter,
    sid: str,
    inp,
    pack_summary: dict[str, Any],
    parameter_key: dict[str, Any],
    config: BenchmarkConfig,
    hardware: HardwareNotes,
    judge_adapter: LlmAdapter | None,
) -> ModelRunMetrics:
    call_metrics = CallMetrics(adapter=spec.adapter, model=spec.model)
    notes_parts: list[str] = []
    detail: dict[str, Any] = {}

    # --- (a) parameter extraction vs answer key ---
    t0 = time.perf_counter()
    try:
        predicted = adapter.extract_parameters(
            inp.scenario_description.fi,
            inp.scenario_description.en,
            inp.options.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        predicted = {}
        notes_parts.append(f"param extract failed: {exc}")
    call_metrics = call_metrics.merge(
        CallMetrics(latency_ms=(time.perf_counter() - t0) * 1000)
    )
    call_metrics = call_metrics.merge(_pop_adapter_metrics(adapter))
    if isinstance(adapter, FallbackAdapter) and adapter.used_fallback:
        notes_parts.append(adapter.last_fallback_reason or "fell back to stub")

    param_grade = grade_parameters(predicted, parameter_key)
    detail["parameter"] = param_grade.as_dict()
    detail["predicted_parameters"] = predicted

    # --- (b) numeric reading / MoM probes on code-owned figures ---
    answers: dict[str, str] = {}
    lang = inp.options.language
    for probe in DEFAULT_PROBES:
        q = probe.question_fi if lang == "fi" else probe.question_en
        t1 = time.perf_counter()
        try:
            answers[probe.id] = _ask_probe(adapter, probe.id, q, pack_summary)
        except Exception as exc:  # noqa: BLE001
            answers[probe.id] = ""
            notes_parts.append(f"probe {probe.id} failed: {exc}")
        call_metrics = call_metrics.merge(
            CallMetrics(latency_ms=(time.perf_counter() - t1) * 1000)
        )
        call_metrics = call_metrics.merge(_pop_adapter_metrics(adapter))

    probe_grade = grade_probes(answers, pack_summary)
    detail["probes"] = probe_grade.as_dict()
    detail["probe_answers"] = answers
    reading_score = float(probe_grade.per_field.get("_reading", probe_grade.score))
    mom_score = float(probe_grade.per_field.get("_mom", probe_grade.score))

    # --- (c) interpretation rubric + separate FI band ---
    question = (
        config.interpretation_question_fi
        if lang == "fi"
        else config.interpretation_question_en
    )
    t2 = time.perf_counter()
    try:
        interpretation = adapter.interpret_figures(question, pack_summary)
    except Exception as exc:  # noqa: BLE001
        interpretation = ""
        notes_parts.append(f"interpret failed: {exc}")
    call_metrics = call_metrics.merge(
        CallMetrics(latency_ms=(time.perf_counter() - t2) * 1000)
    )
    call_metrics = call_metrics.merge(_pop_adapter_metrics(adapter))

    interp_grade = grade_interpretation(interpretation, pack_summary, language=lang)
    fi_grade = grade_fi_quality(interpretation, expected_language=lang)
    detail["interpretation"] = interp_grade.as_dict()
    detail["fi_quality"] = fi_grade.as_dict()
    detail["interpretation_answer"] = interpretation
    detail["interpretation_question"] = question

    judge_score = None
    if config.judge.enabled and judge_adapter is not None and interpretation:
        t3 = time.perf_counter()
        try:
            jg = run_llm_judge(
                judge_adapter,
                question=question,
                answer=interpretation,
                pack_summary=pack_summary,
            )
            judge_score = jg.score
            detail["judge"] = jg.as_dict()
        except Exception as exc:  # noqa: BLE001
            notes_parts.append(f"judge failed: {exc}")
            detail["judge"] = GradeDetail(score=0.0, notes=str(exc)).as_dict()
        call_metrics = call_metrics.merge(
            CallMetrics(latency_ms=(time.perf_counter() - t3) * 1000)
        )

    cost = estimate_cost_eur(
        adapter=spec.adapter,
        tokens_in=call_metrics.tokens_in,
        tokens_out=call_metrics.tokens_out,
        latency_ms=call_metrics.latency_ms,
        cost_eur_per_1k_tokens=config.cost_eur_per_1k_tokens,
    )

    return ModelRunMetrics(
        model=spec.id,
        scenario_id=sid,
        adapter=spec.adapter,
        status="ok",
        latency_ms=round(call_metrics.latency_ms, 3),
        tokens_in=call_metrics.tokens_in,
        tokens_out=call_metrics.tokens_out,
        hardware=hardware.short(),
        parameter_score=param_grade.score,
        reading_score=round(reading_score, 4),
        mom_score=round(mom_score, 4),
        interpretation_score=interp_grade.score,
        fi_quality_score=fi_grade.score,
        judge_score=judge_score,
        rough_cost_eur=cost,
        notes="; ".join(notes_parts) if notes_parts else config.hardware_note,
        detail=detail,
    )


def run_benchmark(
    config: BenchmarkConfig,
    *,
    scenarios_root: Path | None = None,
    batch_id: str | None = None,
) -> BenchmarkResult:
    """
    Full model-matrix run (Phase 3 + PL-7 scorecard).

    For each model × scenario:
      1. Extract parameters from NL description → grade vs key
      2. Generate pack from *key* params (code-owned figures)
      3. Numeric reading / MoM probes
      4. Interpretation rubric + separate FI quality band (+ optional LLM judge)
      5. Persist JSON + CSV + SQLite under config.out_dir

    Ollama cells: when ``skip_unavailable`` and the host is down, those models
    are skipped (stub still always runs). Live Ollama integration tests skip
    the same way when no daemon is present.
    """
    root = Path(scenarios_root or config.scenarios_root or Path.cwd())
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    batch_id = batch_id or uuid.uuid4().hex[:12]
    hardware = HardwareNotes(note=config.hardware_note)
    (out_dir / "hardware.json").write_text(
        json.dumps(hardware.as_dict(), indent=2) + "\n", encoding="utf-8"
    )

    judge_adapter: LlmAdapter | None = None
    if config.judge.enabled:
        judge_adapter = get_adapter(
            config.judge.adapter,
            fallback_stub=True,
            model=config.judge.model or DEFAULT_OLLAMA_MODEL,
            host=config.judge.host or DEFAULT_OLLAMA_HOST,
        )

    runs: list[ModelRunMetrics] = []
    spot_rows: list[dict[str, Any]] = []
    skipped_models: list[dict[str, Any]] = []
    availability_cache: dict[str, bool] = {}

    for spec in config.models:
        if spec.adapter == "ollama" and config.skip_unavailable:
            cache_key = spec.host or DEFAULT_OLLAMA_HOST
            if cache_key not in availability_cache:
                availability_cache[cache_key] = _ollama_host_available(spec)
            if not availability_cache[cache_key]:
                skipped_models.append(
                    {
                        "model": spec.id,
                        "adapter": spec.adapter,
                        "reason": f"Ollama not reachable at {cache_key}",
                    }
                )
                continue

        adapter = _resolve_adapter(spec)
        for sid in config.scenario_ids:
            path = _scenario_input_path(root, sid)
            inp = load_input(path)
            if inp.options.scenario_id is None:
                inp.options.scenario_id = sid
            key = inp.parameters_from_language_model.model_dump()
            # Figures from key params — code calculates; models only read/interpret.
            pack = generate_pack(inp, seed=config.seed)
            summary = build_pack_summary(pack)
            (out_dir / f"pack_summary_{sid}.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            row = _run_one(
                spec=spec,
                adapter=adapter,
                sid=sid,
                inp=inp,
                pack_summary=summary,
                parameter_key=key,
                config=config,
                hardware=hardware,
                judge_adapter=judge_adapter,
            )
            runs.append(row)
            spot_rows.append(
                {
                    "model": row.model,
                    "scenario_id": sid,
                    "question": row.detail.get("interpretation_question", ""),
                    "model_answer": row.detail.get("interpretation_answer", ""),
                    "interpretation_score": row.interpretation_score,
                    "fi_quality_score": row.fi_quality_score,
                    "judge_score": row.judge_score,
                }
            )

    # Persist
    store = MetricsStore(out_dir / "metrics.sqlite")
    for r in runs:
        store.insert_run(
            batch_id=batch_id,
            model=r.model,
            adapter=r.adapter,
            scenario_id=r.scenario_id,
            latency_ms=r.latency_ms,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            hardware=r.hardware,
            parameter_score=r.parameter_score,
            reading_score=r.reading_score,
            mom_score=r.mom_score,
            interpretation_score=r.interpretation_score,
            fi_quality_score=r.fi_quality_score,
            judge_score=r.judge_score,
            rough_cost_eur=r.rough_cost_eur,
            notes=r.notes,
            detail=r.detail,
        )

    by_model = store.summary_by_model(batch_id)
    summary = {
        "batch_id": batch_id,
        "n_runs": len(runs),
        "models": [m.id for m in config.models],
        "models_run": sorted({r.model for r in runs}),
        "scenarios": config.scenario_ids,
        "status": "phase7",
        "skip_unavailable": config.skip_unavailable,
        "skipped_models": skipped_models,
        "hardware": hardware.as_dict(),
        "by_model": by_model,
        "sqlite": str(out_dir / "metrics.sqlite"),
        "scorecard_json": str(out_dir / "scorecard.json"),
        "scorecard_csv": str(out_dir / "scorecard.csv"),
        "runs_csv": str(out_dir / "runs.csv"),
        "fi_band_notes": (
            "FI quality is a separate band; EN-only answers on FI prompts get a low "
            "fi_quality_score without failing the main interpretation rubric."
        ),
    }
    result = BenchmarkResult(batch_id=batch_id, runs=runs, summary=summary, out_dir=out_dir)
    result.write(out_dir / "results.json")

    write_scorecard_json(
        out_dir / "scorecard.json",
        batch_id=batch_id,
        by_model=by_model,
        skipped_models=skipped_models,
        notes={"fi_band": summary["fi_band_notes"]},
    )
    write_scorecard_csv(out_dir / "scorecard.csv", batch_id=batch_id, by_model=by_model)
    write_runs_csv(
        out_dir / "runs.csv",
        batch_id=batch_id,
        runs=[
            {
                **{k: v for k, v in asdict(r).items() if k != "detail"},
                "fi_band": fi_band_label(r.fi_quality_score),
            }
            for r in runs
        ],
    )

    if config.write_spotcheck:
        write_spotcheck_csv(out_dir / "spotcheck.csv", spot_rows, batch_id=batch_id)
        write_spotcheck_readme(out_dir / "spotcheck_README.md")

    return result


# Back-compat alias used by Phase 1–2 tests / CLI
def run_benchmark_stub(
    config: Any,
    *,
    parameter_keys: dict[str, dict[str, Any]] | None = None,
    adapters: dict[str, LlmAdapter] | None = None,
) -> BenchmarkResult:
    """
    Compatibility wrapper.

    Accepts legacy BenchmarkConfig(models: list[str]) or new ModelSpec config.
    `parameter_keys` / `adapters` are ignored when scenarios are loaded from disk
    (preferred); adapters map is used only if provided for unit tests.
    """
    _ = parameter_keys  # scenarios on disk are the answer keys
    # Normalize legacy config
    if hasattr(config, "models") and config.models and isinstance(config.models[0], str):
        from payloq_benchmark.config import parse_model_token

        cfg = BenchmarkConfig(
            scenario_ids=list(config.scenario_ids),
            models=[parse_model_token(m) for m in config.models],
            out_dir=Path(config.out_dir),
            write_spotcheck=False,
        )
    elif isinstance(config, BenchmarkConfig):
        cfg = config
    else:
        cfg = BenchmarkConfig(
            scenario_ids=list(getattr(config, "scenario_ids", ["good"])),
            out_dir=Path(getattr(config, "out_dir", "runs/benchmark")),
            write_spotcheck=False,
        )

    # If custom adapters injected (unit tests), run a minimal path
    if adapters:
        return _run_with_injected_adapters(cfg, adapters)

    # Find repo root for scenarios
    root = Path.cwd()
    for candidate in [root, *Path(__file__).resolve().parents]:
        if (candidate / "scenarios").is_dir() and (candidate / "pyproject.toml").exists():
            root = candidate
            break
    return run_benchmark(cfg, scenarios_root=root)


def _run_with_injected_adapters(
    cfg: BenchmarkConfig,
    adapters: dict[str, LlmAdapter],
) -> BenchmarkResult:
    """Test helper: skip disk scenarios when keys missing; use stub summaries."""
    batch_id = uuid.uuid4().hex[:12]
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hardware = HardwareNotes(note=cfg.hardware_note)
    runs: list[ModelRunMetrics] = []

    root = Path.cwd()
    for candidate in [root, *Path(__file__).resolve().parents]:
        if (candidate / "scenarios").is_dir():
            root = candidate
            break

    for spec in cfg.models:
        adapter = adapters.get(spec.id) or adapters.get(spec.adapter) or get_adapter("stub")
        for sid in cfg.scenario_ids:
            try:
                path = _scenario_input_path(root, sid)
                inp = load_input(path)
                key = inp.parameters_from_language_model.model_dump()
                pack = generate_pack(inp, seed=cfg.seed)
                summary = build_pack_summary(pack)
            except FileNotFoundError:
                # Minimal synthetic summary for isolated unit tests
                from payloq_schemas.models import (
                    GeneratorInput,
                    ParametersFromLanguageModel,
                    ScenarioDescription,
                    ScenarioMeta,
                    Options,
                )

                key = {
                    "monthly_revenue_start_eur": 200000,
                    "monthly_revenue_growth": 0.008,
                    "cost_shares_of_revenue": {
                        "materials": 0.36,
                        "services": 0.08,
                        "personnel": 0.33,
                        "other": 0.14,
                    },
                    "days_sales_outstanding": 38,
                    "days_payables_outstanding": 31,
                    "target_cash_at_end_eur": 330000,
                    "special_investment_eur": 0,
                    "partly_fixed_costs": False,
                }
                inp = GeneratorInput(
                    meta=ScenarioMeta(scenario=sid),
                    scenario_description=ScenarioDescription(
                        fi=f"skenaario {sid}", en=f"scenario {sid}"
                    ),
                    options=Options(
                        industry="test",
                        company_size="small",
                        months=12,
                        language="fi",
                        scenario_id=sid,
                    ),
                    parameters_from_language_model=ParametersFromLanguageModel.model_validate(
                        key
                    ),
                )
                pack = generate_pack(inp, seed=cfg.seed)
                summary = build_pack_summary(pack)

            row = _run_one(
                spec=spec,
                adapter=adapter,
                sid=sid,
                inp=inp,
                pack_summary=summary,
                parameter_key=key,
                config=cfg,
                hardware=hardware,
                judge_adapter=None,
            )
            runs.append(row)

    summary = {
        "batch_id": batch_id,
        "n_runs": len(runs),
        "models": [m.id for m in cfg.models],
        "scenarios": cfg.scenario_ids,
        "status": "phase3-injected",
    }
    result = BenchmarkResult(batch_id=batch_id, runs=runs, summary=summary, out_dir=out_dir)
    result.write(out_dir / "results.json")
    return result
