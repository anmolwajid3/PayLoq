"""Benchmark matrix config (JSON) — stub + Ollama models, CPU-friendly defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from payloq_llm.defaults import RECOMMENDED_CPU_MODELS


@dataclass
class ModelSpec:
    """One cell in the model matrix."""

    id: str
    adapter: str = "stub"  # stub | ollama
    model: str | None = None  # Ollama tag, e.g. llama3.2:1b
    host: str | None = None
    fallback_stub: bool = True
    tier: str = "custom"  # baseline | recommended | optional | custom

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str) -> ModelSpec:
        if isinstance(data, str):
            return parse_model_token(data)
        return cls(
            id=str(data.get("id") or data.get("model") or data.get("adapter") or "stub"),
            adapter=str(data.get("adapter") or "stub"),
            model=data.get("model"),
            host=data.get("host"),
            fallback_stub=bool(data.get("fallback_stub", True)),
            tier=str(data.get("tier") or "custom"),
        )


def parse_model_token(token: str) -> ModelSpec:
    """
    Parse CLI tokens:
      stub
      ollama
      ollama:llama3.2:1b
      ollama/llama3.2:1b
      shortlist   → recommended CPU shortlist (stub + llama3.2:1b + optional)
      shortlist:recommended → stub + llama3.2:1b only
    """
    token = token.strip()
    if not token or token == "stub":
        return ModelSpec(id="stub", adapter="stub", tier="baseline")
    if token in {"shortlist", "cpu-shortlist", "shortlist:all"}:
        # Sentinel — expanded in from_cli / expand_model_tokens
        return ModelSpec(id="__shortlist__", adapter="shortlist", tier="recommended")
    if token == "shortlist:recommended":
        return ModelSpec(id="__shortlist_recommended__", adapter="shortlist", tier="recommended")
    if token == "ollama":
        return ModelSpec(
            id="ollama:llama3.2:1b",
            adapter="ollama",
            model="llama3.2:1b",
            tier="recommended",
        )
    if token.startswith("ollama:"):
        tag = token[len("ollama:") :]
        return ModelSpec(id=f"ollama:{tag}", adapter="ollama", model=tag)
    if token.startswith("ollama/"):
        tag = token[len("ollama/") :]
        return ModelSpec(id=f"ollama:{tag}", adapter="ollama", model=tag)
    # Bare Ollama tag convenience (e.g. llama3.2:1b)
    if ":" in token or token.endswith("b"):
        return ModelSpec(id=f"ollama:{token}", adapter="ollama", model=token)
    raise ValueError(
        f"Unknown model token '{token}'. Use stub, ollama, ollama:<tag>, "
        "shortlist, or a matrix config JSON."
    )


def expand_model_tokens(tokens: list[str] | list[ModelSpec]) -> list[ModelSpec]:
    """Expand shortlist sentinels into concrete ModelSpec rows."""
    out: list[ModelSpec] = []
    for token in tokens:
        if isinstance(token, ModelSpec):
            if token.adapter == "shortlist":
                include_optional = token.id != "__shortlist_recommended__"
                out.extend(cpu_shortlist_specs(include_optional=include_optional))
            else:
                out.append(token)
            continue
        spec = parse_model_token(token)
        if spec.adapter == "shortlist":
            include_optional = spec.id != "__shortlist_recommended__"
            out.extend(cpu_shortlist_specs(include_optional=include_optional))
        else:
            out.append(spec)
    # De-dupe by id, preserve order
    seen: set[str] = set()
    unique: list[ModelSpec] = []
    for m in out:
        if m.id in seen:
            continue
        seen.add(m.id)
        unique.append(m)
    return unique


def cpu_shortlist_specs(*, include_optional: bool = True) -> list[ModelSpec]:
    """Official CPU-friendly shortlist as ModelSpec list."""
    specs: list[ModelSpec] = []
    for row in RECOMMENDED_CPU_MODELS:
        tier = str(row.get("tier") or "custom")
        if not include_optional and tier == "optional":
            continue
        specs.append(ModelSpec.from_dict(row))
    return specs


@dataclass
class JudgeConfig:
    enabled: bool = False
    adapter: str = "stub"
    model: str | None = None
    host: str | None = None


@dataclass
class BenchmarkConfig:
    scenario_ids: list[str] = field(
        default_factory=lambda: ["good", "weak", "cash_critical"]
    )
    models: list[Any] = field(default_factory=lambda: [ModelSpec(id="stub", adapter="stub")])
    out_dir: Path = Path("runs/benchmark")
    scenarios_root: Path | None = None
    seed: int = 42
    hardware_note: str = "CPU-friendly local workstation"
    judge: JudgeConfig | dict[str, Any] = field(default_factory=JudgeConfig)
    write_spotcheck: bool = True
    # When True, skip ollama:* cells if the host is unreachable (stub still runs).
    skip_unavailable: bool = True
    cost_eur_per_1k_tokens: float | None = None
    interpretation_question_fi: str = (
        "Miksi kassa muuttuu ennusteessa? Käytä vain annettuja lukuja; älä keksi syitä."
    )
    interpretation_question_en: str = (
        "Why does cash change in the projection? Use only the given figures; do not invent causes."
    )

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        normalized: list[ModelSpec] = []
        for m in self.models:
            if isinstance(m, ModelSpec):
                if m.adapter == "shortlist":
                    include_optional = m.id != "__shortlist_recommended__"
                    normalized.extend(cpu_shortlist_specs(include_optional=include_optional))
                else:
                    normalized.append(m)
            elif isinstance(m, str):
                normalized.extend(expand_model_tokens([m]))
            elif isinstance(m, dict):
                normalized.append(ModelSpec.from_dict(m))
            else:
                raise TypeError(f"Unsupported model entry: {m!r}")
        # De-dupe
        seen: set[str] = set()
        unique: list[ModelSpec] = []
        for m in normalized:
            if m.id in seen:
                continue
            seen.add(m.id)
            unique.append(m)
        self.models = unique
        if isinstance(self.judge, dict):
            j = self.judge
            self.judge = JudgeConfig(
                enabled=bool(j.get("enabled", False)),
                adapter=str(j.get("adapter", "stub")),
                model=j.get("model"),
                host=j.get("host"),
            )

    @staticmethod
    def from_cli(
        *,
        models: str = "stub",
        scenarios: str = "good,weak,cash_critical",
        out: Path | str = "runs/benchmark",
        config_path: Path | str | None = None,
        judge: bool = False,
        spotcheck: bool = True,
        ollama_host: str | None = None,
        scenarios_root: Path | None = None,
        seed: int = 42,
        skip_unavailable: bool | None = None,
    ) -> BenchmarkConfig:
        if config_path:
            cfg = load_matrix_config(Path(config_path))
            cfg.out_dir = Path(out)
            if scenarios_root is not None:
                cfg.scenarios_root = scenarios_root
            cfg.seed = seed
            if judge:
                cfg.judge.enabled = True
            cfg.write_spotcheck = spotcheck
            if skip_unavailable is not None:
                cfg.skip_unavailable = skip_unavailable
            if ollama_host:
                for m in cfg.models:
                    if m.adapter == "ollama" and not m.host:
                        m.host = ollama_host
                if cfg.judge.adapter == "ollama" and not cfg.judge.host:
                    cfg.judge.host = ollama_host
            return cfg

        tokens = [m.strip() for m in models.split(",") if m.strip()]
        model_specs = expand_model_tokens(tokens)
        if ollama_host:
            for m in model_specs:
                if m.adapter == "ollama":
                    m.host = ollama_host
        return BenchmarkConfig(
            scenario_ids=[s.strip() for s in scenarios.split(",") if s.strip()],
            models=model_specs,
            out_dir=Path(out),
            scenarios_root=scenarios_root,
            seed=seed,
            judge=JudgeConfig(enabled=judge, adapter="stub" if not judge else "ollama"),
            write_spotcheck=spotcheck,
            skip_unavailable=True if skip_unavailable is None else skip_unavailable,
        )


def load_matrix_config(path: Path) -> BenchmarkConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    models = [ModelSpec.from_dict(m) for m in data.get("models", [{"id": "stub", "adapter": "stub"}])]
    judge_raw = data.get("judge") or {}
    judge = JudgeConfig(
        enabled=bool(judge_raw.get("enabled", False)),
        adapter=str(judge_raw.get("adapter", "stub")),
        model=judge_raw.get("model"),
        host=judge_raw.get("host"),
    )
    return BenchmarkConfig(
        scenario_ids=list(data.get("scenarios") or ["good", "weak", "cash_critical"]),
        models=models,
        out_dir=Path(data.get("out_dir") or "runs/benchmark"),
        seed=int(data.get("seed", 42)),
        hardware_note=str(data.get("hardware_note") or "CPU-friendly local workstation"),
        judge=judge,
        write_spotcheck=bool(data.get("write_spotcheck", True)),
        skip_unavailable=bool(data.get("skip_unavailable", True)),
        cost_eur_per_1k_tokens=data.get("cost_eur_per_1k_tokens"),
        interpretation_question_fi=str(
            data.get("interpretation_question_fi")
            or BenchmarkConfig.interpretation_question_fi
        ),
        interpretation_question_en=str(
            data.get("interpretation_question_en")
            or BenchmarkConfig.interpretation_question_en
        ),
    )


DEFAULT_MATRIX_EXAMPLE: dict[str, Any] = {
    "scenarios": ["good", "weak", "cash_critical"],
    "hardware_note": "CPU-friendly local workstation (Anmol Desktop first)",
    "seed": 42,
    "write_spotcheck": True,
    "skip_unavailable": True,
    "models": [
        {"id": "stub", "adapter": "stub", "tier": "baseline"},
        {
            "id": "ollama:llama3.2:1b",
            "adapter": "ollama",
            "model": "llama3.2:1b",
            "tier": "recommended",
            "fallback_stub": True,
        },
    ],
    "judge": {
        "enabled": False,
        "adapter": "ollama",
        "model": "llama3.2:1b",
    },
}
