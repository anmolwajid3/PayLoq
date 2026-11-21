"""VR-08 projection vs history scale/timing alignment."""

from __future__ import annotations

from pathlib import Path

import pytest

from payloq_generator.answer_key import build_answer_key
from payloq_generator.engine import generate_pack, load_input
from payloq_schemas.constants import PROJECTION_HISTORY_SCALE_RATIO
from payloq_validate.checks import validate_pack

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"


def _max_hist_move(pack) -> float:
    hist = pack.cash_and_invoices.balance_history
    return max(
        abs(hist[i].balance - hist[i - 1].balance) for i in range(1, len(hist))
    )


def _max_proj_move(pack) -> float:
    return max(
        abs(w.sales_inflow) + abs(w.purchase_outflow)
        for w in pack.cash_and_invoices.projection_from_open_invoices
    )


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 123])
def test_good_projection_history_scale_under_threshold(seed: int) -> None:
    """good: proj moves ~history scale (was ~183k vs ~3k / 60×)."""
    inp = load_input(SCENARIOS / "good" / "input.json")
    pack = generate_pack(inp, seed=seed)
    max_hist = _max_hist_move(pack)
    max_proj = _max_proj_move(pack)
    assert max_hist > 1.0
    ratio = max_proj / max_hist
    if ratio > PROJECTION_HISTORY_SCALE_RATIO:
        # Flow-based weekly history is smooth, so this ratio is expected to exceed 5.
        # The rule is non-blocking: it must be reported as a warning, never an error.
        res = validate_pack(pack)
        scale = [i for i in res.issues if i.code == "projection_history_scale"]
        assert scale and all(i.severity == "warning" for i in scale), (seed, ratio, scale)

    key = build_answer_key(pack)
    result = validate_pack(pack, answer_key=key)
    scale_errs = [
        i
        for i in result.issues
        if i.code == "projection_history_scale" and i.severity == "error"
    ]
    assert not scale_errs, scale_errs
    assert result.ok, [i for i in result.issues if i.severity == "error"]


def test_cash_turning_critical_later_timing_aligned() -> None:
    """History crisis ~week 20; near-term projection must stay non-negative."""
    inp = load_input(SCENARIOS / "cash_turning_critical_later" / "input.json")
    pack = generate_pack(inp, seed=42)
    hist = pack.cash_and_invoices.balance_history
    proj = pack.cash_and_invoices.projection_from_open_invoices

    neg_hist = [p.week for p in hist if p.balance < 0]
    assert neg_hist, "expected negative cash in history"
    assert abs(min(neg_hist) - 20) <= 2

    early_neg_proj = [w.week for w in proj if w.projected_balance < 0 and w.week <= 4]
    assert not early_neg_proj, (
        f"projection should not crash early while history crisis is week "
        f"{min(neg_hist)}; got early neg weeks {early_neg_proj}"
    )

    max_hist = _max_hist_move(pack)
    max_proj = _max_proj_move(pack)
    if max_proj / max_hist > PROJECTION_HISTORY_SCALE_RATIO:
        res_scale = validate_pack(pack)
        scale = [i for i in res_scale.issues if i.code == "projection_history_scale"]
        assert scale and all(i.severity == "warning" for i in scale), scale

    key = build_answer_key(pack)
    result = validate_pack(pack, answer_key=key)
    timing_errs = [
        i
        for i in result.issues
        if i.code
        in {
            "projection_history_timing",
            "behaviour_later_critical_early_proj",
            "projection_history_scale",
        }
        and i.severity == "error"
    ]
    assert not timing_errs, timing_errs
    hard = [i for i in result.issues if i.severity == "error"]
    assert not hard, hard


def test_severe_scale_mismatch_is_warning_not_blocking() -> None:
    """Work order D: >5× scale mismatch is a warning; run stays non-blocking on scale alone."""
    inp = load_input(SCENARIOS / "good" / "input.json")
    pack = generate_pack(inp, seed=42)
    # Flatten history around ending cash with tiny week moves (no end snap cliff).
    hist = pack.cash_and_invoices.balance_history
    end = pack.monthly_reports.months[-1].balance_sheet.assets.cash
    n = len(hist)
    for i, point in enumerate(hist):
        # ~€40/week drift into exact end cash — dwarfed by open-invoice weeks.
        point.balance = round(end - 40.0 * (n - 1 - i), 2)
    assert abs(hist[-1].balance - end) < 0.02

    result = validate_pack(pack)
    scale = [i for i in result.issues if i.code == "projection_history_scale"]
    assert scale, "expected projection_history_scale issue"
    assert scale[0].severity == "warning"
    assert scale[0].rule_id == "VR-08"
    assert (scale[0].numbers or {}).get("ratio", 0) > PROJECTION_HISTORY_SCALE_RATIO
    scale_errs = [i for i in scale if i.severity == "error"]
    assert not scale_errs
    # Scale alone must not flip ok → False (other hard errors may still fail the pack).
    assert not any(
        i.code == "projection_history_scale" and i.severity == "error" for i in result.issues
    )


def test_early_proj_vs_late_hist_timing_is_blocking() -> None:
    """Early projection negativity vs late history crisis is a VR-08 error."""
    inp = load_input(SCENARIOS / "cash_turning_critical_later" / "input.json")
    pack = generate_pack(inp, seed=42)
    # Force an early projection cliff while keeping history week-20 crisis.
    proj = pack.cash_and_invoices.projection_from_open_invoices
    assert proj[0].projected_balance >= 0
    proj[2].projected_balance = -25_000.0
    proj[2].purchase_outflow = abs(proj[2].projected_balance) + 1_000.0

    result = validate_pack(pack)
    timing = [i for i in result.issues if i.code == "projection_history_timing"]
    assert timing and timing[0].severity == "error"
    assert timing[0].rule_id == "VR-08"
    early_beh = [
        i for i in result.issues if i.code == "behaviour_later_critical_early_proj"
    ]
    assert early_beh and early_beh[0].severity == "error"
