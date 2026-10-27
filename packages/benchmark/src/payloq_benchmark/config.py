"""Benchmark matrix config (JSON) — stub + Ollama models, CPU-friendly defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelSpec:
    """One cell in the model matrix."""

    id: str
    adapter: str = "stub"  # stub | ollama
    model: str | None = None  # Ollama tag, e.g. llama3.2:1b
    host: str | None = None
    fallback_stub: bool = True

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
        )


def parse_model_token(token: str) -> ModelSpec:
    """
    Parse CLI tokens:
      stub
      ollama
      ollama:llama3.2:1b
      ollama/llama3.2:1b
    """
    token = token.strip()
    if not token or token == "stub":
        return ModelSpec(id="stub", adapter="stub")
    if token == "ollama":
        return ModelSpec(id="ollama:llama3.2:1b", adapter="ollama", model="llama3.2:1b")
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
        f"Unknown model token '{token}'. Use stub, ollama, ollama:<tag>, or a matrix config JSON."
    )


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
                normalized.append(m)
            elif isinstance(m, str):
                normalized.append(parse_model_token(m))
            elif isinstance(m, dict):
                normalized.append(ModelSpec.from_dict(m))
            else:
                raise TypeError(f"Unsupported model entry: {m!r}")
        self.models = normalized
        if isinstance(self.judge, dict):
            j = self.judge
            self.judge = JudgeConfig(
                enabled=bool(j.get("enabled", False)),
                adapter=str(j.get("adapter", "stub")),
                model=j.get("model"),
                host=j.get("host"),
            )

    # Back-compat: allow list[str] assignment via factory helpers
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
            if ollama_host:
                for m in cfg.models:
                    if m.adapter == "ollama" and not m.host:
                        m.host = ollama_host
                if cfg.judge.adapter == "ollama" and not cfg.judge.host:
                    cfg.judge.host = ollama_host
            return cfg

        model_specs = [parse_model_token(m) for m in models.split(",") if m.strip()]
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
    "models": [
        {"id": "stub", "adapter": "stub"},
        {
            "id": "ollama:llama3.2:1b",
            "adapter": "ollama",
            "model": "llama3.2:1b",
            "fallback_stub": True,
        },
    ],
    "judge": {
        "enabled": False,
        "adapter": "ollama",
        "model": "llama3.2:1b",
    },
}
