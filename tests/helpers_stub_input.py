"""Build GeneratorInput from StubLlmAdapter.extract_parameters without input_from_text.

Task A rejects stub on the from-text path; pack-quality tests still need deterministic
params. Call StubLlmAdapter.extract_parameters directly (Task B), then assemble input.
"""

from __future__ import annotations

from typing import Any

from payloq_llm.adapters import StubLlmAdapter
from payloq_llm.parse import validate_model
from payloq_llm.text_sanitize import sanitize_invoice_texts
from payloq_schemas.models import (
    GeneratorInput,
    InvoiceDescriptiveTexts,
    ParametersFromLanguageModel,
    ScenarioDescription,
    ScenarioMeta,
)


def generator_input_via_stub_extract(
    *,
    text: str,
    options: dict[str, Any],
    language: str = "en",
    with_invoice_texts: bool = True,
    adapter: StubLlmAdapter | None = None,
) -> GeneratorInput:
    stub = adapter or StubLlmAdapter()
    raw = stub.extract_parameters(text, text, options)
    params = validate_model(ParametersFromLanguageModel, raw)
    invoice_texts: InvoiceDescriptiveTexts | None = None
    if with_invoice_texts:
        invoice_texts = sanitize_invoice_texts(
            stub.generate_invoice_texts(
                description_fi=text,
                description_en=text,
                industry=str(options.get("industry", "SME")),
                language=str(options.get("language", language)),
            ),
            description_fi=text,
            description_en=text,
        )
    return GeneratorInput(
        meta=ScenarioMeta(
            fictional=True,
            note="test: stub extract (bypasses input_from_text)",
            seed=int(options.get("seed") or 42),
        ),
        scenario_description=ScenarioDescription(fi=text, en=text),
        options=options,  # type: ignore[arg-type]
        parameters_from_language_model=params,
        invoice_texts=invoice_texts,
    )
