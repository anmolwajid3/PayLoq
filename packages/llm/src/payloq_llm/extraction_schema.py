"""Ollama ``format`` JSON Schema for section-B parameter extraction."""

from __future__ import annotations

from typing import Any

# JSON Schema passed to Ollama /api/chat as ``format`` (section B).
EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scenario_shape", "scenario_shape_quote", "stated", "parameters"],
    "properties": {
        "scenario_shape": {
            "type": "string",
            "enum": [
                "healthy",
                "weak",
                "cash_tight",
                "cash_critical",
                "unspecified",
            ],
        },
        "scenario_shape_quote": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
        },
        "stated": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "Map of field name → exact quote from the description.",
        },
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "revenue_monthly_eur",
                "revenue_annual_eur",
                "growth_per_month_fraction",
                "starting_cash_eur",
                "covenant_min_cash_eur",
                "dso_days",
                "dpo_days",
                "one_off_events",
                "industry",
                "company_size",
            ],
            "properties": {
                "revenue_monthly_eur": {
                    "anyOf": [{"type": "number"}, {"type": "null"}],
                },
                "revenue_annual_eur": {
                    "anyOf": [{"type": "number"}, {"type": "null"}],
                },
                "growth_per_month_fraction": {
                    "anyOf": [{"type": "number"}, {"type": "null"}],
                },
                "starting_cash_eur": {
                    "anyOf": [{"type": "number"}, {"type": "null"}],
                },
                "covenant_min_cash_eur": {
                    "anyOf": [{"type": "number"}, {"type": "null"}],
                },
                "dso_days": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "dpo_days": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "one_off_events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "amount_eur",
                            "month_index",
                            "direction",
                        ],
                        "properties": {
                            "type": {"type": "string"},
                            "amount_eur": {"type": "number"},
                            "month_index": {"type": "integer"},
                            "direction": {
                                "type": "string",
                                "enum": ["inflow", "outflow"],
                            },
                        },
                    },
                },
                "industry": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "company_size": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
        },
    },
}


def extraction_format_schema() -> dict[str, Any]:
    """Return a copy of the section-B schema for Ollama ``format``."""
    import copy

    return copy.deepcopy(EXTRACTION_JSON_SCHEMA)
