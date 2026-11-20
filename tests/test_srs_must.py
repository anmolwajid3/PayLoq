"""Lock SRS MUST behaviours for Task A (outputs, VR, scenarios, DR)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from payloq_generator.answer_key import build_answer_key
from payloq_generator.engine import generate_pack, load_input, write_pack
from payloq_generator.params_clamp import clamp_parameters
from payloq_generator.pipeline import run_generation
from payloq_llm.adapters import input_from_text
from payloq_schemas.models import ParametersFromLanguageModel
from payloq_validate.checks import validate_pack

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"

SRS_OUTPUTS = (
    "input.json",
    "monthly_reports.json",
    "cash_and_invoices.json",
    "scenario.xlsx",
    "answer_key.json",
    "run_log.json",
)


@pytest.mark.parametrize(
    "scenario_id",
    ["good", "weak", "cash_critical", "cash_turning_critical_later"],
)
def test_srs_output_folder_and_validation(tmp_path: Path, scenario_id: str) -> None:
    inp = load_input(SCENARIOS / scenario_id / "input.json")
    outcome = run_generation(inp, tmp_path / scenario_id, seed=42)
    assert outcome.ok, outcome.validation.issues
    out = outcome.out_dir
    for name in SRS_OUTPUTS:
        assert (out / name).exists(), name
    assert (out / "run_log.json").exists()
    run_log = json.loads((out / "run_log.json").read_text(encoding="utf-8"))
    assert run_log["seed"] == outcome.seed_used
    assert run_log["software_version"]
    assert run_log["validation_result"] == "all checks PASS"
    key = json.loads((out / "answer_key.json").read_text(encoding="utf-8"))
    assert "parameters" in key and "key_findings" in key
    assert "questions" in key and "forbidden_claims" in key
    # DR-02: money has cents representation in JSON (float)
    cash = json.loads((out / "cash_and_invoices.json").read_text(encoding="utf-8"))
    inv0 = cash["open_invoices"][0]
    assert "amount_net_eur" in inv0 and "vat_eur" in inv0
    assert cash["balance_history"][0]["week"] == 1


def test_repeatability_hash(tmp_path: Path) -> None:
    inp = load_input(SCENARIOS / "good" / "input.json")
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert run_generation(inp, a, seed=42).ok
    assert run_generation(inp, b, seed=42).ok
    for name in ("monthly_reports.json", "cash_and_invoices.json", "answer_key.json"):
        ha = hashlib.sha256((a / name).read_bytes()).hexdigest()
        hb = hashlib.sha256((b / name).read_bytes()).hexdigest()
        assert ha == hb, name


def test_cash_critical_week_near_3() -> None:
    inp = load_input(SCENARIOS / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    neg = [w.week for w in pack.cash_and_invoices.projection_from_open_invoices if w.projected_balance < 0]
    assert neg and min(neg) <= 4


def test_cash_turning_critical_later_history_week_20() -> None:
    inp = load_input(SCENARIOS / "cash_turning_critical_later" / "input.json")
    pack = generate_pack(inp, seed=42)
    neg = [p.week for p in pack.cash_and_invoices.balance_history if p.balance < 0]
    assert neg, "expected negative cash in history"
    assert abs(min(neg) - 20) <= 2


def test_invoices_out_of_balance_vr05(tmp_path: Path) -> None:
    inp = load_input(SCENARIOS / "invoices_out_of_balance" / "input.json")
    outcome = run_generation(inp, tmp_path / "broken", seed=42)
    assert outcome.ok  # purpose achieved
    assert outcome.test_only_broken
    assert "VR-05" in outcome.validation.failing_rule_ids()
    run_log = json.loads((outcome.out_dir / "run_log.json").read_text(encoding="utf-8"))
    assert run_log["test_only_broken"] is True
    assert (outcome.out_dir / "input.json").exists()


def test_vr_rules_on_good_pack() -> None:
    inp = load_input(SCENARIOS / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    key = build_answer_key(pack)
    result = validate_pack(pack, answer_key=key)
    errors = [i for i in result.issues if i.severity == "error"]
    assert not errors, errors
    assert all(i.rule_id for i in result.issues) or result.ok


def test_param_clamp_logs_change() -> None:
    params = ParametersFromLanguageModel(
        monthly_revenue_start_eur=5_000_000,
        monthly_revenue_growth=0.40,
        cost_shares_of_revenue={
            "materials": 0.3,
            "services": 0.1,
            "personnel": 0.3,
            "other": 0.2,
        },
        days_sales_outstanding=200,
        days_payables_outstanding=5,
        target_cash_at_end_eur=100_000,
    )
    clamped, changes = clamp_parameters(params)
    assert clamped.monthly_revenue_growth == 0.05
    assert clamped.days_sales_outstanding == 90
    assert clamped.days_payables_outstanding == 14
    assert any(c["field"] == "monthly_revenue_growth" for c in changes)


def test_empty_description_message() -> None:
    from payloq_llm.adapters import OllamaAdapter

    with pytest.raises(ValueError, match="Description is missing"):
        input_from_text(text="   ", adapter=OllamaAdapter())


def test_finnish_from_text_rejects_stub() -> None:
    from payloq_llm.adapters import StubLlmAdapter

    with pytest.raises(ValueError, match="stub"):
        input_from_text(
            text="Kone on pieni, käteinen rahavirta on tiukka ja kriittinen kolmen viikon päästä.",
            adapter=StubLlmAdapter(),
            language="fi",
        )


def test_money_two_decimals() -> None:
    inp = load_input(SCENARIOS / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    for inv in pack.cash_and_invoices.open_invoices:
        assert inv.amount_net_eur is not None and inv.vat_eur is not None
        assert round(inv.amount_incl_vat, 2) == inv.amount_incl_vat
        assert abs(inv.amount_incl_vat - (inv.amount_net_eur + inv.vat_eur)) <= 0.02


def test_write_pack_legacy_xlsx_alias(tmp_path: Path) -> None:
    inp = load_input(SCENARIOS / "weak" / "input.json")
    pack = generate_pack(inp, seed=42)
    result = validate_pack(pack, answer_key=build_answer_key(pack))
    write_pack(pack, tmp_path / "w", seed=42, validation=result.as_dict())
    assert (tmp_path / "w" / "scenario.xlsx").exists()
    assert (tmp_path / "w" / "scenario_weak.xlsx").exists()
