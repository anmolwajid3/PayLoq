"""Work order G: grounding reject (Run #17) + raw-vs-parsed mutation detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from payloq_generator.answer_key import build_answer_key
from payloq_generator.engine import generate_pack, load_input
from payloq_llm.extract_pipeline import finalize_extracted_parameters, prepare_extracted_dict
from payloq_llm.grounding import ground_stated_parameters, mark_stated_sources
from payloq_validate.checks import validate_pack

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"
FIXTURE = ROOT / "tests" / "fixtures" / "run17_raw_llm.json"


def _run17() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_run17_fixture_exists() -> None:
    assert FIXTURE.exists(), f"missing Run #17 fixture at {FIXTURE}"
    data = _run17()
    assert data["wrong_revenue_eur"] == 420_000
    assert data["expected_correct_revenue_eur"] == 4_200_000


def test_run17_grounding_rejects_wrong_revenue_scale() -> None:
    """€420k stated vs €4.2M in description → reject; errors name the field."""
    data = _run17()
    desc = f"{data['description_fi']} {data['description_en']}"
    raw = dict(data["raw_llm_parameters"])
    sources = mark_stated_sources(raw)
    result = ground_stated_parameters(raw, desc, field_sources=sources)
    assert not result.ok
    fields = {i.field for i in result.issues}
    assert "monthly_revenue_start_eur" in fields, result.issues
    err = result.error_text()
    assert "monthly_revenue_start_eur" in err
    assert "420000" in err or "420000.0" in err


def test_run17_finalize_locks_code_stated_revenue_scale() -> None:
    """
    Code-first NL parse locks €4.2M over raw LLM €420k before grounding.

    Pure grounding still rejects the uncorrected raw payload (test above);
    finalize must not keep the undercounted revenue.
    """
    data = _run17()
    desc = f"{data['description_fi']} {data['description_en']}"
    opts = data["options"]
    params, changes, grounding = finalize_extracted_parameters(
        dict(data["raw_llm_parameters"]),
        desc,
        industry=opts.get("industry"),
        company_size=opts.get("company_size"),
        seed=int(opts.get("seed") or 17),
        require_starting_cash=True,
    )
    assert grounding.ok, grounding.error_text()
    assert params["monthly_revenue_start_eur"] == pytest.approx(
        float(data["expected_correct_revenue_eur"])
    )
    assert params["monthly_revenue_start_eur"] != pytest.approx(
        float(data["wrong_revenue_eur"])
    )
    assert params["field_sources"].get("monthly_revenue_start_eur") == "stated"
    assert any(
        c.get("field") == "monthly_revenue_start_eur"
        and "nl_stated" in (c.get("source") or "")
        for c in changes
    )


def test_raw_vs_parsed_detects_revenue_scale_mutation() -> None:
    """
    Compare raw LLM JSON to values after normalize/prepare.

    If a stated revenue is rewritten (the €420k vs €4.2M class of bug), fail and
    log which step changed it.
    """
    data = _run17()
    raw = dict(data["raw_llm_parameters"])
    raw_rev = float(raw["monthly_revenue_start_eur"])
    assert raw_rev == pytest.approx(420_000.0)

    prepared, changes = prepare_extracted_dict(raw)
    prep_rev = float(prepared["monthly_revenue_start_eur"])
    mutating = [
        c
        for c in changes
        if c.get("field") == "monthly_revenue_start_eur"
        and c.get("original") is not None
        and c.get("clipped") is not None
        and abs(float(c["original"]) - float(c["clipped"])) > 1.0
    ]
    # prepare_extracted_dict must NOT silently rescale stated revenue.
    assert prep_rev == pytest.approx(raw_rev), (
        f"prepare step changed revenue {raw_rev} → {prep_rev}; changes={changes}"
    )
    assert not mutating, f"step mutated revenue: {mutating}"

    # Correct grounded value for the same description would be 4.2M — document the bug.
    correct = float(data["expected_correct_revenue_eur"])
    assert abs(raw_rev - correct) / correct > 0.5


@pytest.mark.parametrize("scenario_id", ["good", "weak", "cash_critical"])
def test_work_order_g_scenarios_validate(scenario_id: str) -> None:
    """G: good and weak pass; cash_critical passes with projection_history_scale as warning."""
    inp = load_input(SCENARIOS / scenario_id / "input.json")
    pack = generate_pack(inp, seed=42)
    key = build_answer_key(pack)
    result = validate_pack(pack, answer_key=key)
    hard = [i for i in result.issues if i.severity == "error"]
    assert not hard, hard
    assert result.ok
    # Answer key carries assumed/stated provenance + invoice totals (E).
    assert "assumed_fields" in key
    assert "invoice_totals" in key
    assert "open_sales_incl_vat_eur" in key["invoice_totals"]


def test_work_order_g_invoices_out_of_balance_fails() -> None:
    from payloq_generator.engine import break_receivables_mismatch

    inp = load_input(SCENARIOS / "invoices_out_of_balance" / "input.json")
    pack = break_receivables_mismatch(generate_pack(inp, seed=42))
    result = validate_pack(pack)
    assert not result.ok
    assert "VR-05" in result.failing_rule_ids()


def test_assumptions_xlsx_tab(tmp_path: Path) -> None:
    from openpyxl import load_workbook
    from payloq_export_xlsx.writer import write_scenario_xlsx

    inp = load_input(SCENARIOS / "good" / "input.json")
    # Mark one field assumed so the tab has content.
    inp.parameters_from_language_model.field_sources["days_sales_outstanding"] = "assumed"
    pack = generate_pack(inp, seed=42)
    path = write_scenario_xlsx(pack, tmp_path / "a.xlsx")
    wb = load_workbook(path)
    assert "Assumptions" in wb.sheetnames
    rows = list(wb["Assumptions"].iter_rows(values_only=True))
    assert rows[0][0].startswith("Kenttä") or "Field" in str(rows[0][0])
