"""Defense-in-depth VR-13 cleanup for invoice texts inside the generator."""

from __future__ import annotations

from payloq_generator.text_fi import (
    PURCHASE_COUNTERPARTIES_FI,
    PURCHASE_DESCRIPTIONS_FI,
    SALES_COUNTERPARTIES_FI,
    SALES_DESCRIPTIONS_FI,
)
from payloq_schemas.models import InvoiceDescriptiveTexts
from payloq_schemas.text_rules import (
    descriptive_text_has_numbers,
    strip_numbers_from_descriptive_text,
)


def _fix(text: str, fallback: str) -> str:
    cleaned = strip_numbers_from_descriptive_text(text)
    if not cleaned or descriptive_text_has_numbers(cleaned) or len(cleaned) < 3:
        return fallback
    return cleaned


def sanitize_invoice_texts_for_pack(texts: InvoiceDescriptiveTexts) -> InvoiceDescriptiveTexts:
    """Strip digits from LLM/stub invoice texts; replace bad entries with FI stubs."""
    sales_cp_fb = list(SALES_COUNTERPARTIES_FI)
    purch_cp_fb = list(PURCHASE_COUNTERPARTIES_FI)
    sales_desc_fb = list(SALES_DESCRIPTIONS_FI)
    purch_desc_fb = list(PURCHASE_DESCRIPTIONS_FI)

    sales_cp = [
        _fix(t, sales_cp_fb[i % len(sales_cp_fb)])
        for i, t in enumerate(texts.sales_counterparties or sales_cp_fb)
    ] or sales_cp_fb
    purch_cp = [
        _fix(t, purch_cp_fb[i % len(purch_cp_fb)])
        for i, t in enumerate(texts.purchase_counterparties or purch_cp_fb)
    ] or purch_cp_fb
    sales_desc = [
        _fix(t, sales_desc_fb[i % len(sales_desc_fb)])
        for i, t in enumerate(texts.sales_descriptions or sales_desc_fb)
    ] or sales_desc_fb
    purch_desc = [
        _fix(t, purch_desc_fb[i % len(purch_desc_fb)])
        for i, t in enumerate(texts.purchase_descriptions or purch_desc_fb)
    ] or purch_desc_fb

    return texts.model_copy(
        update={
            "sales_counterparties": sales_cp,
            "purchase_counterparties": purch_cp,
            "sales_descriptions": sales_desc,
            "purchase_descriptions": purch_desc,
        }
    )
