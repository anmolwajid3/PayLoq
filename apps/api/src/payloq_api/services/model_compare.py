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
from payloq_benchmark.pack_summary import build_pack_summary
from payloq_benchmark.scorecard import fi_band_label
from payloq_llm.adapters import LlmAdapter, get_adapter, list_ollama_models
from payloq_llm.defaults import (
    DEFAULT_COMPARE_MODELS,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
)
from payloq_schemas.models import ScenarioPack

INTERPRET_QUESTION_FI = (
    "Miksi kassa muuttuu ennusteessa? Käytä vain annettuja lukuja; älä keksi syitä."
)
INTERPRET_QUESTION_EN = (
    "Why does cash change in the projection? Use only the given figures; do not invent causes."
)


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
    base = list(requested) if requested else list(DEFAULT_COMPARE_MODELS)
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

    row: dict[str, Any] = {
        "model": model,
        "parameter_score": param_grade.score,
        "reading_score": round(reading, 4),
        "mom_score": round(mom, 4),
        "interpretation_score": interp_grade.score,
        "fi_quality_score": fi_grade.score,
        "fi_band": fi_band_label(fi_grade.score),
        "latency_ms": round(latency_ms, 1),
        "interpretation_answer": interpretation,
        "predicted_parameters": predicted,
        "probe_answers": answers,
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
                )
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"model": tag, "reason": str(exc)})

    recommended = None
    if rows:
        recommended = max(rows, key=lambda r: float(r.get("composite_score") or 0.0))["model"]

    payload: dict[str, Any] = {
        "version": 1,
        "principle": "code calculates; models extract/interpret only",
        "pack_model": pack_model or DEFAULT_OLLAMA_MODEL,
        "models": rows,
        "skipped": skipped,
        "recommended_model": recommended,
        "shortlist_default": list(DEFAULT_COMPARE_MODELS),
        "fi_band_legend": {
            "high": "≥ 0.75",
            "mid": "0.40–0.75",
            "low": "< 0.40",
            "n/a": "skipped / EN-only prompt",
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
