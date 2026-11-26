# Human spot-check sheet

Fill the `reviewer_*` columns for a sample of interpretation answers.

## Rubric (0–1 each)

| Column | Meaning |
| --- | --- |
| `reviewer_factual_0_1` | Answer uses only figures from the pack / probe summary |
| `reviewer_understandable_0_1` | Clear FI or EN; appropriate for a non-accountant reader |
| `reviewer_no_invented_causes_0_1` | No unsupported external causes (fraud, customers leaving, etc.) |
| `reviewer_fi_quality_0_1` | Finnish quality on FI prompts (EN-only answers score low here; do not fail the whole model) |

Set `reviewed_by` and `reviewed_at` (ISO date) when done.

Code graders and optional LLM judge scores are pre-filled for comparison — human scores are the source of truth for soft quality.
