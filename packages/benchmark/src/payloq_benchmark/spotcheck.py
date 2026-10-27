"""Human spot-check sheet template for interpretation samples."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable


SPOTCHECK_HEADERS = [
    "batch_id",
    "model",
    "scenario_id",
    "question",
    "model_answer",
    "code_interpretation_score",
    "judge_score",
    "reviewer_factual_0_1",
    "reviewer_understandable_0_1",
    "reviewer_no_invented_causes_0_1",
    "reviewer_notes",
    "reviewed_by",
    "reviewed_at",
]


def write_spotcheck_csv(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *,
    batch_id: str,
) -> Path:
    """Write a CSV template reviewers can fill in Excel / LibreOffice."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SPOTCHECK_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = {h: "" for h in SPOTCHECK_HEADERS}
            out.update(
                {
                    "batch_id": batch_id,
                    "model": row.get("model", ""),
                    "scenario_id": row.get("scenario_id", ""),
                    "question": row.get("question", ""),
                    "model_answer": row.get("model_answer", ""),
                    "code_interpretation_score": row.get("interpretation_score", ""),
                    "judge_score": row.get("judge_score", ""),
                }
            )
            writer.writerow(out)
    return path


def write_spotcheck_readme(path: Path) -> Path:
    """Short instructions next to the CSV."""
    path = Path(path)
    path.write_text(
        """# Human spot-check sheet

Fill the `reviewer_*` columns for a sample of interpretation answers.

## Rubric (0–1 each)

| Column | Meaning |
| --- | --- |
| `reviewer_factual_0_1` | Answer uses only figures from the pack / probe summary |
| `reviewer_understandable_0_1` | Clear FI or EN; appropriate for a non-accountant reader |
| `reviewer_no_invented_causes_0_1` | No unsupported external causes (fraud, customers leaving, etc.) |

Set `reviewed_by` and `reviewed_at` (ISO date) when done.

Code graders and optional LLM judge scores are pre-filled for comparison — human scores are the source of truth for soft quality.
""",
        encoding="utf-8",
    )
    return path
