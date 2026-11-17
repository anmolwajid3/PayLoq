"""VR-13 / FR-A-32 helpers: descriptive texts must not contain numbers."""

from __future__ import annotations

import re

# Any ASCII/Unicode digit fails VR-13 in counterparty / description fields.
# Invoice ids (S-2600) are separate fields and are not checked with this helper.
DIGIT_IN_TEXT = re.compile(r"\d")

# Strip euro amounts, digit runs, and common money suffixes copied from NL descriptions.
_AMOUNT_OR_DIGIT_TOKEN = re.compile(
    r"(?:"
    r"[€$£]\s*[~\-]?\s*\d[\d\s.,]*\s*[kKmMbB]?"  # €30k, €95,000
    r"|"
    r"\d[\d\s.,]*\s*[€$£]"  # 95,000€
    r"|"
    r"\b\d[\d\s.,]*\s*(?:eur|euro|euros|usd)\b"  # 30000 EUR
    r"|"
    r"\b\d+[\d.,]*\s*[kKmMbB]\b"  # 30k, 25K
    r"|"
    r"\d+"  # remaining digits
    r")",
    re.IGNORECASE,
)

_MULTI_SPACE = re.compile(r"\s{2,}")
_DANGLING_PUNCT = re.compile(r"\s*([,;:/|\-–—])\s*(?=[,;:/|\-–—]|$)")
_EDGE_PUNCT = re.compile(r"^[\s,;:/|\-–—.~]+|[\s,;:/|\-–—.~]+$")


def descriptive_text_has_numbers(text: str | None) -> bool:
    """True when free-text descriptive field contains any digit (VR-13)."""
    return bool(DIGIT_IN_TEXT.search(text or ""))


def strip_numbers_from_descriptive_text(text: str | None) -> str:
    """
    Remove digits and currency/amount tokens from a free-text field.

    Does not touch invoice id fields — callers must only pass counterparty /
    description (and LLM invoice text lists). Empty/whitespace-only results
    become "" so callers can fall back to stubs.
    """
    if not text:
        return ""
    cleaned = _AMOUNT_OR_DIGIT_TOKEN.sub(" ", text)
    cleaned = _DANGLING_PUNCT.sub(" ", cleaned)
    cleaned = _EDGE_PUNCT.sub("", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    # Safety: if any digit remains (edge scripts), drop them.
    if DIGIT_IN_TEXT.search(cleaned):
        cleaned = DIGIT_IN_TEXT.sub("", cleaned)
        cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
        cleaned = _EDGE_PUNCT.sub("", cleaned)
    return cleaned
