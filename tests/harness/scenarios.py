"""Scenario templates. Numeric values are drawn from the seed, not fixed literals."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SEEDS: tuple[int, ...] = (1, 2, 3, 42, 99)

# Work-order scenarios, then the additional descriptions. Table row order.
SCENARIO_ORDER: tuple[str, ...] = (
    "good",
    "weak",
    "cash_in_trouble",
    "invoices_out_of_balance",
    "cash_turning_critical",
    "vague",
    "fully_stated",
    "partly_stated",
    "one_off_inflow",
    "no_one_off",
    "annual_revenue",
    "months_24",
    "finnish",
)

_PARAM_KEYS: tuple[str, ...] = (
    "revenue_monthly_eur",
    "revenue_annual_eur",
    "growth_per_month_percent",
    "starting_cash_eur",
    "covenant_min_cash_eur",
    "dso_days",
    "dpo_days",
    "dso_weeks",
    "dpo_weeks",
    "dso_months",
    "dpo_months",
    "one_off_events",
    "industry",
    "company_size",
)


@dataclass
class Case:
    scenario: str
    seed: int
    text: str
    language: str
    months: int
    scenario_id: str | None
    industry: str
    company_size: str
    shape: str
    extraction: dict[str, Any]
    stated_values: dict[str, float]
    one_off: dict[str, Any] | None
    cash_shape: str | None
    broken_receivables: bool
    template: dict[str, Any] = field(repr=False)


def load_templates() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        if path.name == "invoice_texts.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        found[str(data["id"])] = data
    missing = [name for name in SCENARIO_ORDER if name not in found]
    extra = sorted(set(found) - set(SCENARIO_ORDER))
    if missing or extra:
        raise RuntimeError(f"scenario fixtures missing={missing} extra={extra}")
    return found


def _rng(scenario: str, seed: int) -> random.Random:
    digest = hashlib.sha256(f"{scenario}|{seed}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _draw(rng: random.Random, spec: dict[str, Any]) -> float:
    lo = spec["min"]
    hi = spec["max"]
    step = spec["step"]
    times = spec.get("times", 1)
    if isinstance(step, float):
        decimals = int(spec.get("decimals", 1))
        n = round((float(hi) - float(lo)) / float(step))
        value: float = round(float(lo) + rng.randint(0, n) * float(step), decimals)
    else:
        n = int((int(hi) - int(lo)) // int(step))
        value = int(lo) + rng.randint(0, n) * int(step)
    if times != 1:
        value = int(value) * int(times)
    return value


def _format_value(name: str, value: float) -> str:
    if name == "growth_per_month_percent":
        return f"{float(value):.1f}"
    return str(int(value))


def build_case(
    scenario: str, seed: int, templates: dict[str, dict[str, Any]] | None = None
) -> Case:
    templates = templates or load_templates()
    template = templates[scenario]
    rng = _rng(scenario, seed)
    numeric: dict[str, float] = {}
    ranges = template.get("ranges") or {}
    for name, spec in ranges.items():
        numeric[name] = _draw(rng, spec)
    one_off_spec = template.get("one_off")
    one_off: dict[str, Any] | None = None
    if one_off_spec:
        amount = int(_draw(rng, one_off_spec["amount"]))
        month = int(_draw(rng, one_off_spec["month"]))
        numeric["one_off_amount_eur"] = amount
        numeric["one_off_month"] = month
        one_off = {
            "type": one_off_spec["type"],
            "amount_eur": amount,
            "month_index": month,
            "direction": one_off_spec["direction"],
        }
    rendered = {name: _format_value(name, value) for name, value in numeric.items()}
    quotes = template.get("quotes") or {}
    stated_order = list(template.get("stated_order") or [])
    stated: dict[str, str] = {}
    parts = [str(template["lead"]).strip()]
    for key in stated_order:
        sentence = str(quotes[key]).format(**rendered)
        stated[key] = sentence
        parts.append(sentence)
    text = " ".join(part for part in parts if part)

    parameters: dict[str, Any] = {key: None for key in _PARAM_KEYS}
    parameters["one_off_events"] = []
    stated_values: dict[str, float] = {}
    for key in stated_order:
        if key == "one_off_events":
            parameters["one_off_events"] = [dict(one_off)] if one_off else []
            continue
        parameters[key] = numeric[key]
        stated_values[key] = float(numeric[key])
    extraction = {
        "scenario_shape": template["scenario_shape"],
        "scenario_shape_quote": template.get("scenario_shape_quote"),
        "stated": stated,
        "parameters": parameters,
    }
    scenario_id = template.get("scenario_id")
    expect = template.get("expect") or {}
    return Case(
        scenario=scenario,
        seed=seed,
        text=text,
        language=str(template.get("language") or "en"),
        months=int(template.get("months") or 12),
        scenario_id=str(scenario_id) if scenario_id else None,
        industry=str(template.get("industry") or "metal workshop (machine shop)"),
        company_size=str(template.get("company_size") or "small"),
        shape=str(template["scenario_shape"]),
        extraction=extraction,
        stated_values=stated_values,
        one_off=one_off,
        cash_shape=expect.get("cash_shape"),
        broken_receivables=bool(expect.get("broken_receivables")),
        template=template,
    )
