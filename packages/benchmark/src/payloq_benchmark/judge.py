"""Optional LLM-as-judge for interpretation quality (synthetic data only)."""

from __future__ import annotations

import json
from typing import Any

from payloq_llm.adapters import LlmAdapter

from payloq_benchmark.graders import GradeDetail, extract_first_number


def judge_prompt(
    *,
    question: str,
    answer: str,
    pack_summary: dict[str, Any],
) -> str:
    return (
        "You are scoring a virtual-accountant answer on synthetic PayLoq figures.\n"
        "Score ONLY these axes from 0.0 to 1.0:\n"
        "- factual: uses numbers present in Figures JSON\n"
        "- understandable: clear short language (FI or EN)\n"
        "- no_invented_causes: does not invent unsupported external causes\n"
        "Return ONLY JSON: "
        '{"factual":0-1,"understandable":0-1,"no_invented_causes":0-1,'
        '"overall":0-1,"notes":"..."}\n\n'
        f"Figures JSON:\n{json.dumps(pack_summary, ensure_ascii=False)}\n\n"
        f"Question:\n{question}\n\n"
        f"Answer to score:\n{answer}\n"
    )


def parse_judge_response(text: str) -> GradeDetail:
    """Best-effort parse of judge JSON; falls back to extracting overall."""
    data: dict[str, Any] = {}
    try:
        from payloq_llm.parse import extract_json_object

        data = extract_json_object(text)
    except Exception:  # noqa: BLE001
        overall = extract_first_number(text)
        return GradeDetail(
            score=max(0.0, min(1.0, overall or 0.0)),
            notes="judge parse fallback",
        )

    def _clip(key: str, default: float = 0.0) -> float:
        try:
            return max(0.0, min(1.0, float(data.get(key, default))))
        except (TypeError, ValueError):
            return default

    per = {
        "factual": _clip("factual"),
        "understandable": _clip("understandable"),
        "no_invented_causes": _clip("no_invented_causes"),
    }
    if "overall" in data:
        overall = _clip("overall")
    else:
        overall = sum(per.values()) / 3.0
    notes = str(data.get("notes") or "llm-judge")
    return GradeDetail(score=round(overall, 4), notes=notes, per_field=per)


def run_llm_judge(
    adapter: LlmAdapter,
    *,
    question: str,
    answer: str,
    pack_summary: dict[str, Any],
) -> GradeDetail:
    """Call an adapter as judge. Prefer adapters that can return free text."""
    prompt = judge_prompt(question=question, answer=answer, pack_summary=pack_summary)
    # Prefer dedicated chat if present; else interpret_figures with empty summary nudge.
    if hasattr(adapter, "chat"):
        raw = adapter.chat(prompt, json_mode=True)  # type: ignore[attr-defined]
    else:
        raw = adapter.interpret_figures(prompt, {"judge_mode": True, **pack_summary})
    return parse_judge_response(raw)
