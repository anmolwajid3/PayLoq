"""payloq generate | validate | bench"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="payloq",
    help="PayLoq research PoC — synthetic financial packs + local LLM benchmark.",
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
    from_text: Optional[str] = typer.Option(
        None,
        "--from-text",
        help="Natural-language company situation → parameters via LLM (stub or Ollama).",
    ),
    from_text_file: Optional[Path] = typer.Option(
        None,
        "--from-text-file",
        help="Read NL description from a UTF-8 text file (same as --from-text).",
    ),
    llm: str = typer.Option(
        "stub",
        "--llm",
        help="LLM adapter for --from-text: stub | ollama. Presets (--scenario) ignore this.",
    ),
    ollama_model: Optional[str] = typer.Option(
        None,
        "--ollama-model",
        help="Ollama model tag (default: llama3.2:1b).",
    ),
    ollama_host: Optional[str] = typer.Option(
        None,
        "--ollama-host",
        help="Ollama base URL (default: http://127.0.0.1:11434).",
    ),
    no_fallback_stub: bool = typer.Option(
        False,
        "--no-fallback-stub",
        help="With --llm ollama, fail instead of falling back to the stub adapter.",
    ),
    language: str = typer.Option(
        "fi",
        "--language",
        help="Primary language for --from-text (fi|en). Finnish required for PoC.",
    ),
    industry: str = typer.Option(
        "metal workshop (machine shop)",
        "--industry",
        help="Industry hint passed to the LLM with --from-text.",
    ),
    months: int = typer.Option(12, "--months", help="Months of history for --from-text (12–24)."),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory."),
    seed: int = typer.Option(42, "--seed", help="Deterministic seed."),
    xlsx: bool = typer.Option(True, "--xlsx/--no-xlsx", help="Also write Excel workbook."),
) -> None:
    """Generate a consistent JSON (+ Excel) pack from parameters or NL text."""
    from payloq_generator.engine import generate_pack, load_input, write_pack
    from payloq_llm.adapters import (
        FallbackAdapter,
        default_options_from_text,
        get_adapter,
        input_from_text,
    )
    from payloq_llm.defaults import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL
    from payloq_validate.checks import validate_pack

    sources = sum(bool(x) for x in (input, scenario, from_text, from_text_file))
    if sources != 1:
        typer.echo(
            "Provide exactly one of --input, --scenario, --from-text, or --from-text-file",
            err=True,
        )
        raise typer.Exit(2)

    fallback_note: str | None = None

    if scenario:
        # Built-in presets: hand-authored params — no LLM required.
        scenario_path = _repo_root() / "scenarios" / scenario / "input.json"
        if not scenario_path.exists():
            scenario_path = Path("scenarios") / scenario / "input.json"
        if not scenario_path.exists():
            typer.echo(f"Unknown scenario '{scenario}' (expected {scenario_path})", err=True)
            raise typer.Exit(2)
        inp = load_input(scenario_path)
        if inp.options.scenario_id is None:
            inp.options.scenario_id = scenario
    elif input is not None:
        inp = load_input(input)
    else:
        text = from_text
        if from_text_file is not None:
            text = from_text_file.read_text(encoding="utf-8")
        assert text is not None

        if language not in {"fi", "en"}:
            typer.echo("--language must be fi or en", err=True)
            raise typer.Exit(2)
        if months < 12 or months > 24:
            typer.echo("--months must be between 12 and 24", err=True)
            raise typer.Exit(2)

        adapter = get_adapter(
            llm,
            fallback_stub=not no_fallback_stub,
            model=ollama_model or DEFAULT_OLLAMA_MODEL,
            host=ollama_host or DEFAULT_OLLAMA_HOST,
        )
        opts = default_options_from_text(
            industry=industry,
            months=months,
            language=language,
        )
        try:
            inp = input_from_text(
                text=text,
                adapter=adapter,
                language=language,
                options=opts,
                with_invoice_texts=True,
            )
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"LLM parameter extraction failed: {exc}", err=True)
            raise typer.Exit(1) from exc

        if isinstance(adapter, FallbackAdapter) and adapter.used_fallback:
            fallback_note = adapter.last_fallback_reason
            typer.echo(f"Warning: fell back to stub LLM ({fallback_note})", err=True)

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
    if fallback_note:
        typer.echo(f"LLM: stub fallback ({fallback_note})")
    elif from_text or from_text_file:
        typer.echo(f"LLM: {llm}")
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
    models: str = typer.Option(
        "stub",
        "--models",
        help="Comma-separated model tokens: stub, ollama, ollama:llama3.2:1b, …",
    ),
    scenarios: str = typer.Option(
        "good,weak,cash_critical", "--scenarios", help="Comma-separated scenario ids."
    ),
    out: Path = typer.Option(Path("runs/benchmark"), "--out", "-o"),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Matrix JSON (see benchmarks/matrix.example.json). Overrides --models/--scenarios.",
    ),
    judge: bool = typer.Option(
        False,
        "--judge/--no-judge",
        help="Optional LLM judge on interpretation answers (synthetic data only).",
    ),
    spotcheck: bool = typer.Option(
        True,
        "--spotcheck/--no-spotcheck",
        help="Write human spot-check CSV template under --out.",
    ),
    ollama_host: Optional[str] = typer.Option(
        None,
        "--ollama-host",
        help="Ollama base URL for ollama:* models (default http://127.0.0.1:11434).",
    ),
    seed: int = typer.Option(42, "--seed", help="Generator seed for figure packs."),
) -> None:
    """Run Phase 3 model-matrix benchmark (graders + SQLite metrics under runs/)."""
    from payloq_benchmark.config import BenchmarkConfig
    from payloq_benchmark.runner import run_benchmark

    root = _repo_root()
    cfg = BenchmarkConfig.from_cli(
        models=models,
        scenarios=scenarios,
        out=out,
        config_path=config,
        judge=judge,
        spotcheck=spotcheck,
        ollama_host=ollama_host,
        scenarios_root=root,
        seed=seed,
    )
    result = run_benchmark(cfg, scenarios_root=root)
    scorecard = out / "scorecard.json"
    typer.echo(
        f"Benchmark batch {result.batch_id}: {result.summary['n_runs']} runs → {out.resolve()}"
    )
    typer.echo(f"  results:   {out / 'results.json'}")
    typer.echo(f"  sqlite:    {out / 'metrics.sqlite'}")
    typer.echo(f"  scorecard: {scorecard}")
    if spotcheck:
        typer.echo(f"  spotcheck: {out / 'spotcheck.csv'}")
    for row in result.summary.get("by_model") or []:
        typer.echo(
            "  {model}: param={avg_parameter:.3f} read={avg_reading:.3f} "
            "mom={avg_mom:.3f} interp={avg_interpretation:.3f} "
            "latency_ms={avg_latency_ms:.1f}".format(
                model=row["model"],
                avg_parameter=row["avg_parameter"] or 0.0,
                avg_reading=row["avg_reading"] or 0.0,
                avg_mom=row["avg_mom"] or 0.0,
                avg_interpretation=row["avg_interpretation"] or 0.0,
                avg_latency_ms=row["avg_latency_ms"] or 0.0,
            )
        )


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
