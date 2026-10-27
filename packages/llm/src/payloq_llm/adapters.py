"""Local-first LLM adapters. Phase 1 ships stubs; Ollama is optional."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from payloq_schemas.models import GeneratorInput, ParametersFromLanguageModel


class LlmAdapter(ABC):
    name: str

    @abstractmethod
    def extract_parameters(self, description_fi: str, description_en: str, options: dict[str, Any]) -> dict[str, Any]:
        """Map NL description → structured parameters (dict matching ParametersFromLanguageModel)."""

    @abstractmethod
    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        """Interpret ready-made figures in plain language (no invented causes)."""


class StubLlmAdapter(LlmAdapter):
    """Deterministic stand-in until real local models are wired (Phase 2/3)."""

    name = "stub"

    def __init__(self, preset: ParametersFromLanguageModel | None = None) -> None:
        self.preset = preset

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        if self.preset is not None:
            return self.preset.model_dump()
        # Heuristic stub from keywords — CPU-only, no network
        text = f"{description_fi} {description_en}".lower()
        if "kriittinen" in text or "critical" in text or "negatiiv" in text:
            growth, cash, invest = 0.0, 45_000.0, 80_000.0
            partly = True
        elif "laskee" in text or "falling" in text or "tappioll" in text or "weak" in text:
            growth, cash, invest = -0.012, 85_000.0, 70_000.0
            partly = True
        else:
            growth, cash, invest = 0.008, 330_000.0, 0.0
            partly = False
        return ParametersFromLanguageModel(
            monthly_revenue_start_eur=200_000.0,
            monthly_revenue_growth=growth,
            cost_shares_of_revenue={
                "materials": 0.37,
                "services": 0.08,
                "personnel": 0.34,
                "other": 0.15,
            },
            days_sales_outstanding=40.0,
            days_payables_outstanding=32.0,
            target_cash_at_end_eur=cash,
            special_investment_eur=invest,
            notes="stub adapter — replace with real local model in Phase 2",
            partly_fixed_costs=partly,
        ).model_dump()

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        cash = pack_summary.get("cash_end")
        neg = pack_summary.get("first_negative_projection_week")
        lines = [
            f"[stub] Kysymys / Question: {question}",
            f"Kassasaldo kauden lopussa / Cash at period end: {cash}",
        ]
        if neg:
            lines.append(
                f"Ennuste menee negatiiviseksi viikolla / Projection turns negative in week: {neg}"
            )
        lines.append(
            "Huom: tämä on stub-vastaus; kielimalli ei keksi syitä — luvut tulevat koodista."
        )
        return "\n".join(lines)


class OllamaAdapter(LlmAdapter):
    """Optional local Ollama client. Not required for Phase 1 generation."""

    name = "ollama"

    def __init__(self, model: str = "llama3.2", host: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = {
            "role": "user",
            "content": (
                "Extract PayLoq generator parameters as JSON. "
                f"FI: {description_fi}\nEN: {description_en}\nOptions: {json.dumps(options)}"
            ),
        }
        raw = self._chat(prompt["content"])
        return json.loads(raw)

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        return self._chat(
            "Answer using only the provided figures; do not invent causes.\n"
            f"Figures: {json.dumps(pack_summary)}\nQuestion: {question}"
        )

    def _chat(self, content: str) -> str:
        try:
            import urllib.request

            body = json.dumps(
                {"model": self.model, "messages": [{"role": "user", "content": content}], "stream": False}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "")
        except Exception as exc:  # noqa: BLE001 — optional dependency path
            raise RuntimeError(
                f"Ollama unavailable at {self.host} (optional for Phase 1). "
                f"Use --llm stub. Underlying error: {exc}"
            ) from exc


def get_adapter(name: str = "stub", **kwargs: Any) -> LlmAdapter:
    if name == "stub":
        return StubLlmAdapter(**kwargs)
    if name == "ollama":
        return OllamaAdapter(**kwargs)
    raise ValueError(f"Unknown LLM adapter: {name}")


def input_from_descriptions(
    *,
    description_fi: str,
    description_en: str,
    options: dict[str, Any],
    adapter: LlmAdapter | None = None,
) -> GeneratorInput:
    """Helper for Phase 2: NL → GeneratorInput via adapter (stub by default)."""
    adapter = adapter or StubLlmAdapter()
    params = adapter.extract_parameters(description_fi, description_en, options)
    return GeneratorInput.model_validate(
        {
            "meta": {"fictional": True, "note": f"parameters via {adapter.name} adapter"},
            "scenario_description": {"fi": description_fi, "en": description_en},
            "options": options,
            "parameters_from_language_model": params,
        }
    )
