"""Session report: scenario × seed table, then the failure list."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from harness.caches import known_sites
from harness.runner import CellResult
from harness.scenarios import SCENARIO_ORDER, SEEDS

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = REPO_ROOT / "reports" / "harness_report.md"
REPORT_JSON = REPO_ROOT / "reports" / "harness_report.json"
STORE_DOCS = Path("/cursor/stores/bc-73e99589-5a86-4a9d-a243-46f08a6d17fd/docs")
LIVE_JSON = REPO_ROOT / "reports" / "harness_live.json"

# Extra rows for check G (not seed-specific; recorded once).
G_ORDER: tuple[str, ...] = ("stub", "ollama-unreachable")

CELLS: list[CellResult] = []
TIER = "fixture"
TERMINAL_TEXT = ""


def add(cell: CellResult) -> None:
    CELLS.append(cell)


def _index() -> dict[tuple[str, int], CellResult]:
    return {(cell.scenario, cell.seed): cell for cell in CELLS}


def _rows() -> list[str]:
    return list(SCENARIO_ORDER) + list(G_ORDER)


def _label(index: dict[tuple[str, int], CellResult], scenario: str, seed: int) -> str:
    cell = index.get((scenario, seed))
    if cell is None:
        return "—"
    return cell.label


def table_lines() -> list[str]:
    index = _index()
    header = "| scenario | " + " | ".join(str(seed) for seed in SEEDS) + " |"
    rule = "| --- | " + " | ".join("---" for _ in SEEDS) + " |"
    lines = [header, rule]
    for scenario in _rows():
        cells = " | ".join(_label(index, scenario, seed) for seed in SEEDS)
        lines.append(f"| {scenario} | {cells} |")
    return lines


def failure_blocks() -> list[str]:
    lines: list[str] = []
    ordered = sorted(
        CELLS,
        key=lambda cell: (
            _rows().index(cell.scenario) if cell.scenario in _rows() else 99,
            cell.seed,
        ),
    )
    any_fail = False
    for cell in ordered:
        for item in cell.failures:
            any_fail = True
            lines.append(f"### {cell.scenario} / seed {cell.seed} / {item.check}")
            lines.append(f"- expected: {item.expected}")
            lines.append(f"- actual: {item.actual}")
            lines.append(f"- file: {item.file}")
            lines.append("")
    if not any_fail:
        lines.append("No failures.")
        lines.append("")
    return lines


def cache_lines() -> list[str]:
    lines = ["## Module-level caches", ""]
    for site in known_sites():
        lines.append(f"- `{site.file}:{site.line}` {site.name}")
    lines.append("")
    return lines


def render_markdown() -> str:
    parts = [
        "# Harness report",
        "",
        f"Tier: {TIER}. Command: `pytest tests/harness -q`"
        + (" --live" if TIER == "live" else "")
        + ".",
        "",
        (
            "Each cell is PASS or the failed check name. Checks: status, consistency, "
            "fidelity, sensitivity, repeatability, seed isolation, stub, ollama-unreachable."
        ),
        "",
        *table_lines(),
        "",
        "## Failures",
        "",
        *failure_blocks(),
        *cache_lines(),
    ]
    return "\n".join(parts).rstrip() + "\n"


def render_terminal() -> str:
    parts = [
        *table_lines(),
        "",
        "Failures",
        "",
        *failure_blocks(),
    ]
    return "\n".join(parts).rstrip() + "\n"


def _failure_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for cell in sorted(
        CELLS,
        key=lambda item: (
            _rows().index(item.scenario) if item.scenario in _rows() else 99,
            item.seed,
        ),
    ):
        for item in cell.failures:
            records.append(item.as_dict(scenario=cell.scenario, seed=cell.seed))
    return records


def render_json() -> dict[str, Any]:
    index = _index()
    table: dict[str, dict[str, str]] = {}
    for scenario in _rows():
        table[scenario] = {str(seed): _label(index, scenario, seed) for seed in SEEDS}
    passed = sum(1 for cell in CELLS if not cell.failures)
    return {
        "tier": TIER,
        "command": "pytest tests/harness -q" + (" --live" if TIER == "live" else ""),
        "seeds": list(SEEDS),
        "caches": [site.as_dict() for site in known_sites()],
        "table": table,
        "failures": _failure_records(),
        "summary": {
            "cells": len(CELLS),
            "passed": passed,
            "failed": len(CELLS) - passed,
        },
    }


def write_reports() -> str:
    global TERMINAL_TEXT
    markdown = render_markdown()
    payload = render_json()
    TERMINAL_TEXT = render_terminal()
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(markdown, encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    STORE_DOCS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPORT_MD, STORE_DOCS / "harness_report.md")
    shutil.copy2(REPORT_JSON, STORE_DOCS / "harness_report.json")
    if TIER == "live":
        live_rows = [
            {
                "scenario": cell.scenario,
                "seed": cell.seed,
                "model": cell.model,
                "raw_json": cell.raw_json,
            }
            for cell in CELLS
            if cell.scenario not in G_ORDER
        ]
        LIVE_JSON.write_text(
            json.dumps(live_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        shutil.copy2(LIVE_JSON, STORE_DOCS / "harness_live.json")
    return TERMINAL_TEXT


def reset() -> None:
    CELLS.clear()
