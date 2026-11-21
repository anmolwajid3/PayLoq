"""Automated harness. `pytest tests/harness -q` is the default (fixture) tier."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.caches import assert_registry_complete, cache_labels
from harness.report import add
from harness.runner import run_cell_in, run_check_g
from harness.scenarios import SCENARIO_ORDER, SEEDS, load_templates


@pytest.fixture(scope="session")
def templates() -> dict:
    return load_templates()


def test_module_level_caches_are_listed() -> None:
    assert_registry_complete()
    labels = cache_labels()
    assert labels == [
        "apps/api/src/payloq_api/config.py:53 get_settings",
        "apps/api/src/payloq_api/db.py:11 _engine",
        "packages/schemas/src/payloq_schemas/field_map.py:60 load_field_map",
    ]


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("scenario", SCENARIO_ORDER)
def test_scenario_seed(
    scenario: str,
    seed: int,
    tmp_path: Path,
    templates: dict,
    live: bool,
) -> None:
    cell = run_cell_in(tmp_path, scenario, seed, live=live, templates=templates)
    add(cell)
    if cell.failures:
        detail = "\n".join(
            f"{item.check}: expected [{item.expected}] actual [{item.actual}] file [{item.file}]"
            for item in cell.failures
        )
        pytest.fail(detail)


def test_stub_and_ollama_unreachable(tmp_path: Path) -> None:
    cells = run_check_g(tmp_path)
    lines: list[str] = []
    for cell in cells:
        add(cell)
        for item in cell.failures:
            lines.append(
                f"{cell.scenario}: expected [{item.expected}] actual [{item.actual}] file [{item.file}]"
            )
    if lines:
        pytest.fail("\n".join(lines))
