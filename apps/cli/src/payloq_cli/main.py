"""payloq generate | validate | bench"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="payloq",
    help="PayLoq research PoC — synthetic financial packs + local LLM benchmark scaffold.",
    no_args_is_help=True,
)


def _repo_root() -> Path:
    """Locate repo root (directory containing scenarios/)."""
    here = Path(__file__).resolve()
    for candidate in [Path.cwd(), *here.parents]:
        if (candidate / "scenarios").is_dir() and (candidate / "pyproject.toml").exists():
            return candidate
    # Editable checkout: apps/cli/src/payloq_cli/main.py → parents[4]
    return here.parents[4]


@app.command()
def generate(
    input: Optional[Path] = typer.Option(
        None, "--input", "-i", help="Path to input.json (parameters + description)."
    ),
    scenario: Optional[str] = typer.Option(
        None, "--scenario", "-s", help="Built-in scenario id: good | weak | cash_critical."
    ),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory."),
    seed: int = typer.Option(42, "--seed", help="Deterministic seed."),
    xlsx: bool = typer.Option(True, "--xlsx/--no-xlsx", help="Also write Excel workbook."),
) -> None:
    """Generate a consistent JSON (+ Excel) pack from parameters."""
    from payloq_generator.engine import generate_pack, load_input, write_pack
    from payloq_schemas.models import GeneratorInput
    from payloq_validate.checks import validate_pack

    if not input and not scenario:
        typer.echo("Provide --input or --scenario", err=True)
        raise typer.Exit(2)

    if scenario:
        scenario_path = _repo_root() / "scenarios" / scenario / "input.json"
        if not scenario_path.exists():
            # fallback: cwd-relative
            scenario_path = Path("scenarios") / scenario / "input.json"
        if not scenario_path.exists():
            typer.echo(f"Unknown scenario '{scenario}' (expected {scenario_path})", err=True)
            raise typer.Exit(2)
        inp = load_input(scenario_path)
        if inp.options.scenario_id is None:
            inp.options.scenario_id = scenario
    else:
        assert input is not None
        inp = load_input(input)

    pack = generate_pack(inp, seed=seed)
    write_pack(pack, out, write_xlsx=xlsx)
    result = validate_pack(pack)
    if not result.ok:
        typer.echo("Generated pack failed validation:", err=True)
        for issue in result.issues:
            typer.echo(f"  [{issue.severity}] {issue.code}: {issue.message}", err=True)
        raise typer.Exit(1)

    warnings = [i for i in result.issues if i.severity == "warning"]
    typer.echo(f"Wrote pack to {out.resolve()}")
    if warnings:
        typer.echo(f"{len(warnings)} warning(s):")
        for w in warnings:
            typer.echo(f"  {w.code}: {w.message}")
    else:
        typer.echo("Validators: OK")


@app.command()
def validate(
    path: Path = typer.Argument(..., help="Directory containing input.json + monthly + cash JSON."),
) -> None:
    """Run consistency validators on an existing pack directory."""
    from payloq_validate.checks import validate_pack_dir

    result = validate_pack_dir(path)
    for issue in result.issues:
        typer.echo(f"[{issue.severity}] {issue.code}: {issue.message}")
    if not result.ok:
        raise typer.Exit(1)
    typer.echo("OK")


@app.command("bench")
def bench(
    models: str = typer.Option("stub", "--models", help="Comma-separated model/adapter ids."),
    scenarios: str = typer.Option(
        "good,weak,cash_critical", "--scenarios", help="Comma-separated scenario ids."
    ),
    out: Path = typer.Option(Path("runs/benchmark"), "--out", "-o"),
) -> None:
    """Run benchmark scaffold (Phase 3 structure; stub adapters by default)."""
    from payloq_benchmark.runner import BenchmarkConfig, run_benchmark_stub

    config = BenchmarkConfig(
        scenario_ids=[s.strip() for s in scenarios.split(",") if s.strip()],
        models=[m.strip() for m in models.split(",") if m.strip()],
        out_dir=out,
    )
    # Load parameter keys from scenario inputs when present
    keys: dict = {}
    root = _repo_root()
    for sid in config.scenario_ids:
        p = root / "scenarios" / sid / "input.json"
        if not p.exists():
            p = Path("scenarios") / sid / "input.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            keys[sid] = data.get("parameters_from_language_model", {})

    result = run_benchmark_stub(config, parameter_keys=keys)
    typer.echo(f"Benchmark scaffold wrote {out / 'results.json'} ({result.summary['n_runs']} runs)")


@app.command("list-scenarios")
def list_scenarios() -> None:
    """List built-in scenario folders."""
    root = _repo_root() / "scenarios"
    if not root.exists():
        root = Path("scenarios")
    for p in sorted(root.iterdir()):
        if p.is_dir() and (p / "input.json").exists():
            typer.echo(p.name)


if __name__ == "__main__":
    app()
