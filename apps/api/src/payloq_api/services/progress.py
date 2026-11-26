"""Run progress file (artifact_dir/progress.json) for long Generate jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def progress_path(artifact_dir: Path | str) -> Path:
    return Path(artifact_dir) / "progress.json"


def write_progress(
    artifact_dir: Path | str,
    *,
    percent: int,
    stage: str,
    label_en: str,
    label_fi: str | None = None,
    done: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    path = progress_path(artifact_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "label_en": label_en,
        "label_fi": label_fi or label_en,
        "done": bool(done),
        "error": error,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def load_progress(artifact_dir: str | Path | None) -> dict[str, Any] | None:
    if not artifact_dir:
        return None
    path = progress_path(artifact_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
