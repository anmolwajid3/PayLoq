"""End-to-end: generate three scenarios and assert validators + behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from payloq_export_xlsx.writer import write_scenario_xlsx
from payloq_generator.engine import generate_pack, load_input, write_pack
from payloq_validate.checks import validate_pack, validate_pack_dir

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"


@pytest.mark.parametrize("scenario_id", ["good", "weak", "cash_critical"])
def test_generate_and_validate(tmp_path: Path, scenario_id: str) -> None:
    inp = load_input(SCENARIOS / scenario_id / "input.json")
    pack = generate_pack(inp, seed=42)
    result = validate_pack(pack)
    errors = [i for i in result.issues if i.severity == "error"]
    assert not errors, errors

    out = tmp_path / scenario_id
    write_pack(pack, out, write_xlsx=True)
    assert (out / "input.json").exists()
    assert (out / "monthly_reports.json").exists()
    assert (out / "cash_and_invoices.json").exists()
    assert (out / f"scenario_{scenario_id}.xlsx").exists()

    disk = validate_pack_dir(out)
    assert disk.ok, disk.issues


def test_cash_critical_goes_negative_near_week_3() -> None:
    inp = load_input(SCENARIOS / "cash_critical" / "input.json")
    pack = generate_pack(inp, seed=42)
    proj = pack.cash_and_invoices.projection_from_open_invoices
    neg = [w.week for w in proj if w.projected_balance < 0]
    assert neg, "expected near-term negative cash"
    assert min(neg) <= 4
    # Overall profitability
    assert sum(m.income_statement.net_result for m in pack.monthly_reports.months) > 0


def test_good_stays_non_negative() -> None:
    inp = load_input(SCENARIOS / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    assert all(w.projected_balance >= 0 for w in pack.cash_and_invoices.projection_from_open_invoices)
    assert sum(m.income_statement.net_result for m in pack.monthly_reports.months) > 0


def test_weak_loses_and_shrinks_cash() -> None:
    inp = load_input(SCENARIOS / "weak" / "input.json")
    pack = generate_pack(inp, seed=42)
    months = pack.monthly_reports.months
    assert sum(m.income_statement.net_result for m in months) < 0
    assert months[-1].balance_sheet.assets.cash < months[0].balance_sheet.assets.cash


def test_xlsx_writer(tmp_path: Path) -> None:
    inp = load_input(SCENARIOS / "good" / "input.json")
    pack = generate_pack(inp)
    path = write_scenario_xlsx(pack, tmp_path / "t.xlsx")
    assert path.exists() and path.stat().st_size > 0


def test_fi_en_descriptions_present() -> None:
    for sid in ("good", "weak", "cash_critical"):
        inp = load_input(SCENARIOS / sid / "input.json")
        assert inp.scenario_description.fi.strip()
        assert inp.scenario_description.en.strip()
