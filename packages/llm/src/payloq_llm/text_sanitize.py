"""Sanitize LLM invoice texts so free-text fields pass VR-13 / FR-A-32."""

from __future__ import annotations

from payloq_llm.stub_texts import stub_invoice_texts
from payloq_schemas.models import InvoiceDescriptiveTexts
from payloq_schemas.text_rules import (
    descriptive_text_has_numbers,
    strip_numbers_from_descriptive_text,
)

# Long blobs are usually the raw NL description pasted into a line field.
_MAX_DESC_LEN = 80
_MAX_COUNTERPARTY_LEN = 60


def _looks_like_pasted_description(text: str, *, nl_blobs: tuple[str, ...]) -> bool:
    low = text.lower().strip()
    if len(low) > _MAX_DESC_LEN:
        return True
    for blob in nl_blobs:
        b = (blob or "").lower().strip()
        if not b:
            continue
        if low == b:
            return True
        # Substantial overlap with the company description → refuse paste.
        if len(low) >= 40 and low in b:
            return True
        if len(b) >= 40 and b[:80] in low:
            return True
    return False


def _clean_one(
    text: str,
    *,
    fallback: str,
    nl_blobs: tuple[str, ...],
    is_counterparty: bool,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return fallback
    if _looks_like_pasted_description(raw, nl_blobs=nl_blobs):
        return fallback
    max_len = _MAX_COUNTERPARTY_LEN if is_counterparty else _MAX_DESC_LEN
    if len(raw) > max_len:
        # Prefer stub over truncated garbage that still carries NL numbers.
        if descriptive_text_has_numbers(raw):
            return fallback
        raw = raw[:max_len].rsplit(" ", 1)[0].strip() or fallback
    cleaned = strip_numbers_from_descriptive_text(raw)
    if not cleaned or descriptive_text_has_numbers(cleaned):
        return fallback
    # After stripping, reject near-empty remnants ("room", "-", etc. from "12-room")
    if len(cleaned) < 3:
        return fallback
    return cleaned


def _clean_list(
    items: list[str],
    fallbacks: list[str],
    *,
    nl_blobs: tuple[str, ...],
    is_counterparty: bool,
) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(items or []):
        fb = fallbacks[i % len(fallbacks)]
        out.append(
            _clean_one(
                item,
                fallback=fb,
                nl_blobs=nl_blobs,
                is_counterparty=is_counterparty,
            )
        )
    if not out:
        return list(fallbacks)
    return out


def sanitize_invoice_texts(
    texts: InvoiceDescriptiveTexts,
    *,
    description_fi: str = "",
    description_en: str = "",
) -> InvoiceDescriptiveTexts:
    """
    Ensure counterparties / line descriptions have no digits and are not the
    raw from_text NL description. Falls back to built-in stubs per field.
    """
    language = texts.language if texts.language in ("fi", "en") else "fi"
    stubs = stub_invoice_texts(language=language)
    nl_blobs = (description_fi or "", description_en or "")

    sales_cp = _clean_list(
        list(texts.sales_counterparties),
        list(stubs.sales_counterparties),
        nl_blobs=nl_blobs,
        is_counterparty=True,
    )
    purch_cp = _clean_list(
        list(texts.purchase_counterparties),
        list(stubs.purchase_counterparties),
        nl_blobs=nl_blobs,
        is_counterparty=True,
    )
    sales_desc = _clean_list(
        list(texts.sales_descriptions),
        list(stubs.sales_descriptions),
        nl_blobs=nl_blobs,
        is_counterparty=False,
    )
    purch_desc = _clean_list(
        list(texts.purchase_descriptions),
        list(stubs.purchase_descriptions),
        nl_blobs=nl_blobs,
        is_counterparty=False,
    )

    note = texts.notes or ""
    if any(
        descriptive_text_has_numbers(t)
        for t in (
            list(texts.sales_counterparties)
            + list(texts.purchase_counterparties)
            + list(texts.sales_descriptions)
            + list(texts.purchase_descriptions)
        )
    ):
        suffix = "sanitized digits for VR-13"
        note = f"{note}; {suffix}" if note else suffix

    return InvoiceDescriptiveTexts(
        sales_counterparties=sales_cp,
        purchase_counterparties=purch_cp,
        sales_descriptions=sales_desc,
        purchase_descriptions=purch_desc,
        language=language,  # type: ignore[arg-type]
        notes=note or None,
    )
