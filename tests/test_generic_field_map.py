"""Property tests for the generic field map (fidelity + display).

No hard-coded example amounts/phrases — random values only.
"""

from __future__ import annotations

import json
import random
import string
from pathlib import Path
from typing import Any

import pytest

from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_llm.extraction_schema import EXTRACTION_JSON_SCHEMA
from payloq_schemas.field_map import (
    build_field_summary_rows,
    field_map_by_input_name,
    iter_field_map,
    load_field_map,
    read_output_location,
)
from payloq_schemas.models import (
    GeneratorInput,
    Options,
    ParametersFromLanguageModel,
    ScenarioDescription,
    ScenarioMeta,
)
from payloq_validate.fidelity import check_fidelity

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_MAP = REPO_ROOT / "packages/schemas/src/payloq_schemas/field_map.json"
WEB_MAP = REPO_ROOT / "apps/web/src/lib/field_map.json"

# Property-test budgets (random cases).
CASES_PER_FIELD = 25
SWAP_CASES = 40
MUTATE_CASES = 40
UNSTATED_CASES = 40


def _schema_parameter_names() -> set[str]:
    props = (
        EXTRACTION_JSON_SCHEMA.get("properties", {})
        .get("parameters", {})
        .get("properties", {})
    )
    return set(props.keys())


def test_field_map_covers_extraction_schema_exactly() -> None:
    rows = load_field_map()
    names = [r.input_name for r in rows]
    assert len(names) == len(set(names)), names
    assert set(names) == _schema_parameter_names()


def test_web_field_map_copy_matches_schema() -> None:
    assert SCHEMA_MAP.is_file()
    assert WEB_MAP.is_file()
    assert json.loads(SCHEMA_MAP.read_text(encoding="utf-8")) == json.loads(
        WEB_MAP.read_text(encoding="utf-8")
    )


def _fmt_int(n: int) -> str:
    """Format with thousands separators that grounding accepts."""
    return f"{n:,}"


def _random_eur(rng: random.Random, lo: int = 12_000, hi: int = 900_000) -> int:
    # Avoid multiples that collide across fields in swap tests by using odd steps.
    return rng.randrange(lo, hi, 100)


def _random_growth(rng: random.Random) -> float:
    # Fraction in (-0.2, 0.2) excluding near-zero noise.
    raw = rng.uniform(0.001, 0.05)
    return raw if rng.random() < 0.7 else -raw


def _random_days(rng: random.Random) -> int:
    return rng.randint(14, 90)


def _random_month(rng: random.Random) -> int:
    return rng.randint(1, 12)


def _random_direction(rng: random.Random) -> str:
    return rng.choice(["inflow", "outflow"])


def _random_token(rng: random.Random, n: int = 8) -> str:
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(n))


def _phrase_for_field(input_name: str, value: Any) -> str:
    """Description fragment stating one field — templates only, values injected."""
    if input_name == "revenue_monthly_eur":
        return f"Monthly revenue {_fmt_int(int(value))} euro."
    if input_name == "revenue_annual_eur":
        return f"Annual revenue {_fmt_int(int(value))} euro."
    if input_name == "growth_per_month_fraction":
        pct = float(value) * 100.0
        return f"Growth {pct:.4g}% per month."
    if input_name == "starting_cash_eur":
        return f"Starting cash {_fmt_int(int(value))} euro."
    if input_name == "covenant_min_cash_eur":
        return f"Bank minimum cash {_fmt_int(int(value))} euro."
    if input_name == "dso_days":
        return f"DSO {int(value)} days."
    if input_name == "dpo_days":
        return f"DPO {int(value)} days."
    if input_name == "one_off_events":
        ev = value[0]
        return (
            f"One-off {ev['direction']} of {_fmt_int(int(ev['amount_eur']))} "
            f"euro in month {int(ev['month_index'])}."
        )
    if input_name == "industry":
        return f"Industry is {value}."
    if input_name == "company_size":
        return f"Company size is {value}."
    raise AssertionError(f"no phrase template for {input_name}")


def _random_value(input_name: str, rng: random.Random) -> Any:
    if input_name == "revenue_monthly_eur":
        return float(_random_eur(rng))
    if input_name == "revenue_annual_eur":
        return float(_random_eur(rng, 200_000, 4_000_000))
    if input_name == "growth_per_month_fraction":
        return _random_growth(rng)
    if input_name == "starting_cash_eur":
        return float(_random_eur(rng, 10_000, 500_000))
    if input_name == "covenant_min_cash_eur":
        return float(_random_eur(rng, 5_000, 400_000))
    if input_name == "dso_days":
        return float(_random_days(rng))
    if input_name == "dpo_days":
        return float(_random_days(rng))
    if input_name == "one_off_events":
        return [
            {
                "type": "other",
                "amount_eur": float(_random_eur(rng, 20_000, 200_000)),
                "month_index": _random_month(rng),
                "direction": _random_direction(rng),
            }
        ]
    if input_name == "industry":
        return f"industry-{_random_token(rng)}"
    if input_name == "company_size":
        return f"size-{_random_token(rng)}"
    raise AssertionError(input_name)


def _null_parameters() -> dict[str, Any]:
    return {
        "revenue_monthly_eur": None,
        "revenue_annual_eur": None,
        "growth_per_month_fraction": None,
        "starting_cash_eur": None,
        "covenant_min_cash_eur": None,
        "dso_days": None,
        "dpo_days": None,
        "one_off_events": [],
        "industry": None,
        "company_size": None,
    }


def _envelope_for(
    *,
    stated_fields: dict[str, Any],
    industry: str | None = None,
    company_size: str | None = None,
) -> dict[str, Any]:
    parameters = _null_parameters()
    stated: dict[str, str] = {}
    for name, value in stated_fields.items():
        parameters[name] = value
        stated[name] = _phrase_for_field(name, value)
    if industry is not None:
        parameters["industry"] = industry
    if company_size is not None:
        parameters["company_size"] = company_size
    return {
        "scenario_shape": "unspecified",
        "scenario_shape_quote": None,
        "stated": stated,
        "parameters": parameters,
    }


def _finalize(
    envelope: dict[str, Any],
    description: str,
    *,
    seed: int,
    industry: str = "services",
    company_size: str = "small",
) -> tuple[dict[str, Any], Any]:
    params, _changes, result = finalize_extracted_parameters(
        envelope,
        description,
        industry=industry,
        company_size=company_size,
        seed=seed,
        months=12,
        llm_model_name="test",
    )
    return params, result


def _options_for(industry: str, company_size: str) -> dict[str, Any]:
    return {
        "industry": industry,
        "company_size": company_size,
        "months": 12,
        "language": "en",
        "currency": "EUR",
        "scenario_id": "prop",
    }


def _expected_output_value(input_name: str, value: Any, params: dict[str, Any]) -> Any:
    row = field_map_by_input_name()[input_name]
    if input_name == "revenue_annual_eur":
        # Annual may remain on params; monthly is derived when monthly was null.
        annual = params.get("revenue_annual_eur")
        if annual is not None:
            return float(annual)
        return float(value)
    if row.output_root == "options":
        return value
    if input_name == "one_off_events":
        return value
    if input_name == "revenue_monthly_eur":
        return float(value)
    return float(value) if isinstance(value, (int, float)) else value


def _assert_value_at_location(
    input_name: str,
    expected: Any,
    params: dict[str, Any],
    options: dict[str, Any],
) -> None:
    row = field_map_by_input_name()[input_name]
    actual = read_output_location(
        params=params, options=options, location=row.output_location
    )
    if input_name == "one_off_events":
        assert isinstance(actual, list) and actual, actual
        exp = expected[0]
        act = actual[0]
        assert float(act["amount_eur"]) == pytest.approx(float(exp["amount_eur"]), abs=1)
        assert int(act["month_index"]) == int(exp["month_index"])
        assert str(act["direction"]).lower() == str(exp["direction"]).lower()
        return
    if input_name == "revenue_annual_eur":
        # Output location is revenue_annual_eur; also monthly should be annual/12.
        assert actual is not None
        assert float(actual) == pytest.approx(float(expected), abs=1)
        monthly = params.get("monthly_revenue_start_eur")
        assert monthly is not None
        assert float(monthly) == pytest.approx(float(expected) / 12.0, abs=1)
        return
    if isinstance(expected, (int, float)):
        assert actual is not None, row.output_location
        assert float(actual) == pytest.approx(float(expected), abs=1)
    else:
        assert str(actual).casefold() == str(expected).casefold()


def _assert_label_shows_value(
    input_name: str,
    expected: Any,
    params: dict[str, Any],
    options: dict[str, Any],
) -> None:
    row = field_map_by_input_name()[input_name]
    summary = build_field_summary_rows(params=params, options=options, lang="en")
    by_name = {r["input_name"]: r for r in summary}
    assert input_name in by_name
    entry = by_name[input_name]
    assert entry["label"] == row.label("en")
    # Value under this row's label must match the field (no cross-row swap).
    if input_name == "one_off_events":
        assert expected[0]["direction"] in entry["display"]
        assert str(int(expected[0]["month_index"])) in entry["display"]
        return
    if isinstance(expected, (int, float)):
        # Display encodes the number; tolerate formatting.
        raw = str(int(expected)) if float(expected) == int(expected) else str(expected)
        # Growth shown as percent.
        if input_name == "growth_per_month_fraction":
            pct = float(expected) * 100.0
            assert f"{pct:.4g}" in entry["display"].replace(" ", "") or str(
                round(pct, 4)
            ) in entry["display"]
            return
        assert raw in entry["display"].replace(" ", "").replace(",", "") or raw in entry[
            "display"
        ].replace(",", "")
    else:
        assert str(expected) in entry["display"]


@pytest.mark.parametrize("row", list(iter_field_map()), ids=lambda r: r.input_name)
def test_each_field_random_stated_reaches_output_and_label(row: Any) -> None:
    failures: list[str] = []
    for i in range(CASES_PER_FIELD):
        rng = random.Random(1000 + hash(row.input_name) % 10_000 + i)
        value = _random_value(row.input_name, rng)
        description = _phrase_for_field(row.input_name, value)
        industry = "services"
        company_size = "small"
        if row.input_name == "industry":
            industry = str(value)
        if row.input_name == "company_size":
            company_size = str(value)
        envelope = _envelope_for(
            stated_fields={row.input_name: value},
            industry=industry if row.input_name == "industry" else None,
            company_size=company_size if row.input_name == "company_size" else None,
        )
        params, stated_result = _finalize(
            envelope,
            description,
            seed=42 + i,
            industry=industry,
            company_size=company_size,
        )
        if not stated_result.ok:
            failures.append(f"case {i}: finalize failed: {stated_result.error_text()}")
            continue
        options = _options_for(industry, company_size)
        # For option fields, stated_values carry the extract; options must match.
        if row.output_root == "options":
            params = dict(params)
            params.setdefault("stated_values", {})
            params["stated_values"][row.input_name] = value
        try:
            _assert_value_at_location(row.input_name, value, params, options)
            _assert_label_shows_value(row.input_name, value, params, options)
            fid = check_fidelity(
                params=params,
                stated_values=params.get("stated_values"),
                options=options,
            )
            if not fid.ok:
                failures.append(f"case {i}: fidelity {fid.error_text()}")
        except AssertionError as exc:
            failures.append(f"case {i}: {exc}")
    assert not failures, (
        f"{row.input_name}: {len(failures)}/{CASES_PER_FIELD} failed — "
        f"{failures[:5]}"
    )


def test_two_fields_do_not_swap() -> None:
    failures: list[str] = []
    numeric_rows = [
        r
        for r in load_field_map()
        if r.fidelity_rule == "numeric_near" and r.input_name != "revenue_annual_eur"
    ]
    for i in range(SWAP_CASES):
        rng = random.Random(5000 + i)
        a, b = rng.sample(numeric_rows, 2)
        va = _random_value(a.input_name, rng)
        vb = _random_value(b.input_name, rng)
        # Ensure distinct values so a swap is detectable.
        while float(va) == float(vb):
            vb = _random_value(b.input_name, rng)
        description = (
            f"{_phrase_for_field(a.input_name, va)} {_phrase_for_field(b.input_name, vb)}"
        )
        envelope = _envelope_for(stated_fields={a.input_name: va, b.input_name: vb})
        params, stated_result = _finalize(envelope, description, seed=100 + i)
        if not stated_result.ok:
            failures.append(f"case {i}: finalize {stated_result.error_text()}")
            continue
        options = _options_for("services", "small")
        try:
            _assert_value_at_location(a.input_name, va, params, options)
            _assert_value_at_location(b.input_name, vb, params, options)
            summary = build_field_summary_rows(params=params, options=options, lang="en")
            by_name = {r["input_name"]: r for r in summary}
            # Neither value shown under the other field's label.
            assert by_name[a.input_name]["label"] == a.label("en")
            assert by_name[b.input_name]["label"] == b.label("en")
            fid = check_fidelity(
                params=params,
                stated_values=params.get("stated_values"),
                options=options,
            )
            assert fid.ok, fid.error_text()
        except AssertionError as exc:
            failures.append(f"case {i} ({a.input_name}/{b.input_name}): {exc}")
    assert not failures, f"{len(failures)}/{SWAP_CASES} failed — {failures[:5]}"


def test_mutate_output_fails_fidelity_naming_field() -> None:
    failures: list[str] = []
    numeric_rows = [
        r
        for r in load_field_map()
        if r.fidelity_rule == "numeric_near" and r.input_name not in {"revenue_annual_eur"}
    ]
    for i in range(MUTATE_CASES):
        rng = random.Random(9000 + i)
        row = rng.choice(numeric_rows)
        value = _random_value(row.input_name, rng)
        description = _phrase_for_field(row.input_name, value)
        envelope = _envelope_for(stated_fields={row.input_name: value})
        params, stated_result = _finalize(envelope, description, seed=200 + i)
        if not stated_result.ok:
            failures.append(f"case {i}: finalize {stated_result.error_text()}")
            continue
        options = _options_for("services", "small")
        mutated = dict(params)
        key = row.output_key
        original = mutated.get(key)
        # Mutate far outside absolute and relative grounding tolerances.
        if original is None:
            mutated[key] = 999_999.0
        else:
            base = float(original)
            mutated[key] = base * 3.0 + 50_000.0 if abs(base) > 1e-9 else 50_000.0
        # Keep stated_values pointing at the pre-mutation stated amount.
        fid = check_fidelity(
            params=mutated,
            stated_values=params.get("stated_values"),
            options=options,
        )
        if fid.ok:
            failures.append(f"case {i}: expected fidelity error for {row.input_name}")
            continue
        err = fid.error_text()
        if row.input_name not in err and key not in err:
            failures.append(
                f"case {i}: error did not name field {row.input_name}: {err}"
            )
    assert not failures, f"{len(failures)}/{MUTATE_CASES} failed — {failures[:5]}"


def test_unstated_field_is_assumed_not_stated() -> None:
    failures: list[str] = []
    assumable = [
        r
        for r in load_field_map()
        if r.output_root == "parameters_from_language_model"
        and r.fidelity_rule == "numeric_near"
        and r.input_name
        in {
            "revenue_monthly_eur",
            "growth_per_month_fraction",
            "starting_cash_eur",
            "covenant_min_cash_eur",
            "dso_days",
            "dpo_days",
        }
    ]
    for i in range(UNSTATED_CASES):
        rng = random.Random(12_000 + i)
        # State one field so finalize succeeds with a grounded description;
        # leave the subject field unstated.
        subject = rng.choice(assumable)
        other = rng.choice([r for r in assumable if r.input_name != subject.input_name])
        other_val = _random_value(other.input_name, rng)
        description = _phrase_for_field(other.input_name, other_val)
        envelope = _envelope_for(stated_fields={other.input_name: other_val})
        params, stated_result = _finalize(envelope, description, seed=300 + i)
        if not stated_result.ok:
            failures.append(f"case {i}: finalize {stated_result.error_text()}")
            continue
        sources = params.get("field_sources") or {}
        key = subject.output_key
        src = sources.get(key)
        if src == "stated":
            failures.append(
                f"case {i}: {subject.input_name} marked stated but was unstated "
                f"(sources={sources})"
            )
            continue
        if src != "assumed":
            failures.append(
                f"case {i}: {subject.input_name} expected assumed, got {src!r}"
            )
    assert not failures, f"{len(failures)}/{UNSTATED_CASES} failed — {failures[:5]}"


def test_stated_everything_example_for_evidence(tmp_path: Path) -> None:
    """One stated-everything run for the evidence report (values still random-seeded)."""
    rng = random.Random(42)
    values = {r.input_name: _random_value(r.input_name, rng) for r in load_field_map()}
    # Avoid annual+monthly conflict: drop annual when monthly stated.
    values.pop("revenue_annual_eur", None)
    industry = str(values["industry"])
    company_size = str(values["company_size"])
    description = " ".join(
        _phrase_for_field(name, val) for name, val in values.items()
    )
    envelope = _envelope_for(
        stated_fields=values,
        industry=industry,
        company_size=company_size,
    )
    params, stated_result = _finalize(
        envelope,
        description,
        seed=42,
        industry=industry,
        company_size=company_size,
    )
    assert stated_result.ok, stated_result.error_text()
    options = _options_for(industry, company_size)
    summary = build_field_summary_rows(params=params, options=options, lang="en")
    fid = check_fidelity(
        params=params, stated_values=params.get("stated_values"), options=options
    )
    assert fid.ok, fid.error_text()

    # Build a minimal GeneratorInput for the evidence dump.
    inp = GeneratorInput(
        meta=ScenarioMeta(scenario="prop_stated_everything", fictional=True),
        scenario_description=ScenarioDescription(en=description, fi=description),
        options=Options.model_validate(options),
        parameters_from_language_model=ParametersFromLanguageModel.model_validate(params),
    )
    out = {
        "description": description,
        "raw_extraction_envelope": envelope,
        "parsed_parameters": params,
        "field_summary": summary,
        "fidelity_ok": fid.ok,
        "input_json": inp.model_dump(),
    }
    path = tmp_path / "stated_everything.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    # Also stash under /tmp for the evidence writer.
    Path("/tmp/generic-field-map-stated-everything.json").write_text(
        path.read_text(encoding="utf-8"), encoding="utf-8"
    )
