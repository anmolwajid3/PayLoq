"""Scorecard export helpers — JSON / CSV under runs/ (SQLite is MetricsStore)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

# Aggregate scorecard columns (by_model).
SCORECARD_CSV_HEADERS = [
    "batch_id",
    "model",
    "n",
    "avg_parameter",
    "avg_reading",
    "avg_mom",
    "avg_interpretation",
    "avg_fi_quality",
    "fi_band",
    "avg_judge",
    "avg_latency_ms",
    "tokens_total",
    "cost_eur",
]

# Flat per-run export.
RUNS_CSV_HEADERS = [
    "batch_id",
    "model",
    "adapter",
    "scenario_id",
    "status",
    "latency_ms",
    "tokens_in",
    "tokens_out",
    "parameter_score",
    "reading_score",
    "mom_score",
    "interpretation_score",
    "fi_quality_score",
    "fi_band",
    "judge_score",
    "rough_cost_eur",
    "notes",
]


def fi_band_label(score: float | None) -> str:
    """
    Finnish quality band for EN-only / FI prompts.

    High ≥ 0.75 · Mid 0.40–0.75 · Low < 0.40 · n/a when not applicable.
    """
    if score is None:
        return "n/a"
    if score >= 0.75:
        return "high"
    if score >= 0.40:
        return "mid"
    return "low"


def write_scorecard_json(
    path: Path,
    *,
    batch_id: str,
    by_model: list[dict[str, Any]],
    skipped_models: list[dict[str, Any]] | None = None,
    notes: dict[str, Any] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    enriched = []
    for row in by_model:
        item = dict(row)
        item["fi_band"] = fi_band_label(item.get("avg_fi_quality"))
        enriched.append(item)
    payload = {
        "batch_id": batch_id,
        "by_model": enriched,
        "skipped_models": skipped_models or [],
        "fi_band_legend": {
            "high": "≥ 0.75 — clear Finnish markers on FI prompts",
            "mid": "0.40–0.75 — partial FI / mixed language",
            "low": "< 0.40 — EN-only or little Finnish on FI prompts",
            "n/a": "no FI-band score (skipped / EN prompt only)",
        },
        "notes": notes or {},
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_scorecard_csv(
    path: Path,
    *,
    batch_id: str,
    by_model: Iterable[dict[str, Any]],
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCORECARD_CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in by_model:
            out = {
                "batch_id": batch_id,
                "model": row.get("model"),
                "n": row.get("n"),
                "avg_parameter": row.get("avg_parameter"),
                "avg_reading": row.get("avg_reading"),
                "avg_mom": row.get("avg_mom"),
                "avg_interpretation": row.get("avg_interpretation"),
                "avg_fi_quality": row.get("avg_fi_quality"),
                "fi_band": fi_band_label(row.get("avg_fi_quality")),
                "avg_judge": row.get("avg_judge"),
                "avg_latency_ms": row.get("avg_latency_ms"),
                "tokens_total": row.get("tokens_total"),
                "cost_eur": row.get("cost_eur"),
            }
            writer.writerow(out)
    return path


def write_runs_csv(
    path: Path,
    *,
    batch_id: str,
    runs: Iterable[dict[str, Any]],
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUNS_CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in runs:
            out = {h: row.get(h) for h in RUNS_CSV_HEADERS}
            out["batch_id"] = batch_id
            if out.get("fi_band") is None:
                out["fi_band"] = fi_band_label(row.get("fi_quality_score"))
            writer.writerow(out)
    return path
