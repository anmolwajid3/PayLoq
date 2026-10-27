"""Extract and validate structured JSON from LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from model output (fences / prose OK)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")

    candidates: list[str] = []
    fence = _FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(text)
    obj = _OBJECT_RE.search(text)
    if obj:
        candidates.append(obj.group(0))

    last_err: Exception | None = None
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
        if isinstance(data, dict):
            return data
        last_err = ValueError(f"expected JSON object, got {type(data).__name__}")
    raise ValueError(f"could not parse JSON object from model response: {last_err}")


def validate_model(model_cls: type[T], data: dict[str, Any]) -> T:
    """Validate a dict into a Pydantic model; re-raise with a short message."""
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Pydantic validation failed for {model_cls.__name__}: {exc}") from exc
