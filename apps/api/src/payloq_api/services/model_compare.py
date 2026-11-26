"""PL-52: per-input multi-model compare on NL generate (same pack figures)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from payloq_benchmark.graders import (
    DEFAULT_PROBES,
    grade_fi_quality,
    grade_interpretation,
    grade_parameters_binary,
    grade_probes,
)
from payloq_benchmark.judge import run_llm_judge
from payloq_benchmark.pack_summary import build_pack_summary
from payloq_benchmark.scorecard import fi_band_label
from payloq_llm.adapters import LlmAdapter, get_adapter, list_ollama_models
from payloq_llm.defaults import (
    DEFAULT_COMPARE_FINANCE_MODEL,
    DEFAULT_COMPARE_MODELS,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_MODELS,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    JUDGE_FALLBACK_MODELS,
)
from payloq_schemas.models import ScenarioPack

INTERPRET_QUESTION_FI = (
    "Miksi kassa muuttuu ennusteessa? Käytä vain annettuja lukuja; älä keksi syitä."
)
INTERPRET_QUESTION_EN = (
    "Why does cash change in the projection? Use only the given figures; do not invent causes."
)


def resolve_judge_models(
    *,
    pulled: list[str] | set[str],
    pack_model: str | None,
    preferred: list[str] | None = None,
) -> list[str]:
    """All pulled judge tags distinct from the pack model (multi-judge panel).

    Order: preferred shortlist first, then any other pulled non-pack tag.
    Never includes the pack model (no self-judge).
    """
    available = {str(t).strip() for t in pulled if str(t).strip()}
    pack = (pack_model or "").strip() or None
    shortlist = list(preferred) if preferred is not None else list(DEFAULT_JUDGE_MODELS)
    ordered: list[str] = []
    seen: set[str] = set()

    def _ok(tag: str) -> bool:
        return bool(tag) and tag in available and tag != pack

    for tag in shortlist:
        tag = (tag or "").strip()
        if _ok(tag) and tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    # Keep resolve_judge_model's old "any pulled" escape hatch for sparse installs.
    for tag in JUDGE_FALLBACK_MODELS:
        tag = (tag or "").strip()
        if _ok(tag) and tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return ordered


def resolve_judge_model(
    *,
    pulled: list[str] | set[str],
    pack_model: str | None,
    preferred: str = DEFAULT_JUDGE_MODEL,
) -> str | None:
    """Pick the primary judge tag (first of the multi-judge panel)."""
    panel = resolve_judge_models(
        pulled=pulled,
        pack_model=pack_model,
        preferred=[preferred, *DEFAULT_JUDGE_MODELS],
    )
    return panel[0] if panel else None


def resolve_compare_models(
    *,
    requested: list[str] | None,
    primary: str | None,
    host: str | None = None,
    available_only: bool = True,
) -> list[str]:
    """
    Build ordered unique compare list.

    ``None`` / empty requested → default shortlist (+ primary).
    When ``available_only``, drop tags not present in Ollama ``/api/tags``.
    """
    if requested:
        base = list(requested)
    else:
        base = list(DEFAULT_COMPARE_MODELS)
        # Size / specialty ladder: append finance-tuned when caller left defaults.
        base.append(DEFAULT_COMPARE_FINANCE_MODEL)
    if primary:
        base = [primary, *[m for m in base if m != primary]]
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in base:
        tag = (tag or "").strip()
        if not tag or tag in seen or tag == "stub":
            continue
        seen.add(tag)
        ordered.append(tag)

    if not available_only:
        return ordered

    payload = list_ollama_models(host or DEFAULT_OLLAMA_HOST)
    if not payload.get("available"):
        # Host down: still return primary-only so generate can proceed without compare noise.
        return [primary] if primary else []

    names = {str(m.get("name") or "") for m in payload.get("models") or []}
    # Also accept bare name matching name:latest
    def _present(tag: str) -> bool:
        if tag in names:
            return True
        if ":" not in tag and f"{tag}:latest" in names:
            return True
        if tag.endswith(":latest") and tag.rsplit(":", 1)[0] in names:
            return True
        return False

    return [t for t in ordered if _present(t)]


def _ask_probe(adapter: LlmAdapter, probe_id: str, question: str, summary: dict[str, Any]) -> str:
    if hasattr(adapter, "answer_numeric_probe"):
        return adapter.answer_numeric_probe(probe_id, question, summary)  # type: ignore[attr-defined]
    return adapter.interpret_figures(question, summary)


def _composite(row: dict[str, Any]) -> float:
    parts = [
        float(row.get("parameter_score") or 0.0) * 0.25,
        float(row.get("reading_score") or 0.0) * 0.25,
        float(row.get("mom_score") or 0.0) * 0.15,
        float(row.get("interpretation_score") or 0.0) * 0.25,
        float(row.get("fi_quality_score") or 0.0) * 0.10,
    ]
    return round(sum(parts), 4)


def score_model_on_pack(
    *,
    adapter: LlmAdapter,
    model: str,
    description_fi: str,
    description_en: str,
    options: dict[str, Any],
    parameter_key: dict[str, Any],
    pack_summary: dict[str, Any],
    language: str = "fi",
    judge_adapter: LlmAdapter | None = None,
    judge_model: str | None = None,
    judge_panel: list[tuple[str, LlmAdapter]] | None = None,
) -> dict[str, Any]:
    """Extract + read + interpret one model against the same code-owned pack."""
    notes: list[str] = []
    t0 = time.perf_counter()
    predicted: dict[str, Any] = {}
    try:
        predicted = adapter.extract_parameters(description_fi, description_en, options)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"param extract failed: {exc}")
        predicted = {}

    param_grade = grade_parameters_binary(predicted, parameter_key)

    answers: dict[str, str] = {}
    for probe in DEFAULT_PROBES:
        q = probe.question_fi if language == "fi" else probe.question_en
        try:
            answers[probe.id] = _ask_probe(adapter, probe.id, q, pack_summary)
        except Exception as exc:  # noqa: BLE001
            answers[probe.id] = ""
            notes.append(f"probe {probe.id} failed: {exc}")

    probe_grade = grade_probes(answers, pack_summary)
    reading = float(probe_grade.per_field.get("_reading", probe_grade.score))
    mom = float(probe_grade.per_field.get("_mom", probe_grade.score))

    question = INTERPRET_QUESTION_FI if language == "fi" else INTERPRET_QUESTION_EN
    interpretation = ""
    try:
        interpretation = adapter.interpret_figures(question, pack_summary)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"interpret failed: {exc}")

    interp_grade = grade_interpretation(interpretation, pack_summary, language=language)
    fi_grade = grade_fi_quality(interpretation, expected_language=language)
    latency_ms = (time.perf_counter() - t0) * 1000

    wrong_params = [k for k, v in (param_grade.per_field or {}).items() if float(v) < 0.5]
    score_why: list[str] = []
    if param_grade.notes:
        score_why.append(f"params: {param_grade.notes}")
    elif wrong_params:
        score_why.append("params wrong: " + ", ".join(wrong_params[:8]))
    if interp_grade.notes:
        score_why.append(f"interp (code): {interp_grade.notes}")
    if fi_grade.notes:
        score_why.append(f"FI: {fi_grade.notes}")

    panel_specs: list[tuple[str, LlmAdapter]] = list(judge_panel or [])
    if not panel_specs and judge_adapter is not None and judge_model:
        panel_specs = [(judge_model, judge_adapter)]

    panel_rows: list[dict[str, Any]] = []
    for j_tag, j_adapter in panel_specs:
        if not interpretation.strip():
            break
        try:
            jg = run_llm_judge(
                j_adapter,
                question=question,
                answer=interpretation,
                pack_summary=pack_summary,
            )
            j_score = jg.score
            j_notes = jg.notes or ""
            j_axes = {k: float(v) for k, v in (jg.per_field or {}).items()}
            # Code grounding beats a generous LLM judge on invented amounts.
            if "ungrounded" in (interp_grade.notes or "") and j_score is not None:
                j_score = min(float(j_score), 0.45)
                for axis in ("factual", "no_invented_causes"):
                    if axis in j_axes:
                        j_axes[axis] = min(float(j_axes[axis]), 0.4)
                j_notes = (
                    (j_notes + "; ").lstrip("; ")
                    + "capped: code found ungrounded amounts"
                ).strip("; ")
            panel_rows.append(
                {
                    "judge_model": j_tag,
                    "score": j_score,
                    "axes": j_axes,
                    "notes": j_notes,
                }
            )
            if j_notes:
                score_why.append(f"judge[{j_tag}]: {j_notes}")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"judge {j_tag} failed: {exc}")
            panel_rows.append(
                {
                    "judge_model": j_tag,
                    "score": None,
                    "axes": {},
                    "notes": f"failed: {exc}",
                }
            )

    scored = [float(p["score"]) for p in panel_rows if p.get("score") is not None]
    judge_score: float | None = round(sum(scored) / len(scored), 4) if scored else None
    primary = panel_rows[0] if panel_rows else None
    judge_model_out = (
        primary["judge_model"] if primary else judge_model
    )
    judge_notes = primary["notes"] if primary else ""
    judge_axes = dict(primary["axes"]) if primary else {}

    row: dict[str, Any] = {
        "model": model,
        "parameter_score": param_grade.score,
        "reading_score": round(reading, 4),
        "mom_score": round(mom, 4),
        "interpretation_score": interp_grade.score,
        "interpretation_axes": {
            k: float(v) for k, v in (interp_grade.per_field or {}).items()
        },
        "fi_quality_score": fi_grade.score,
        "fi_band": fi_band_label(fi_grade.score),
        "latency_ms": round(latency_ms, 1),
        "interpretation_answer": interpretation,
        "predicted_parameters": predicted,
        "probe_answers": answers,
        "parameter_field_scores": dict(param_grade.per_field or {}),
        "judge_model": judge_model_out,
        "judge_score": judge_score,
        "judge_axes": judge_axes,
        "judge_notes": judge_notes,
        "judge_panel": panel_rows,
        "score_rationale": "; ".join(score_why) if score_why else "",
        "notes": "; ".join(notes) if notes else "",
    }
    row["composite_score"] = _composite(row)
    return row


def run_model_comparison(
    *,
    pack: ScenarioPack,
    text: str,
    language: str,
    options: dict[str, Any],
    models: list[str],
    pack_model: str | None = None,
    host: str | None = None,
    timeout_s: float | None = None,
    out_dir: Path | None = None,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """
    Score each model on the same code-built pack.

    Parameter key = pack.input.parameters_from_language_model (stated + assumed).
    Figures = build_pack_summary(pack). Models only extract/interpret.
    """
    summary = build_pack_summary(pack)
    key = pack.input.parameters_from_language_model.model_dump()
    desc_fi = pack.input.scenario_description.fi or text
    desc_en = pack.input.scenario_description.en or text
    if language == "fi":
        desc_fi = text or desc_fi
    else:
        desc_en = text or desc_en

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    n = max(len(models), 1)

    judge_panel_adapters: list[tuple[str, LlmAdapter]] = []
    judge_models_used: list[str] = []
    judge_model_used: str | None = None
    judge_skip: str | None = None
    try:
        tags_payload = list_ollama_models(host or DEFAULT_OLLAMA_HOST)
        pulled = [
            str(m.get("name") or "").strip()
            for m in (tags_payload.get("models") or [])
            if str(m.get("name") or "").strip()
        ]
        judge_models_used = resolve_judge_models(
            pulled=pulled,
            pack_model=pack_model or DEFAULT_OLLAMA_MODEL,
            preferred=list(DEFAULT_JUDGE_MODELS),
        )
        judge_model_used = judge_models_used[0] if judge_models_used else None
        for j_tag in judge_models_used:
            judge_panel_adapters.append(
                (
                    j_tag,
                    get_adapter(
                        "ollama",
                        fallback_stub=False,
                        model=j_tag,
                        host=host or DEFAULT_OLLAMA_HOST,
                        timeout_s=timeout_s,
                    ),
                )
            )
        if not judge_models_used:
            if not tags_payload.get("available"):
                judge_skip = "judge unavailable: Ollama host down"
            else:
                judge_skip = (
                    f"no separate judge tag pulled (pack={pack_model or DEFAULT_OLLAMA_MODEL}; "
                    f"shortlist={', '.join(DEFAULT_JUDGE_MODELS)})"
                )
    except Exception as exc:  # noqa: BLE001
        judge_skip = f"judge unavailable: {exc}"
        judge_panel_adapters = []
        judge_models_used = []
        judge_model_used = None

    for i, tag in enumerate(models):
        if on_progress is not None:
            # Map compare phase into roughly 55–95%.
            pct = 55 + int(40 * i / n)
            on_progress(
                pct,
                "compare",
                f"Comparing model {i + 1}/{len(models)}: {tag}",
                f"Verrataan mallia {i + 1}/{len(models)}: {tag}",
            )
        try:
            adapter = get_adapter(
                "ollama",
                fallback_stub=False,
                model=tag,
                host=host or DEFAULT_OLLAMA_HOST,
                timeout_s=timeout_s,
            )
            rows.append(
                score_model_on_pack(
                    adapter=adapter,
                    model=tag,
                    description_fi=desc_fi,
                    description_en=desc_en,
                    options=options,
                    parameter_key=key,
                    pack_summary=summary,
                    language=language,
                    judge_panel=judge_panel_adapters,
                    judge_model=judge_model_used,
                )
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"model": tag, "reason": str(exc)})

    recommended = None
    if rows:
        recommended = max(rows, key=lambda r: float(r.get("composite_score") or 0.0))["model"]

    # Per-judge mean across subjects — which judge is harsher / more generous.
    judge_dashboard: list[dict[str, Any]] = []
    for j_tag in judge_models_used:
        cell_scores: list[float] = []
        for row in rows:
            for cell in row.get("judge_panel") or []:
                if cell.get("judge_model") == j_tag and cell.get("score") is not None:
                    cell_scores.append(float(cell["score"]))
        judge_dashboard.append(
            {
                "judge_model": j_tag,
                "mean_score": (
                    round(sum(cell_scores) / len(cell_scores), 4) if cell_scores else None
                ),
                "n_scored": len(cell_scores),
                "is_primary": j_tag == judge_model_used,
            }
        )

    payload: dict[str, Any] = {
        "version": 3,
        "principle": "code calculates; models extract/interpret only",
        "pack_model": pack_model or DEFAULT_OLLAMA_MODEL,
        "judge_model": judge_model_used,
        "judge_models": judge_models_used,
        "judge_dashboard": judge_dashboard,
        "judge_role": (
            "Separate models (never the pack model) each score every interpretation for "
            "factual / understandable / no_invented_causes against the same code figures. "
            "judge_score on a row is the mean across the judge panel. Never stubbed; "
            "skipped when only the pack tag is pulled."
        ),
        "judge_skipped": judge_skip,
        "models": rows,
        "skipped": skipped,
        "recommended_model": recommended,
        "shortlist_default": list(DEFAULT_COMPARE_MODELS),
        "judge_shortlist_default": list(DEFAULT_JUDGE_MODELS),
        "fi_band_legend": {
            "high": "≥ 0.75",
            "mid": "0.40–0.75",
            "low": "< 0.40",
            "n/a": "skipped / EN-only prompt",
        },
        "score_weights": {
            "parameter": 0.25,
            "reading": 0.25,
            "mom": 0.15,
            "interpretation": 0.25,
            "fi_quality": 0.10,
        },
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "comparison.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        answers_root = out_dir / "compare_answers"
        for row in rows:
            safe = str(row["model"]).replace(":", "_").replace("/", "_")
            d = answers_root / safe
            d.mkdir(parents=True, exist_ok=True)
            (d / "interpretation.txt").write_text(
                str(row.get("interpretation_answer") or ""), encoding="utf-8"
            )
            (d / "parameters.json").write_text(
                json.dumps(row.get("predicted_parameters") or {}, indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )

    return payload


def load_comparison(artifact_dir: str | Path | None) -> dict[str, Any] | None:
    if not artifact_dir:
        return None
    path = Path(artifact_dir) / "comparison.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
