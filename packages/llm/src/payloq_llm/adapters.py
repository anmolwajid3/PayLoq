"""Local-first LLM adapters: stub (always) + Ollama (optional, CPU-friendly)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from payloq_schemas.models import (
    GeneratorInput,
    InvoiceDescriptiveTexts,
    ParametersFromLanguageModel,
    ScenarioDescription,
    ScenarioMeta,
)

from payloq_llm.defaults import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_TIMEOUT_S,
)
from payloq_llm.parse import extract_json_object, validate_model
from payloq_llm.prompts import (
    descriptive_texts_prompt,
    interpretation_prompt,
    parameter_extraction_prompt,
    parameter_repair_prompt,
)
from payloq_llm.stub_texts import stub_invoice_texts


class LlmAdapter(ABC):
    name: str

    @abstractmethod
    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        """Map NL description → structured parameters (dict matching ParametersFromLanguageModel)."""

    @abstractmethod
    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        """LLM-authored counterparty / invoice line texts (no amounts)."""

    @abstractmethod
    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        """Interpret ready-made figures in plain language (no invented causes)."""

    def is_available(self) -> bool:
        return True


class StubLlmAdapter(LlmAdapter):
    """Deterministic stand-in — CPU-only, no network. Used as default and Ollama fallback."""

    name = "stub"

    def __init__(self, preset: ParametersFromLanguageModel | None = None) -> None:
        self.preset = preset

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        if self.preset is not None:
            return self.preset.model_dump()
        text = f"{description_fi} {description_en}".lower()
        sid = str(options.get("scenario_id") or "").lower()
        if sid == "cash_critical" or any(
            k in text for k in ("kriittinen", "critical", "negatiiv", "kolmen viikon", "three weeks")
        ):
            growth, cash, invest, partly = 0.0, 45_000.0, 80_000.0, True
            notes = "stub: cash_critical heuristic from NL keywords"
        elif sid == "weak" or any(
            k in text for k in ("laskee", "falling", "tappioll", "weak", "heikko")
        ):
            growth, cash, invest, partly = -0.012, 85_000.0, 70_000.0, True
            notes = "stub: weak heuristic from NL keywords"
        else:
            growth, cash, invest, partly = 0.008, 330_000.0, 0.0, False
            notes = "stub: good / default heuristic"
        params = ParametersFromLanguageModel(
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
            notes=notes,
            partly_fixed_costs=partly,
        )
        return params.model_dump()

    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        _ = (description_fi, description_en, industry)
        return stub_invoice_texts(language=language)  # type: ignore[arg-type]

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
    """Local Ollama HTTP client. Falls back only when callers wrap with FallbackAdapter."""

    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = 1,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = parameter_extraction_prompt(description_fi, description_en, options)
        raw = self._chat(prompt)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                data = extract_json_object(raw)
                params = validate_model(ParametersFromLanguageModel, data)
                return params.model_dump()
            except (ValueError, json.JSONDecodeError) as exc:
                last_err = exc
                if attempt >= self.max_retries:
                    break
                raw = self._chat(parameter_repair_prompt(raw, str(exc)))
        raise RuntimeError(
            f"Ollama returned invalid parameters JSON after retries: {last_err}"
        ) from last_err

    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        prompt = descriptive_texts_prompt(
            description_fi=description_fi,
            description_en=description_en,
            industry=industry,
            language=language,
        )
        raw = self._chat(prompt)
        try:
            data = extract_json_object(raw)
            data.setdefault("language", language)
            return validate_model(InvoiceDescriptiveTexts, data)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama returned invalid invoice texts JSON: {exc}") from exc

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        return self._chat(interpretation_prompt(question, pack_summary))

    def _chat(self, content: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": content}],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama unavailable at {self.host} (model={self.model}). "
                f"Install/start Ollama or use --llm stub. Underlying error: {exc}"
            ) from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Ollama timed out after {self.timeout_s}s at {self.host}."
            ) from exc
        return data.get("message", {}).get("content", "") or ""


class FallbackAdapter(LlmAdapter):
    """Try primary adapter; on failure use stub (logs reason via last_fallback_reason)."""

    name = "fallback"

    def __init__(self, primary: LlmAdapter, fallback: LlmAdapter | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or StubLlmAdapter()
        self.last_fallback_reason: str | None = None
        self.used_fallback = False

    def is_available(self) -> bool:
        return self.primary.is_available() or self.fallback.is_available()

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            result = getattr(self.primary, method)(*args, **kwargs)
            self.used_fallback = False
            self.last_fallback_reason = None
            return result
        except Exception as exc:  # noqa: BLE001 — intentional soft fallback
            self.used_fallback = True
            self.last_fallback_reason = f"{self.primary.name} failed: {exc}"
            return getattr(self.fallback, method)(*args, **kwargs)

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        return self._call("extract_parameters", description_fi, description_en, options)

    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        return self._call(
            "generate_invoice_texts",
            description_fi=description_fi,
            description_en=description_en,
            industry=industry,
            language=language,
        )

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        return self._call("interpret_figures", question, pack_summary)


def get_adapter(
    name: str = "stub",
    *,
    fallback_stub: bool = True,
    model: str | None = None,
    host: str | None = None,
    **kwargs: Any,
) -> LlmAdapter:
    """
    Resolve an adapter by name.

    - stub: always available
    - ollama: local HTTP; when fallback_stub=True, wraps with FallbackAdapter
    """
    if name == "stub":
        return StubLlmAdapter(**kwargs)
    if name == "ollama":
        ollama_kwargs = dict(kwargs)
        if model is not None:
            ollama_kwargs["model"] = model
        if host is not None:
            ollama_kwargs["host"] = host
        primary = OllamaAdapter(**ollama_kwargs)
        if fallback_stub:
            return FallbackAdapter(primary, StubLlmAdapter())
        return primary
    raise ValueError(f"Unknown LLM adapter: {name}")


def default_options_from_text(
    *,
    industry: str = "metal workshop (machine shop)",
    company_size: str = "small (revenue about 2.3 M EUR / year)",
    months: int = 12,
    language: str = "fi",
    scenario_id: str | None = None,
    as_of: str | None = "2026-10-31",
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "industry": industry,
        "company_size": company_size,
        "months": months,
        "language": language,
        "currency": "EUR",
        "as_of": as_of,
    }
    if scenario_id:
        opts["scenario_id"] = scenario_id
    return opts


def input_from_text(
    *,
    text: str,
    adapter: LlmAdapter | None = None,
    language: str = "fi",
    options: dict[str, Any] | None = None,
    with_invoice_texts: bool = True,
    description_en: str | None = None,
) -> GeneratorInput:
    """
    NL description → GeneratorInput via adapter.

    Single-language `--from-text` is accepted: FI text is primary when language=fi;
    EN mirror is filled with the same string unless description_en is provided.
    """
    adapter = adapter or StubLlmAdapter()
    text = text.strip()
    if not text:
        raise ValueError("empty --from-text description")

    if language == "fi":
        description_fi = text
        description_en = (description_en or text).strip()
    else:
        description_en = text
        # Mirror into FI until a dedicated --from-text-fi flag exists.
        description_fi = text

    opts = options or default_options_from_text(language=language)
    params = adapter.extract_parameters(description_fi, description_en, opts)
    validated = validate_model(ParametersFromLanguageModel, params)

    invoice_texts: InvoiceDescriptiveTexts | None = None
    if with_invoice_texts:
        invoice_texts = adapter.generate_invoice_texts(
            description_fi=description_fi,
            description_en=description_en,
            industry=str(opts.get("industry", "SME")),
            language=str(opts.get("language", language)),
        )

    note = f"parameters via {adapter.name} adapter"
    if isinstance(adapter, FallbackAdapter) and adapter.used_fallback:
        note = f"{note}; {adapter.last_fallback_reason}"

    return GeneratorInput(
        meta=ScenarioMeta(fictional=True, note=note),
        scenario_description=ScenarioDescription(fi=description_fi, en=description_en),
        options=opts,  # type: ignore[arg-type]
        parameters_from_language_model=validated,
        invoice_texts=invoice_texts,
    )


# Back-compat alias used by Phase 1 helper name
def input_from_descriptions(
    *,
    description_fi: str,
    description_en: str,
    options: dict[str, Any],
    adapter: LlmAdapter | None = None,
    with_invoice_texts: bool = True,
) -> GeneratorInput:
    adapter = adapter or StubLlmAdapter()
    params = adapter.extract_parameters(description_fi, description_en, options)
    validated = validate_model(ParametersFromLanguageModel, params)
    invoice_texts = None
    if with_invoice_texts:
        invoice_texts = adapter.generate_invoice_texts(
            description_fi=description_fi,
            description_en=description_en,
            industry=str(options.get("industry", "SME")),
            language=str(options.get("language", "fi")),
        )
    return GeneratorInput(
        meta=ScenarioMeta(fictional=True, note=f"parameters via {adapter.name} adapter"),
        scenario_description=ScenarioDescription(fi=description_fi, en=description_en),
        options=options,  # type: ignore[arg-type]
        parameters_from_language_model=validated,
        invoice_texts=invoice_texts,
    )
