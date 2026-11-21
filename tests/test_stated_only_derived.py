"""Stated-only model output + code derivations (property test).

50 random descriptions, each stating a random subset of fields. A chatty model
payload fills every other field, including conversions (annual from monthly,
decimal from percent, days from weeks or months). After the stated-only pass:

- model output is null for every unstated schema field
- every derived value equals the formula on the stated inputs, with source "derived"

No fixed example companies or TC-specific branches.
"""

from __future__ import annotations

import random
import string

from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.extraction_schema import EXTRACTION_JSON_SCHEMA
from payloq_llm.stated_only import apply_derivations, prepare_stated_only_model

N_INPUTS = 50
PROP_SEED = 20261121


def _schema_props() -> dict:
    return EXTRACTION_JSON_SCHEMA["properties"]["parameters"]["properties"]


def _fmt_int(n: int) -> str:
    return f"{int(n):,}"


def _token(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(8))


def _empty_parameters() -> dict:
    out = {}
    for name in _schema_props():
        out[name] = [] if name == "one_off_events" else None
    return out


def _build_case(rng: random.Random) -> tuple[str, dict, dict, dict]:
    """Return description, stated subset, truthful model parameters, expected derived."""
    monthly = float(rng.randrange(80_000, 400_000, 100)) if rng.random() < 0.55 else None
    annual = float(rng.randrange(240_000, 3_600_000, 100)) if rng.random() < 0.45 else None
    if monthly is not None and annual is not None and abs(annual - monthly * 12) < 1:
        annual += 100_000.0
    # One revenue mode keeps the derivation unambiguous. Both stated → no derivation.
    if monthly is not None and annual is not None and rng.random() < 0.5:
        annual = None
    if monthly is None and annual is None and rng.random() < 0.5:
        monthly = float(rng.randrange(80_000, 400_000, 100))

    percent = round(rng.uniform(0.4, 3.8), 3) if rng.random() < 0.6 else None
    if percent is not None and rng.random() < 0.25:
        percent = -percent

    dso_mode = rng.choice(["none", "days", "weeks", "months"])
    dpo_mode = rng.choice(["none", "days", "weeks", "months"])
    dso_days = float(rng.randint(15, 80)) if dso_mode == "days" else None
    dso_weeks = float(rng.randint(2, 12)) if dso_mode == "weeks" else None
    dso_months = float(rng.randint(1, 3)) if dso_mode == "months" else None
    dpo_days = float(rng.randint(15, 80)) if dpo_mode == "days" else None
    dpo_weeks = float(rng.randint(2, 12)) if dpo_mode == "weeks" else None
    dpo_months = float(rng.randint(1, 3)) if dpo_mode == "months" else None

    starting = float(rng.randrange(20_000, 400_000, 100)) if rng.random() < 0.5 else None
    covenant = float(rng.randrange(10_000, 300_000, 100)) if rng.random() < 0.5 else None
    if starting is not None and covenant is not None and starting == covenant:
        covenant += 100.0

    one_off = None
    if rng.random() < 0.35:
        one_off = {
            "type": "other",
            "amount_eur": float(rng.randrange(20_000, 180_000, 100)),
            "month_index": rng.randint(1, 12),
            "direction": rng.choice(["inflow", "outflow"]),
        }

    industry = f"industry-{_token(rng)}" if rng.random() < 0.4 else None
    company_size = f"size-{_token(rng)}" if rng.random() < 0.4 else None

    direct = {
        "revenue_monthly_eur": monthly,
        "revenue_annual_eur": annual,
        "growth_per_month_percent": percent,
        "starting_cash_eur": starting,
        "covenant_min_cash_eur": covenant,
        "dso_days": dso_days,
        "dpo_days": dpo_days,
        "dso_weeks": dso_weeks,
        "dpo_weeks": dpo_weeks,
        "dso_months": dso_months,
        "dpo_months": dpo_months,
        "industry": industry,
        "company_size": company_size,
    }

    parts = ["A trading business."]
    stated: dict[str, str] = {}
    parameters = _empty_parameters()
    phrases = {
        "revenue_monthly_eur": lambda v: f"Monthly revenue {_fmt_int(v)} euro.",
        "revenue_annual_eur": lambda v: f"Annual revenue {_fmt_int(v)} euro.",
        "growth_per_month_percent": lambda v: f"Growth {v}% per month.",
        "starting_cash_eur": lambda v: f"Starting cash {_fmt_int(v)} euro.",
        "covenant_min_cash_eur": lambda v: f"Bank minimum cash {_fmt_int(v)} euro.",
        "dso_days": lambda v: f"DSO {int(v)} days.",
        "dpo_days": lambda v: f"DPO {int(v)} days.",
        "dso_weeks": lambda v: f"DSO {int(v)} weeks.",
        "dpo_weeks": lambda v: f"DPO {int(v)} weeks.",
        "dso_months": lambda v: f"DSO {int(v)} months.",
        "dpo_months": lambda v: f"DPO {int(v)} months.",
        "industry": lambda v: f"Industry is {v}.",
        "company_size": lambda v: f"Company size is {v}.",
    }
    for name, value in direct.items():
        if value is None:
            continue
        phrase = phrases[name](value)
        parts.append(phrase)
        stated[name] = phrase
        parameters[name] = value
    if one_off is not None:
        phrase = (
            f"One-off {one_off['direction']} of {_fmt_int(one_off['amount_eur'])} "
            f"euro in month {one_off['month_index']}."
        )
        parts.append(phrase)
        stated["one_off_events"] = phrase
        parameters["one_off_events"] = [one_off]

    expected: dict[str, tuple[str, float]] = {}
    if monthly is not None and annual is None:
        expected["revenue_annual_eur"] = (
            "revenue_monthly_eur * 12",
            round(monthly * 12.0, 2),
        )
    if annual is not None and monthly is None:
        expected["revenue_monthly_eur"] = (
            "revenue_annual_eur / 12",
            round(annual / 12.0, 2),
        )
    if percent is not None:
        expected["growth_per_month_fraction"] = (
            "growth_per_month_percent / 100",
            round(percent / 100.0, 10),
        )
    if dso_weeks is not None and dso_days is None:
        expected["dso_days"] = ("dso_weeks * 7", round(dso_weeks * 7.0, 2))
    elif dso_months is not None and dso_days is None:
        expected["dso_days"] = ("dso_months * 30", round(dso_months * 30.0, 2))
    if dpo_weeks is not None and dpo_days is None:
        expected["dpo_days"] = ("dpo_weeks * 7", round(dpo_weeks * 7.0, 2))
    elif dpo_months is not None and dpo_days is None:
        expected["dpo_days"] = ("dpo_months * 30", round(dpo_months * 30.0, 2))

    return " ".join(parts), stated, parameters, expected


def _chatty(parameters: dict, stated: dict, expected: dict, rng: random.Random) -> dict:
    """Fill every unstated schema field, including the conversions a model might invent."""
    chatty = dict(parameters)
    chatty["one_off_events"] = list(parameters.get("one_off_events") or [])
    for field, (_formula, value) in expected.items():
        if field not in stated:
            chatty[field] = value
            if field == "growth_per_month_fraction":
                chatty["monthly_revenue_growth"] = value
    # Outside 1–120 so a thousands-group fragment cannot look like this count.
    sentinel_eur = 8_765_432.0 + rng.randint(1, 50)
    sentinel_count = 250 + rng.randint(0, 20)
    for name in _schema_props():
        if name in stated or name == "one_off_events":
            continue
        if chatty.get(name) not in (None, [], ""):
            continue
        if name in {"industry", "company_size"}:
            chatty[name] = f"invented-{_token(rng)}"
        elif name in {"dso_weeks", "dpo_weeks", "dso_months", "dpo_months"} or "days" in name:
            chatty[name] = float(sentinel_count)
        elif name == "growth_per_month_percent":
            chatty[name] = 17.0 + rng.random()
        else:
            chatty[name] = sentinel_eur
    return chatty


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == []


def test_stated_only_50_random_subsets_zero_violations() -> None:
    rng = random.Random(PROP_SEED)
    violations: list[str] = []
    for index in range(N_INPUTS):
        description, stated, truthful, expected = _build_case(rng)
        chatty = _chatty(truthful, stated, expected, rng)
        model_out, _stated_out, _warnings = prepare_stated_only_model(
            chatty, stated, description
        )
        for name in _schema_props():
            if name in stated:
                continue
            if not _is_empty(model_out.get(name)):
                violations.append(
                    f"[{index}] model output has unstated {name}={model_out.get(name)!r}"
                )
        # Converted fraction is not a model field and must not survive as a model value.
        if "growth_per_month_percent" in stated and not _is_empty(
            model_out.get("growth_per_month_fraction")
        ):
            violations.append(f"[{index}] model kept growth fraction")

        derived_params, records = apply_derivations(model_out)
        by_field = {rec["field"]: rec for rec in records}
        if set(by_field) != set(expected):
            violations.append(
                f"[{index}] derived fields {sorted(by_field)} != {sorted(expected)}"
            )
        for field, (formula, value) in expected.items():
            rec = by_field.get(field)
            if rec is None:
                continue
            if rec.get("source") != "derived" or rec.get("formula") != formula:
                violations.append(
                    f"[{index}] {field} source/formula {rec.get('source')} {rec.get('formula')}"
                )
            if abs(float(rec["value"]) - float(value)) > 1e-6:
                violations.append(
                    f"[{index}] {field} value {rec['value']} != formula {value} ({formula})"
                )
            if abs(float(derived_params[field]) - float(value)) > 1e-6:
                violations.append(
                    f"[{index}] parameter {field}={derived_params[field]} != {value}"
                )

        envelope = {
            "scenario_shape": "unspecified",
            "scenario_shape_quote": None,
            "stated": stated,
            "parameters": chatty,
        }
        finalized, _changes, result = finalize_extracted_parameters(
            envelope,
            description,
            industry="services",
            company_size="small",
            seed=1000 + index,
            months=12,
            llm_model_name="stated-only-prop",
        )
        if not result.ok:
            violations.append(f"[{index}] finalize failed: {result.error_text()}")
            continue
        final_records = {
            rec["field"]: rec for rec in (finalized.get("derived_values") or [])
        }
        sources = finalized.get("field_sources") or {}
        for field, (formula, value) in expected.items():
            rec = final_records.get(field)
            if rec is None or rec.get("source") != "derived" or rec.get("formula") != formula:
                violations.append(f"[{index}] finalized record missing for {field}: {rec}")
                continue
            if abs(float(rec["value"]) - float(value)) > 1e-6:
                violations.append(
                    f"[{index}] finalized {field}={rec['value']} != {value}"
                )
            for key in rec.get("keys") or [field]:
                if sources.get(key) != "derived":
                    violations.append(
                        f"[{index}] {key} source={sources.get(key)!r} expected derived"
                    )

    print(
        f"STATED_ONLY inputs={N_INPUTS} violations={len(violations)} "
        f"sample={violations[:8]}"
    )
    assert not violations, (
        f"{len(violations)} violations across {N_INPUTS} inputs — {violations[:12]}"
    )
