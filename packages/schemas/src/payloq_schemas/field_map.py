"""Load the generic extraction field map (single config table).

Fidelity and Run summary display are driven only by this map — no hard-coded
per-field branches outside the declarative rows and their fidelity_rule names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

_FIELD_MAP_PATH = Path(__file__).with_name("field_map.json")


@dataclass(frozen=True)
class FieldMapRow:
    input_name: str
    output_location: str
    display_label: dict[str, str]
    fidelity_rule: str
    format: str
    engine_keys: tuple[str, ...]
    components: tuple[str, ...] = ()

    def label(self, lang: str = "en") -> str:
        key = (lang or "en").lower()
        if key in self.display_label:
            return self.display_label[key]
        return self.display_label.get("en") or self.input_name

    @property
    def output_key(self) -> str:
        """Last path segment of output_location (dict key under params or options)."""
        return self.output_location.rsplit(".", 1)[-1]

    @property
    def output_root(self) -> str:
        """First path segment: parameters_from_language_model | options."""
        return self.output_location.split(".", 1)[0]


def _row_from_dict(raw: dict[str, Any]) -> FieldMapRow:
    labels = raw.get("display_label") or {}
    if not isinstance(labels, dict):
        labels = {"en": str(labels)}
    return FieldMapRow(
        input_name=str(raw["input_name"]),
        output_location=str(raw["output_location"]),
        display_label={str(k): str(v) for k, v in labels.items()},
        fidelity_rule=str(raw.get("fidelity_rule") or "numeric_near"),
        format=str(raw.get("format") or "text"),
        engine_keys=tuple(str(k) for k in (raw.get("engine_keys") or [raw["input_name"]])),
        components=tuple(str(c) for c in (raw.get("components") or ())),
    )


@lru_cache(maxsize=1)
def load_field_map() -> tuple[FieldMapRow, ...]:
    data = json.loads(_FIELD_MAP_PATH.read_text(encoding="utf-8"))
    fields = data.get("fields") or []
    if not isinstance(fields, list) or not fields:
        raise ValueError("field_map.json must contain a non-empty fields list")
    return tuple(_row_from_dict(row) for row in fields if isinstance(row, dict))


def iter_field_map() -> Iterator[FieldMapRow]:
    yield from load_field_map()


def field_map_by_input_name() -> dict[str, FieldMapRow]:
    return {row.input_name: row for row in load_field_map()}


def read_output_location(
    *,
    params: dict[str, Any] | None,
    options: dict[str, Any] | None,
    location: str,
) -> Any:
    """Read a dotted output_location from params/options (input.json roots)."""
    parts = location.split(".")
    if not parts:
        return None
    root = parts[0]
    if root == "parameters_from_language_model":
        cur: Any = params or {}
    elif root == "options":
        cur = options or {}
    else:
        cur = params or {}
        # Allow bare key paths.
        if len(parts) == 1:
            return cur.get(parts[0])
    for part in parts[1:]:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def resolve_path_in_params(params: dict[str, Any], row: FieldMapRow) -> Any:
    """Read the output value for a map row from a flat params dict when possible."""
    if row.output_root == "parameters_from_language_model":
        return params.get(row.output_key)
    return None


def format_field_value(row: FieldMapRow, value: Any, *, lang: str = "en") -> str:
    """Human-readable display string for a Run summary cell (no cross-row labels)."""
    if value is None:
        return "—"
    fmt = row.format
    if fmt == "eur":
        try:
            return f"{float(value):,.2f} €".replace(",", " ")
        except (TypeError, ValueError):
            return str(value)
    if fmt == "fraction":
        try:
            return f"{float(value) * 100:.4g}%"
        except (TypeError, ValueError):
            return str(value)
    if fmt == "percent":
        try:
            return f"{float(value):.4g}%"
        except (TypeError, ValueError):
            return str(value)
    if fmt == "count":
        try:
            return f"{float(value):.0f}"
        except (TypeError, ValueError):
            return str(value)
    if fmt == "days":
        try:
            return f"{float(value):.0f} days" if lang != "fi" else f"{float(value):.0f} pv"
        except (TypeError, ValueError):
            return str(value)
    if fmt == "one_off_events":
        if not isinstance(value, list) or not value:
            return "—" if lang != "fi" else "—"
        parts: list[str] = []
        for ev in value:
            if not isinstance(ev, dict):
                continue
            amt = ev.get("amount_eur")
            month = ev.get("month_index")
            direction = ev.get("direction")
            try:
                amt_s = f"{float(amt):,.2f} €".replace(",", " ")
            except (TypeError, ValueError):
                amt_s = str(amt)
            parts.append(f"{amt_s} · month {month} · {direction}")
        return "; ".join(parts) if parts else "—"
    return str(value)


def _summary_source(
    *,
    keys: tuple[str, ...],
    sources: dict[str, Any],
    stated_values: dict[str, Any],
) -> str | None:
    """Stated wins, then derived, then assumed or any other recorded source."""
    saw_derived = False
    saw_other: str | None = None
    for key in keys:
        if sources.get(key) == "stated" or (
            key in stated_values and stated_values.get(key) not in (None, "")
        ):
            return "stated"
        if sources.get(key) == "derived":
            saw_derived = True
        elif key in sources and saw_other is None:
            saw_other = str(sources[key])
    if saw_derived:
        return "derived"
    return saw_other


def build_field_summary_rows(
    *,
    params: dict[str, Any] | None,
    options: dict[str, Any] | None = None,
    lang: str = "en",
) -> list[dict[str, Any]]:
    """
    Run summary rows: one per field-map row, each using that row's display label only.
    """
    params = dict(params or {})
    options = dict(options or {})
    sources = dict(params.get("field_sources") or {})
    stated_values = dict(params.get("stated_values") or {})
    rows: list[dict[str, Any]] = []
    for row in load_field_map():
        value = read_output_location(
            params=params, options=options, location=row.output_location
        )
        source = _summary_source(
            keys=(row.output_key, row.input_name, *row.engine_keys),
            sources=sources,
            stated_values=stated_values,
        )
        rows.append(
            {
                "input_name": row.input_name,
                "output_location": row.output_location,
                "label": row.label(lang),
                "label_en": row.label("en"),
                "label_fi": row.label("fi"),
                "value": value,
                "display": format_field_value(row, value, lang=lang),
                "source": source,
                "format": row.format,
                "fidelity_rule": row.fidelity_rule,
            }
        )
    return rows


# B ↔ engine helpers derived from the map (replaces hard-coded alias tables for fidelity).
def b_to_engine_from_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in load_field_map():
        if row.output_root == "parameters_from_language_model":
            out[row.input_name] = row.output_key
    return out


def engine_to_b_from_map() -> dict[str, str]:
    return {v: k for k, v in b_to_engine_from_map().items()}
