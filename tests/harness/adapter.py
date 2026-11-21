"""Fixture adapter: the only extraction source in the default tier.

Returns the recorded extraction JSON for the bound scenario. Invoice wording
comes from tests/harness/fixtures/invoice_texts.json, not from a model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from payloq_llm.adapters import LlmAdapter
from payloq_schemas.models import InvoiceDescriptiveTexts

_TEXTS_PATH = Path(__file__).resolve().parent / "fixtures" / "invoice_texts.json"
_TEXTS: dict[str, Any] | None = None


def _texts() -> dict[str, Any]:
    global _TEXTS
    if _TEXTS is None:
        _TEXTS = json.loads(_TEXTS_PATH.read_text(encoding="utf-8"))
    return _TEXTS


class FixtureAdapter(LlmAdapter):
    """Recorded extraction. Does not parse the description and does not call Ollama."""

    name = "fixture"
    model = "fixture-recording"

    def __init__(self) -> None:
        self._extraction: dict[str, Any] | None = None
        self.last_raw_output: str | None = None
        self.last_call_metrics: dict[str, Any] | None = None

    def bind(self, extraction: dict[str, Any]) -> None:
        self._extraction = json.loads(json.dumps(extraction))

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        if self._extraction is None:
            raise RuntimeError("fixture adapter has no recorded extraction bound")
        # Same post-parse path OllamaAdapter.extract_parameters uses.
        from payloq_generator.consistency import require_consistent
        from payloq_llm.extract_pipeline import finalize_extracted_parameters

        raw = json.dumps(self._extraction, ensure_ascii=False, sort_keys=True)
        self.last_raw_output = raw
        combined = f"{description_fi} {description_en}"
        data = json.loads(raw)
        out, _changes, stated_check = finalize_extracted_parameters(
            data,
            combined,
            industry=str(options.get("industry") or ""),
            company_size=str(options.get("company_size") or ""),
            seed=int(options.get("seed") or 42),
            months=int(options.get("months") or 12),
            require_starting_cash=False,
            llm_model_name=self.model,
        )
        if not stated_check.ok:
            raise RuntimeError(stated_check.error_text())
        require_consistent(out)
        self.last_call_metrics = {
            "adapter": self.name,
            "model": self.model,
            "source": "recording",
        }
        return out

    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        _ = (description_fi, description_en, industry)
        blob = _texts()
        lang = language if language in blob else "en"
        row = blob[lang]
        return InvoiceDescriptiveTexts(
            sales_counterparties=list(row["sales_counterparties"]),
            purchase_counterparties=list(row["purchase_counterparties"]),
            sales_descriptions=list(row["sales_descriptions"]),
            purchase_descriptions=list(row["purchase_descriptions"]),
            language=lang,  # type: ignore[arg-type]
            notes="recorded fixture invoice texts",
        )

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        _ = (question, pack_summary)
        return "fixture recording"
