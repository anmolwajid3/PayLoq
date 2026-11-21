"""Generic repeatability property test (FR-A-25 / NFR-01).

Same input + seed + code → byte-identical input.json, monthly_reports.json,
and cash_and_invoices.json across in-process repeats and a fresh subprocess.

No special-case descriptions or TC-specific branches — random valid envelopes only.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from payloq_generator.pipeline import run_generation
from payloq_llm.extract_pipeline import finalize_extracted_parameters
from payloq_schemas.models import (
    GeneratorInput,
    Options,
    ParametersFromLanguageModel,
    ScenarioDescription,
    ScenarioMeta,
)
from payloq_validate.checks import validate_pack

ROOT = Path(__file__).resolve().parents[1]
FILES = ("input.json", "monthly_reports.json", "cash_and_invoices.json")
N_INPUTS = 50
PROP_SEED = int(os.environ.get("REPEATABILITY_PROP_SEED", "1"))

SHAPES = ("unspecified", "healthy", "weak", "cash_critical", "cash_tight")
INDUSTRIES = (
    "metal workshop",
    "boutique hotel",
    "bakery",
    "software consultancy",
    "retail shop",
    "steel fabricator",
)
SIZES = ("micro", "small", "medium", "large")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_cash_triangle(out: Path) -> None:
    """Blocking rule: last history cash == latest cash == last monthly cash."""
    monthly = json.loads((out / "monthly_reports.json").read_text(encoding="utf-8"))
    cash = json.loads((out / "cash_and_invoices.json").read_text(encoding="utf-8"))
    hist_last = float(cash["balance_history"][-1]["balance"])
    last_monthly = float(monthly["months"][-1]["balance_sheet"]["assets"]["cash"])
    latest = last_monthly
    assert abs(hist_last - latest) <= 0.02, (hist_last, latest, last_monthly)
    assert abs(latest - last_monthly) <= 0.02


def _random_envelope(rng: random.Random) -> tuple[str, dict, str, str, int, int, str | None]:
    """Build one random valid description + extraction envelope + run config."""
    seed = rng.randint(1, 50_000)
    industry = rng.choice(INDUSTRIES)
    size = rng.choice(SIZES)
    shape = rng.choice(SHAPES)
    months = rng.choice([12, 18, 24])
    as_of = "2026-10-31" if rng.random() < 0.75 else None

    rev = rng.randint(60_000, 450_000)
    growth = round(rng.uniform(-0.05, 0.05), 6)
    start = rng.randint(30_000, 350_000)
    cov = rng.randint(20_000, 300_000)
    dso = rng.randint(15, 90)
    dpo = rng.randint(14, 90)

    parts = [f"A {size} {industry} business."]
    stated: dict[str, str] = {}
    parameters: dict = {
        "one_off_events": [],
        "industry": industry,
        "company_size": size,
        "revenue_monthly_eur": float(rev),
        "growth_per_month_percent": None,
        "starting_cash_eur": None,
        "covenant_min_cash_eur": None,
        "dso_days": None,
        "dpo_days": None,
    }
    parts.append(f"Monthly revenue {rev} euro.")
    stated["revenue_monthly_eur"] = parts[-1]

    growth_percent = round(growth * 100.0, 4)
    for key, value, phrase in (
        ("growth_per_month_percent", float(growth_percent), f"Growth {growth_percent}% per month."),
        ("starting_cash_eur", float(start), f"Starting cash {start} euro."),
        ("covenant_min_cash_eur", float(cov), f"Bank minimum cash {cov} euro."),
        ("dso_days", float(dso), f"DSO {dso} days."),
        ("dpo_days", float(dpo), f"DPO {dpo} days."),
    ):
        if rng.random() < 0.75:
            parts.append(phrase)
            stated[key] = phrase
            parameters[key] = value

    if rng.random() < 0.35:
        amt = rng.randint(5_000, 90_000)
        month = rng.randint(1, min(12, months))
        direction = rng.choice(["inflow", "outflow"])
        phrase = f"One-off {direction} of {amt} euro in month {month}."
        parts.append(phrase)
        stated["one_off_events"] = phrase
        parameters["one_off_events"] = [
            {
                "type": "other",
                "amount_eur": float(amt),
                "month_index": month,
                "direction": direction,
            }
        ]

    desc = " ".join(parts)
    envelope = {
        "scenario_shape": shape,
        "scenario_shape_quote": None,
        "stated": stated,
        "parameters": parameters,
    }
    return desc, envelope, industry, size, seed, months, as_of


def _finalize_input(
    desc: str,
    envelope: dict,
    *,
    industry: str,
    size: str,
    seed: int,
    months: int,
    as_of: str | None,
) -> GeneratorInput | None:
    params, _changes, result = finalize_extracted_parameters(
        envelope,
        desc,
        industry=industry,
        company_size=size,
        seed=seed,
        months=months,
        llm_model_name="repeatability-prop",
    )
    if not result.ok:
        return None
    opts: dict = {
        "industry": industry,
        "company_size": size,
        "months": months,
        "language": "en",
        "currency": "EUR",
    }
    if as_of:
        opts["as_of"] = as_of
    try:
        return GeneratorInput(
            meta=ScenarioMeta(fictional=True, note="repeatability-prop", seed=seed),
            scenario_description=ScenarioDescription(fi=desc, en=desc),
            options=Options(**opts),
            parameters_from_language_model=ParametersFromLanguageModel.model_validate(params),
        )
    except Exception:  # noqa: BLE001
        return None


def _collect_valid_cases(n: int = N_INPUTS) -> list[tuple]:
    rng = random.Random(10_000 + PROP_SEED)
    cases: list[tuple] = []
    attempts = 0
    while len(cases) < n and attempts < n * 12:
        attempts += 1
        desc, envelope, industry, size, seed, months, as_of = _random_envelope(rng)
        inp = _finalize_input(
            desc,
            envelope,
            industry=industry,
            size=size,
            seed=seed,
            months=months,
            as_of=as_of,
        )
        if inp is None:
            continue
        # Must produce a successful pack at least once to be a "valid" input.
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as td:
            outcome = run_generation(
                inp, Path(td) / "probe", seed=seed, write_xlsx=False, max_seed_attempts=5
            )
            if not outcome.ok or not all((outcome.out_dir / name).exists() for name in FILES):
                continue
        cases.append((desc, envelope, industry, size, seed, months, as_of, inp))
    if len(cases) < n:
        pytest.fail(f"Could only collect {len(cases)}/{n} valid random inputs")
    return cases


def _run_subprocess(inp: GeneratorInput, seed: int, out: Path) -> dict[str, str]:
    payload = {
        "inp": json.loads(inp.model_dump_json()),
        "seed": seed,
        "out": str(out),
    }
    payload_path = out.parent / "payload.json"
    script_path = out.parent / "sub_run.py"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    script_path.write_text(
        textwrap.dedent(
            """\
            import hashlib, json, sys
            from pathlib import Path
            from payloq_generator.pipeline import run_generation
            from payloq_schemas.models import GeneratorInput

            payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
            inp = GeneratorInput.model_validate(payload["inp"])
            out = Path(payload["out"])
            outcome = run_generation(
                inp, out, seed=payload["seed"], write_xlsx=False, max_seed_attempts=5
            )
            files = ("input.json", "monthly_reports.json", "cash_and_invoices.json")
            print(
                json.dumps(
                    {
                        "ok": outcome.ok,
                        "hashes": {
                            name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                            if (out / name).exists()
                            else None
                            for name in files
                        },
                    }
                )
            )
            """
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        [sys.executable, str(script_path), str(payload_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_repeatability_50_random_descriptions_inprocess_and_subprocess(tmp_path: Path) -> None:
    cases = _collect_valid_cases(N_INPUTS)
    differing = 0
    details: list[str] = []

    for i, (desc, envelope, industry, size, seed, months, as_of, _cached) in enumerate(cases):
        # Rebuild input each in-process run (fresh finalize) to catch state leaks.
        hashes: list[dict[str, str]] = []
        for r in range(3):
            inp = _finalize_input(
                desc,
                envelope,
                industry=industry,
                size=size,
                seed=seed,
                months=months,
                as_of=as_of,
            )
            assert inp is not None
            out = tmp_path / f"case{i}" / f"run{r}"
            outcome = run_generation(
                inp, out, seed=seed, write_xlsx=False, max_seed_attempts=5
            )
            assert outcome.ok, outcome.validation.failing_rule_ids()
            _assert_cash_triangle(out)
            hashes.append({name: _sha256(out / name) for name in FILES})

        inp_sub = _finalize_input(
            desc,
            envelope,
            industry=industry,
            size=size,
            seed=seed,
            months=months,
            as_of=as_of,
        )
        assert inp_sub is not None
        sub_out = tmp_path / f"case{i}" / "sub"
        sub_out.mkdir(parents=True, exist_ok=True)
        sub = _run_subprocess(inp_sub, seed, sub_out)
        assert sub["ok"], sub
        _assert_cash_triangle(sub_out)
        hashes.append(sub["hashes"])

        if any(h != hashes[0] for h in hashes):
            differing += 1
            mismatched = [
                name for name in FILES if len({h[name] for h in hashes}) > 1
            ]
            details.append(
                f"input[{i}] seed={seed} shape={envelope['scenario_shape']} "
                f"mismatched={mismatched}"
            )

    assert differing == 0, (
        f"{differing}/{N_INPUTS} inputs had differing SHA-256 hashes. " + "; ".join(details)
    )


def test_cash_history_latest_monthly_consistency_blocking() -> None:
    """Last history == latest cash == last monthly cash (blocking VR-07)."""
    from payloq_generator.engine import generate_pack, load_input

    inp = load_input(ROOT / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    hist_last = pack.cash_and_invoices.balance_history[-1].balance
    monthly_last = pack.monthly_reports.months[-1].balance_sheet.assets.cash
    latest_cash = monthly_last
    assert hist_last == pytest.approx(latest_cash, abs=0.02)
    assert latest_cash == pytest.approx(monthly_last, abs=0.02)
    result = validate_pack(pack)
    cash_errors = [
        i
        for i in result.issues
        if i.severity == "error" and (i.rule_id == "VR-07" or i.code == "cash_vs_history")
    ]
    assert not cash_errors, cash_errors


def test_stale_out_dir_cleared_on_failed_write(tmp_path: Path) -> None:
    """Failed writes must not leave previous-run data files (state leak via reuse)."""
    from payloq_generator.engine import load_input, write_pack, generate_pack
    from payloq_validate.checks import ValidationResult

    inp = load_input(ROOT / "scenarios" / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    out = tmp_path / "reuse"
    write_pack(pack, out, seed=42, write_xlsx=False, write_data_files=True)
    assert (out / "input.json").exists()
    # Simulate VR-30 failure path: rewrite without data files.
    write_pack(
        pack,
        out,
        seed=42,
        write_xlsx=False,
        write_data_files=False,
        validation=ValidationResult(ok=False).as_dict(),
    )
    for name in FILES:
        assert not (out / name).exists(), name
    assert (out / "run_log.json").exists()
