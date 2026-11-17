"""Local-first LLM adapters: stub (always) + Ollama (optional, CPU-friendly)."""

from __future__ import annotations

import json
import time
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
    INTERPRETATION_SYSTEM,
    descriptive_texts_prompt,
    interpretation_prompt,
    parameter_extraction_prompt,
    parameter_repair_prompt,
)
from payloq_llm.nl_cash_intent import (
    looks_cash_critical,
    repair_params_from_nl,
    suggested_target_cash_eur,
)
from payloq_llm.stub_texts import stub_invoice_texts
from payloq_llm.text_sanitize import sanitize_invoice_texts


class LlmAdapter(ABC):
    name: str
    # Populated after each call when the adapter records metrics (Phase 3).
    last_call_metrics: dict[str, Any] | None = None
    # FR-A-12: raw model text for the last parameter-extraction call.
    last_raw_output: str | None = None

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

    def chat(self, content: str, *, json_mode: bool = False) -> str:
        """Optional free-form chat used by benchmark judge / probes. Default: interpret."""
        _ = json_mode
        return self.interpret_figures(content, {})

    def answer_numeric_probe(
        self, probe_id: str, question: str, pack_summary: dict[str, Any]
    ) -> str:
        """Answer a code-graded numeric reading probe. Default: free-text interpret."""
        _ = probe_id
        return self.interpret_figures(question, pack_summary)

class StubLlmAdapter(LlmAdapter):
    """Deterministic stand-in — CPU-only, no network. Used as default and Ollama fallback."""

    name = "stub"

    def __init__(self, preset: ParametersFromLanguageModel | None = None) -> None:
        self.preset = preset
        self.last_call_metrics: dict[str, Any] | None = None

    def _record(self, *, latency_ms: float, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.last_call_metrics = {
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "adapter": self.name,
            "model": "stub",
        }

    def extract_parameters(
        self, description_fi: str, description_en: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        if self.preset is not None:
            out = self.preset.model_dump()
            self._record(latency_ms=(time.perf_counter() - t0) * 1000, tokens_out=32)
            return out
        combined = f"{description_fi} {description_en}"
        text = combined.lower()
        sid = str(options.get("scenario_id") or "").lower()
        industry = str(options.get("industry") or "").lower()
        invest_month = 2
        factors = None
        one_offs: list[dict] = []
        rev_start = 200_000.0

        hotelish = any(
            k in text or k in industry
            for k in ("hotel", "hotelli", "boutique", "adr", "occupancy", "majoitus")
        )
        winter_collapse = any(
            k in text
            for k in (
                "winter",
                "talvi",
                "oct–mar",
                "oct-mar",
                "october",
                "collapse",
                "off-season",
                "sesongin",
            )
        )
        # Digit-heavy hotel / roof repair heuristics
        roof_repair = any(k in text for k in ("roof", "hvac", "95", "95,000", "95000", "katto"))
        cash_stressed = sid == "cash_critical" or looks_cash_critical(combined)
        nl_cash = suggested_target_cash_eur(combined)

        if cash_stressed:
            # Prefer NL covenant / winter-cash figures; never invent healthy 330k.
            cash = float(nl_cash) if nl_cash is not None else 45_000.0
            if cash > 80_000:
                cash = 45_000.0
            growth, invest, partly = 0.0, 80_000.0, True
            notes = "stub: cash_critical heuristic from NL keywords"
        elif sid == "weak" or any(
            k in text for k in ("laskee", "falling", "tappioll", "weak", "heikko")
        ):
            growth, cash, invest, partly = -0.012, 85_000.0, 70_000.0, True
            notes = "stub: weak heuristic from NL keywords"
        else:
            growth, cash, invest, partly = 0.008, 330_000.0, 0.0, False
            notes = "stub: good / default heuristic"

        if hotelish:
            rev_start = 180_000.0
            notes = f"{notes}; hotel industry defaults"
            if cash_stressed or (
                cash > 60_000
                and any(k in text for k in ("tight", "critical", "kriittinen", "covenant", "kovenantti"))
            ):
                cash = float(nl_cash) if nl_cash is not None else min(cash, 40_000.0)
                if cash > 80_000:
                    cash = 40_000.0
                invest, partly = max(invest, 95_000.0), True
        if winter_collapse or (hotelish and any(k in text for k in ("winter", "talvi", "off-season"))):
            # Jan..Dec: winter collapse Oct–Mar (indices 9,10,11,0,1,2)
            factors = [
                0.30,  # Jan
                0.30,  # Feb
                0.35,  # Mar
                0.70,  # Apr
                0.90,  # May
                1.00,  # Jun
                1.00,  # Jul
                1.00,  # Aug
                0.85,  # Sep
                0.35,  # Oct
                0.30,  # Nov
                0.30,  # Dec
            ]
            notes = f"{notes}; winter seasonality factors"
            if cash_stressed and nl_cash is not None:
                cash = float(nl_cash)
        if roof_repair or (hotelish and invest >= 80_000):
            invest = max(invest, 95_000.0)
            invest_month = 2
            one_offs.append(
                {
                    "amount_eur": invest,
                    "month_index": invest_month,
                    "direction": "out",
                    "label": "roof_repair",
                }
            )
            notes = f"{notes}; special investment month {invest_month}"
        if nl_cash is not None and cash_stressed:
            notes = f"{notes}; NL cash/covenant hint {nl_cash:,.0f}"

        params = ParametersFromLanguageModel(
            monthly_revenue_start_eur=rev_start,
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
            special_investment_month=invest_month,
            monthly_revenue_factors=factors,
            one_off_events=one_offs,
            notes=notes,
            partly_fixed_costs=partly,
        )
        out = params.model_dump()
        # Defense in depth: same repair path used after live Ollama extraction
        out, _ = repair_params_from_nl(combined, out)
        self.last_raw_output = json.dumps(out, ensure_ascii=False, indent=2)
        self._record(
            latency_ms=(time.perf_counter() - t0) * 1000,
            tokens_in=max(1, len(text) // 4),
            tokens_out=64,
        )
        return out

    def generate_invoice_texts(
        self,
        *,
        description_fi: str,
        description_en: str,
        industry: str,
        language: str = "fi",
    ) -> InvoiceDescriptiveTexts:
        t0 = time.perf_counter()
        _ = (description_fi, description_en, industry)
        texts = stub_invoice_texts(language=language)  # type: ignore[arg-type]
        texts = sanitize_invoice_texts(
            texts, description_fi=description_fi, description_en=description_en
        )
        self._record(latency_ms=(time.perf_counter() - t0) * 1000, tokens_out=48)
        return texts

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        t0 = time.perf_counter()
        cash = pack_summary.get("cash_end")
        neg = pack_summary.get("first_negative_projection_week")
        neg_date = pack_summary.get("first_negative_projection_week_end")
        neg_bal = pack_summary.get("first_negative_projection_balance")
        first_neg_date = pack_summary.get("first_negative_date") or neg_date
        first_neg_bal = pack_summary.get("first_negative_balance")
        if first_neg_bal is None:
            first_neg_bal = neg_bal
        mom = pack_summary.get("mom_revenue_change")
        mom_cash = pack_summary.get("mom_cash_change")
        hist_change = pack_summary.get("balance_history_change")
        revenue = pack_summary.get("revenue_last")
        invest = pack_summary.get("special_investment_eur")
        drops = pack_summary.get("largest_weekly_cash_drops") or []
        currency = pack_summary.get("currency") or "EUR"
        q_l = question.lower()
        is_neg_q = any(
            k in q_l
            for k in (
                "negative",
                "negatiiv",
                "milloin kassa",
                "when does cash",
                "goes negative",
            )
        )
        is_drop_q = any(k in q_l for k in ("laski", "drop", "miksi", "why", "laske"))

        # Preset-style questions: lead with figure citations, never definitions.
        fi_q = any(ch in q_l for ch in ("ä", "ö", "å")) or any(
            k in q_l for k in ("kassa", "milloin", "miksi", "negatiiv")
        )
        if is_neg_q:
            if first_neg_date is not None and first_neg_bal is not None:
                if fi_q:
                    week_bit = f" (viikko {neg})" if neg is not None else ""
                    out = (
                        f"[stub] Kassa menee ensimmäisen kerran negatiiviseksi "
                        f"{first_neg_date}{week_bit}, saldo {first_neg_bal} {currency}. "
                        f"Kauden lopun kassa on {cash} {currency}."
                    )
                else:
                    week_bit = f" (week {neg})" if neg is not None else ""
                    out = (
                        f"[stub] Cash first goes negative on {first_neg_date}{week_bit}, "
                        f"with balance {first_neg_bal} {currency}. "
                        f"Period-end cash is {cash} {currency}."
                    )
            elif "first_negative_projection_week" in pack_summary or "first_negative_date" in pack_summary:
                if fi_q:
                    out = (
                        f"[stub] Annettujen lukujen mukaan kassa ei mene negatiiviseksi. "
                        f"Kauden lopun kassa on {cash} {currency}."
                    )
                else:
                    out = (
                        f"[stub] The pack figures do not show cash going negative. "
                        f"Period-end cash is {cash} {currency}."
                    )
            else:
                out = (
                    f"[stub] No negative-cash figures were provided. "
                    f"Period-end cash is {cash} {currency}."
                )
            self._record(
                latency_ms=(time.perf_counter() - t0) * 1000,
                tokens_in=max(1, len(question) // 4),
                tokens_out=max(1, len(out) // 4),
            )
            return out

        if is_drop_q:
            lines = [
                f"[stub] Kysymys / Question: {question}",
                f"Kassasaldo kauden lopussa / Cash at period end: {cash} {currency}",
            ]
            if hist_change is not None:
                hist_from = pack_summary.get("balance_history_first_date")
                hist_to = pack_summary.get("balance_history_last_date")
                span = (
                    f" ({hist_from} → {hist_to})"
                    if hist_from and hist_to
                    else ""
                )
                lines.append(
                    f"Kassahistorian muutos{span} / Balance-history change: "
                    f"{hist_change} {currency}"
                )
            if mom_cash is not None:
                lines.append(
                    f"Kassan MoM-muutos / MoM cash change: {mom_cash} {currency}"
                )
            if invest:
                lines.append(
                    f"Erityisinvestointi (parametri) / Special investment: {invest} {currency}"
                )
            if drops:
                top = drops[0]
                lines.append(
                    "Suurin viikkomuutos historiassa / Largest weekly history move: "
                    f"{top.get('from_date')} → {top.get('to_date')}: "
                    f"{top.get('delta')} {currency}"
                )
            lines.append(
                "Huom: stub-vastaus; luvut tulevat koodista — ei määritelmiä."
            )
            out = "\n".join(lines)
            self._record(
                latency_ms=(time.perf_counter() - t0) * 1000,
                tokens_in=max(1, len(question) // 4),
                tokens_out=max(1, len(out) // 4),
            )
            return out

        lines = [
            f"[stub] Kysymys / Question: {question}",
            f"Kassasaldo kauden lopussa / Cash at period end: {cash} {currency}",
        ]
        if revenue is not None:
            lines.append(
                f"Viimeisimmän kuukauden liikevaihto / Last-month revenue: {revenue} {currency}"
            )
        if mom is not None:
            lines.append(f"Liikevaihdon MoM-muutos / MoM revenue change: {mom} {currency}")
        if mom_cash is not None:
            lines.append(f"Kassan MoM-muutos / MoM cash change: {mom_cash} {currency}")
        if hist_change is not None:
            lines.append(
                f"Kassahistorian muutos (alku→loppu) / Balance-history change: "
                f"{hist_change} {currency}"
            )
        if invest:
            lines.append(
                f"Erityisinvestointi (parametri) / Special investment: {invest} {currency}"
            )
        if neg:
            lines.append(
                "Ennuste menee negatiiviseksi viikolla / Projection turns negative in week: "
                f"{neg}"
                + (
                    f" ({neg_date}, saldo/balance {neg_bal} {currency})"
                    if neg_date is not None
                    else ""
                )
            )
        elif "first_negative_projection_week" in pack_summary and neg is None:
            lines.append(
                "Ennuste ei mene negatiiviseksi annetuilla luvuilla / Projection stays non-negative."
            )
        lines.append(
            "Huom: tämä on stub-vastaus; kielimalli ei keksi syitä — luvut tulevat koodista."
        )
        out = "\n".join(lines)
        self._record(
            latency_ms=(time.perf_counter() - t0) * 1000,
            tokens_in=max(1, len(question) // 4),
            tokens_out=max(1, len(out) // 4),
        )
        return out

    def chat(self, content: str, *, json_mode: bool = False) -> str:
        t0 = time.perf_counter()
        if json_mode and "Score ONLY" in content:
            # Deterministic judge stub for offline tests
            out = (
                '{"factual":1.0,"understandable":1.0,"no_invented_causes":1.0,'
                '"overall":1.0,"notes":"stub-judge"}'
            )
        else:
            out = f"[stub-chat] {content[:200]}"
        self._record(
            latency_ms=(time.perf_counter() - t0) * 1000,
            tokens_in=max(1, len(content) // 4),
            tokens_out=max(1, len(out) // 4),
        )
        return out

    def answer_numeric_probe(
        self, probe_id: str, question: str, pack_summary: dict[str, Any]
    ) -> str:
        t0 = time.perf_counter()
        _ = question
        key_map = {
            "cash_end": "cash_end",
            "revenue_last": "revenue_last",
            "mom_revenue_change": "mom_revenue_change",
            "first_negative_projection_week": "first_negative_projection_week",
        }
        key = key_map.get(probe_id)
        value = pack_summary.get(key) if key else None
        if value is None and probe_id == "first_negative_projection_week":
            out = '{"value": null}'
        else:
            out = json.dumps({"value": value})
        self._record(latency_ms=(time.perf_counter() - t0) * 1000, tokens_out=8)
        return out

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
        self.last_call_metrics: dict[str, Any] | None = None

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
        from payloq_generator.params_clamp import cost_shares_out_of_range

        prompt = parameter_extraction_prompt(description_fi, description_en, options)
        raw = self._chat(prompt, json_mode=True)
        self.last_raw_output = raw
        last_err: Exception | None = None
        # FR-A-11 / FR-A-13: retry invalid JSON or out-of-range cost shares up to 2 times
        max_attempts = max(self.max_retries, 2) + 1
        for attempt in range(max_attempts):
            try:
                data = extract_json_object(raw)
                params = validate_model(ParametersFromLanguageModel, data)
                shares = params.cost_shares_of_revenue.model_dump()
                if cost_shares_out_of_range(shares):
                    share_sum = sum(shares.values())
                    raise ValueError(
                        f"cost_shares_of_revenue sum to {share_sum:.4f}; "
                        "must be within ~0.9–1.0 (FR-A-11)"
                    )
                self.last_raw_output = raw
                out = params.model_dump()
                out, _ = repair_params_from_nl(
                    f"{description_fi} {description_en}", out
                )
                return out
            except (ValueError, json.JSONDecodeError) as exc:
                last_err = exc
                if attempt >= max_attempts - 1:
                    break
                raw = self._chat(parameter_repair_prompt(raw, str(exc)), json_mode=True)
                self.last_raw_output = raw
        # Accept schema-valid JSON; pipeline clamp_parameters hard-repairs + logs (FR-A-11).
        try:
            data = extract_json_object(raw)
            params = validate_model(ParametersFromLanguageModel, data)
            out = params.model_dump()
            out, _ = repair_params_from_nl(f"{description_fi} {description_en}", out)
            return out
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Ollama returned invalid parameters JSON after retries: {last_err or exc}"
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
        raw = self._chat(prompt, json_mode=True)
        try:
            data = extract_json_object(raw)
            data.setdefault("language", language)
            texts = validate_model(InvoiceDescriptiveTexts, data)
            return sanitize_invoice_texts(
                texts, description_fi=description_fi, description_en=description_en
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama returned invalid invoice texts JSON: {exc}") from exc

    def interpret_figures(self, question: str, pack_summary: dict[str, Any]) -> str:
        # Free text — do not force JSON format (models invent keys otherwise).
        return self._chat(
            interpretation_prompt(question, pack_summary),
            json_mode=False,
            system=INTERPRETATION_SYSTEM,
        )

    def chat(self, content: str, *, json_mode: bool = False) -> str:
        return self._chat(content, json_mode=json_mode)

    def answer_numeric_probe(
        self, probe_id: str, question: str, pack_summary: dict[str, Any]
    ) -> str:
        _ = probe_id
        prompt = (
            "Answer the numeric probe using ONLY Figures JSON. "
            'Return ONLY JSON like {"value": <number-or-null>}.\n\n'
            f"Figures JSON:\n{json.dumps(pack_summary, ensure_ascii=False)}\n\n"
            f"Probe:\n{question}\n"
        )
        return self._chat(prompt, json_mode=True)

    def _chat(
        self, content: str, *, json_mode: bool = True, system: str | None = None
    ) -> str:
        t0 = time.perf_counter()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        if json_mode:
            payload["format"] = "json"
        body = json.dumps(payload).encode("utf-8")
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
            self.last_call_metrics = {
                "latency_ms": (time.perf_counter() - t0) * 1000,
                "adapter": self.name,
                "model": self.model,
                "error": str(exc),
            }
            raise RuntimeError(
                f"Ollama unavailable at {self.host} (model={self.model}). "
                f"Install/start Ollama or use --llm stub. Underlying error: {exc}"
            ) from exc
        except TimeoutError as exc:
            self.last_call_metrics = {
                "latency_ms": (time.perf_counter() - t0) * 1000,
                "adapter": self.name,
                "model": self.model,
                "error": "timeout",
            }
            raise RuntimeError(
                f"Ollama timed out after {self.timeout_s}s at {self.host}."
            ) from exc

        tokens_in = data.get("prompt_eval_count")
        tokens_out = data.get("eval_count")
        self.last_call_metrics = {
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "tokens_in": int(tokens_in) if tokens_in is not None else None,
            "tokens_out": int(tokens_out) if tokens_out is not None else None,
            "adapter": self.name,
            "model": self.model,
        }
        return data.get("message", {}).get("content", "") or ""

class FallbackAdapter(LlmAdapter):
    """Try primary adapter; on failure use stub (logs reason via last_fallback_reason)."""

    name = "fallback"

    def __init__(self, primary: LlmAdapter, fallback: LlmAdapter | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or StubLlmAdapter()
        self.last_fallback_reason: str | None = None
        self.used_fallback = False
        # Sticky: extract_parameters fallback must survive later successful invoice-text calls
        # so the UI does not claim live Ollama when params actually came from stub.
        self.param_extraction_used_fallback = False
        self.param_extraction_fallback_reason: str | None = None
        self.last_call_metrics: dict[str, Any] | None = None

    def is_available(self) -> bool:
        return self.primary.is_available() or self.fallback.is_available()

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            result = getattr(self.primary, method)(*args, **kwargs)
            self.used_fallback = False
            self.last_fallback_reason = None
            if method == "extract_parameters":
                self.param_extraction_used_fallback = False
                self.param_extraction_fallback_reason = None
            self.last_call_metrics = getattr(self.primary, "last_call_metrics", None)
            self.last_raw_output = getattr(self.primary, "last_raw_output", None)
            return result
        except Exception as exc:  # noqa: BLE001 — intentional soft fallback
            reason = f"{self.primary.name} failed: {exc}"
            self.used_fallback = True
            self.last_fallback_reason = reason
            if method == "extract_parameters":
                self.param_extraction_used_fallback = True
                self.param_extraction_fallback_reason = reason
            result = getattr(self.fallback, method)(*args, **kwargs)
            self.last_call_metrics = getattr(self.fallback, "last_call_metrics", None)
            self.last_raw_output = getattr(self.fallback, "last_raw_output", None)
            return result

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

    def chat(self, content: str, *, json_mode: bool = False) -> str:
        return self._call("chat", content, json_mode=json_mode)

    def answer_numeric_probe(
        self, probe_id: str, question: str, pack_summary: dict[str, Any]
    ) -> str:
        return self._call("answer_numeric_probe", probe_id, question, pack_summary)

def list_ollama_models(host: str | None = None) -> dict[str, Any]:
    """
    Query Ollama ``GET /api/tags`` and return a normalized payload.

    Returns ``{"available": bool, "host": str, "models": [...], "error": str|None}``.
    Does not raise on connection failure — callers (API UI) can show a soft empty state.
    """
    base = (host or DEFAULT_OLLAMA_HOST).rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "host": base,
            "models": [],
            "error": str(exc),
        }

    models: list[dict[str, Any]] = []
    for row in data.get("models") or []:
        details = row.get("details") or {}
        name = row.get("name") or row.get("model")
        if not name:
            continue
        models.append(
            {
                "name": str(name),
                "size": row.get("size"),
                "modified_at": row.get("modified_at"),
                "digest": row.get("digest"),
                "parameter_size": details.get("parameter_size"),
                "family": details.get("family"),
            }
        )
    models.sort(key=lambda m: m["name"])
    return {"available": True, "host": base, "models": models, "error": None}


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
    company_size: str = "small",
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
        raise ValueError(
            "Description is missing. Please write one or two sentences."
        )

    if language == "fi":
        description_fi = text
        description_en = (description_en or text).strip()
    else:
        description_en = text
        # Mirror into FI until a dedicated --from-text-fi flag exists.
        description_fi = text

    opts = options or default_options_from_text(language=language)
    params = adapter.extract_parameters(description_fi, description_en, opts)
    # Repair absurd targets after live/stub extraction (covenant / winter cash in NL).
    repaired, _ = repair_params_from_nl(f"{description_fi} {description_en}", params)
    validated = validate_model(ParametersFromLanguageModel, repaired)

    invoice_texts: InvoiceDescriptiveTexts | None = None
    if with_invoice_texts:
        invoice_texts = sanitize_invoice_texts(
            adapter.generate_invoice_texts(
                description_fi=description_fi,
                description_en=description_en,
                industry=str(opts.get("industry", "SME")),
                language=str(opts.get("language", language)),
            ),
            description_fi=description_fi,
            description_en=description_en,
        )

    note = f"parameters via {adapter.name} adapter"
    if isinstance(adapter, FallbackAdapter) and (
        adapter.param_extraction_used_fallback or adapter.used_fallback
    ):
        reason = (
            adapter.param_extraction_fallback_reason
            or adapter.last_fallback_reason
            or "primary adapter failed"
        )
        note = f"{note}; {reason}"

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
        invoice_texts = sanitize_invoice_texts(
            adapter.generate_invoice_texts(
                description_fi=description_fi,
                description_en=description_en,
                industry=str(options.get("industry", "SME")),
                language=str(options.get("language", "fi")),
            ),
            description_fi=description_fi,
            description_en=description_en,
        )
    return GeneratorInput(
        meta=ScenarioMeta(fictional=True, note=f"parameters via {adapter.name} adapter"),
        scenario_description=ScenarioDescription(fi=description_fi, en=description_en),
        options=options,  # type: ignore[arg-type]
        parameters_from_language_model=validated,
        invoice_texts=invoice_texts,
    )
