"""Local-first LLM adapters: stub (always) + Ollama (optional, CPU-friendly)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from payloq_schemas.company_size import scale_defaults_for_size
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
    resolve_ollama_timeout_s,
)
from payloq_llm.parse import extract_json_object, validate_model
from payloq_llm.prompts import (
    INTERPRETATION_SYSTEM,
    descriptive_texts_prompt,
    interpretation_prompt,
    parameter_extraction_prompt,
    parameter_grounding_repair_prompt,
    parameter_repair_prompt,
)
from payloq_llm.nl_cash_intent import (
    looks_cash_critical,
    repair_params_from_nl,
    suggested_target_cash_eur,
)
from payloq_llm.nl_param_hints import (
    extract_growth_rate,
    extract_special_investment,
    extract_starting_cash_eur,
    looks_bakery,
    looks_steel_or_manufacturing,
    repair_investment_and_revenue_from_nl,
    suggest_revenue_start_eur,
)
from payloq_llm.params_coerce import coerce_parameters_dict
from payloq_llm.invoice_text_defaults import default_invoice_texts
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
        company_size = str(options.get("company_size") or "").lower()
        size_scale = scale_defaults_for_size(str(options.get("company_size") or "small"))
        band = str(size_scale["band"])
        cash_mult = float(size_scale["cash_mult"])
        invest_mult = float(size_scale["invest_mult"])
        invest_month = 2
        factors = None
        one_offs: list[dict] = []
        rev_start = float(size_scale["monthly_revenue_start_eur"])

        hotelish = any(
            k in text or k in industry
            for k in ("hotel", "hotelli", "boutique", "adr", "occupancy", "majoitus")
        )
        bakeryish = looks_bakery(combined, industry)
        steelish = looks_steel_or_manufacturing(combined, industry)
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
                "soft in winter",
                "heikko talvi",
            )
        )
        # Digit-heavy hotel / roof repair heuristics
        roof_repair = any(k in text for k in ("roof", "hvac", "95,000", "95000", "katto"))
        cash_stressed = sid == "cash_critical" or looks_cash_critical(combined)
        nl_cash = suggested_target_cash_eur(combined)
        nl_invest = extract_special_investment(combined)
        nl_rev = suggest_revenue_start_eur(
            combined, industry=industry, company_size=company_size
        )
        nl_growth = extract_growth_rate(combined)
        # Track whether cash/invest came from explicit NL (do not re-scale those).
        cash_from_nl = False
        invest_from_nl = False

        if cash_stressed:
            # Prefer NL covenant / winter trough / cash figures; never invent healthy 330k.
            if nl_cash is not None:
                cash = float(nl_cash)
                cash_from_nl = True
            else:
                cash = 45_000.0
            # Crush only invented SME-healthy defaults — keep mid-market millions.
            if not cash_from_nl and cash > 80_000 and band == "small":
                cash = 45_000.0
            # Do not invent €80k capex when NL states a different one-off (or none).
            if nl_invest is not None:
                invest = float(nl_invest[0])
                invest_from_nl = True
            else:
                invest = 0.0
            growth, partly = 0.0, True
            notes = "stub: cash_critical heuristic from NL keywords"
        elif sid == "weak" or any(
            k in text for k in ("laskee", "falling", "tappioll", "weak", "heikko")
        ):
            growth, cash, partly = -0.012, 85_000.0, True
            if nl_invest is not None:
                invest = float(nl_invest[0])
                invest_from_nl = True
            else:
                invest = 70_000.0
            notes = "stub: weak heuristic from NL keywords"
        else:
            growth, cash, invest, partly = 0.008, 330_000.0, 0.0, False
            if nl_invest is not None:
                invest = float(nl_invest[0])
                invest_from_nl = True
            notes = "stub: good / default heuristic"

        if nl_growth is not None:
            growth = float(nl_growth)
        if nl_rev is not None:
            rev_start = float(nl_rev)
        if bakeryish:
            if nl_rev is None:
                rev_start = 32_000.0 * (
                    0.85 if "small" in company_size or "pieni" in text else 1.0
                )
                rev_start = max(20_000.0, round(rev_start, -3))
            notes = f"{notes}; bakery industry defaults"
        if steelish and not bakeryish and not hotelish:
            notes = f"{notes}; steel/manufacturing industry defaults"
        if hotelish:
            if nl_rev is None:
                # Keep hotel base relative to the company-size band (not fixed SME).
                rev_start = max(40_000.0, float(size_scale["monthly_revenue_start_eur"]) * 0.9)
                if hotelish and band == "small":
                    rev_start = max(rev_start, 180_000.0)
            notes = f"{notes}; hotel industry defaults"
            if cash_stressed or (
                cash > 60_000
                and any(k in text for k in ("tight", "critical", "kriittinen", "covenant", "kovenantti"))
            ):
                if nl_cash is not None:
                    cash = float(nl_cash)
                    cash_from_nl = True
                else:
                    cash = min(cash, 40_000.0)
                # SME hotel thin-cash only — do not crush mid-market covenant figures.
                if not cash_from_nl and cash > 80_000 and band == "small":
                    cash = 40_000.0
                if nl_invest is None and not invest_from_nl:
                    invest = max(invest, 95_000.0)
                partly = True
        if winter_collapse or (hotelish and any(k in text for k in ("winter", "talvi", "off-season"))):
            # Jan..Dec: winter collapse Oct–Mar (indices 9,10,11,0,1,2)
            if bakeryish and not hotelish:
                # Milder winter dip for retail bakery vs hotel occupancy collapse
                factors = [
                    0.70,  # Jan
                    0.70,  # Feb
                    0.80,  # Mar
                    0.90,  # Apr
                    1.00,  # May
                    1.05,  # Jun
                    1.05,  # Jul
                    1.00,  # Aug
                    0.95,  # Sep
                    0.80,  # Oct
                    0.70,  # Nov
                    0.85,  # Dec (holiday lift)
                ]
            else:
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
                cash_from_nl = True
        if nl_invest is not None:
            invest = float(nl_invest[0])
            invest_month = int(nl_invest[1])
            invest_from_nl = True
            # Word-boundary: "oven" must not match inside "covenant".
            ovenish = bakeryish or bool(re.search(r"(?<![a-z])(oven|uuni)\b", text))
            label = "oven_repair" if ovenish else (
                "roof_repair" if roof_repair or hotelish else (
                    "capex_line" if steelish else "special_investment"
                )
            )
            one_offs.append(
                {
                    "type": "capex",
                    "amount_eur": invest,
                    "month_index": invest_month,
                    "direction": "outflow",
                    "label": label,
                }
            )
            notes = f"{notes}; special investment month {invest_month}"
        elif roof_repair or (hotelish and invest >= 80_000):
            invest = max(invest, 95_000.0)
            invest_month = 2
            one_offs.append(
                {
                    "type": "capex",
                    "amount_eur": invest,
                    "month_index": invest_month,
                    "direction": "outflow",
                    "label": "roof_repair",
                }
            )
            notes = f"{notes}; special investment month {invest_month}"
        if nl_cash is not None and cash_stressed:
            notes = f"{notes}; NL cash/covenant hint {nl_cash:,.0f}"

        # Scale only invented keyword baselines — never multiply explicit NL millions.
        if not cash_from_nl:
            cash = round(cash * cash_mult, 2)
        if not invest_from_nl:
            invest = round(invest * invest_mult, 2)
            if one_offs:
                for event in one_offs:
                    event["amount_eur"] = invest
        else:
            # Keep one-off event amount aligned with the NL figure (no size mult).
            if one_offs:
                for event in one_offs:
                    event["amount_eur"] = invest
        if band != "small":
            notes = f"{notes}; company_size band={band}"

        # Opening cash: prefer explicit Starting cash / alkukassa; never invent when absent.
        nl_starting = extract_starting_cash_eur(combined)
        if nl_starting is not None:
            starting_cash = float(nl_starting)
            starting_from_nl = True
        elif nl_cash is not None:
            # Soft fallback for stub demos only (covenant/trough scale) — not invention of
            # a labeled starting-cash figure when the NL never stated one.
            starting_cash = float(nl_cash)
            starting_from_nl = False
        else:
            starting_cash = round(cash * 1.15, 2)
            starting_from_nl = False
        if starting_cash <= 0:
            starting_cash = max(cash, 1.0)

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
            covenant_min_cash_eur=cash,
            starting_cash_eur=starting_cash,
            special_investment_eur=invest,
            special_investment_month=invest_month,
            monthly_revenue_factors=factors,
            one_off_events=one_offs,
            notes=notes,
            partly_fixed_costs=partly,
            field_sources={
                "monthly_revenue_start_eur": "stated" if nl_rev is not None else "assumed",
                "monthly_revenue_growth": "stated" if nl_growth is not None else "assumed",
                "target_cash_at_end_eur": "stated" if cash_from_nl else "assumed",
                "starting_cash_eur": "stated" if starting_from_nl else "assumed",
                "special_investment_eur": "stated" if invest_from_nl else "assumed",
                "days_sales_outstanding": "assumed",
                "days_payables_outstanding": "assumed",
                "cost_shares_of_revenue": "assumed",
            },
        )
        out = params.model_dump()
        # Defense in depth: same repair path used after live Ollama extraction
        out, _ = repair_params_from_nl(combined, out)
        out, _ = repair_investment_and_revenue_from_nl(
            combined, out, industry=industry, company_size=company_size
        )
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
        texts = default_invoice_texts(language=language)  # type: ignore[arg-type]
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
        timeout_s: float | None = None,
        max_retries: int = 1,
        http_timeout_retries: int = 1,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_s = resolve_ollama_timeout_s(timeout_s)
        self.max_retries = max_retries
        # Extra HTTP attempts after a timeout (1 = one retry → 2 total tries).
        self.http_timeout_retries = max(0, int(http_timeout_retries))
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
        from payloq_generator.consistency import require_consistent
        from payloq_llm.extract_pipeline import finalize_extracted_parameters
        from payloq_llm.extraction_schema import extraction_format_schema

        prompt = parameter_extraction_prompt(description_fi, description_en, options)
        seed = int(options.get("seed") or 42)
        format_schema = extraction_format_schema()
        raw = self._chat(
            prompt,
            json_mode=True,
            format_schema=format_schema,
            seed=seed,
        )
        self.last_raw_output = raw
        last_err: Exception | None = None
        combined = f"{description_fi} {description_en}"
        industry = str(options.get("industry") or "")
        company_size = str(options.get("company_size") or "")
        months = int(options.get("months") or 12)
        # Pilot fix A/C: 1 initial + 2 retries (= 3 model calls) then error — never stub.
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                data = extract_json_object(raw)
                out, _changes, stated_check = finalize_extracted_parameters(
                    data,
                    combined,
                    industry=industry,
                    company_size=company_size,
                    seed=seed,
                    months=months,
                    require_starting_cash=False,
                    llm_model_name=self.model,
                )
                if not stated_check.ok:
                    raise ValueError(stated_check.error_text())
                require_consistent(out)
                self.last_raw_output = raw
                return out
            except (ValueError, json.JSONDecodeError) as exc:
                last_err = exc
                if attempt >= max_attempts - 1:
                    break
                raw = self._chat(
                    parameter_repair_prompt(raw, str(exc)),
                    json_mode=True,
                    format_schema=format_schema,
                    seed=seed,
                )
                self.last_raw_output = raw
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
        self,
        content: str,
        *,
        json_mode: bool = True,
        system: str | None = None,
        format_schema: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> str:
        t0 = time.perf_counter()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        options: dict[str, Any] = {"temperature": 0}
        if seed is not None:
            options["seed"] = int(seed)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if format_schema is not None:
            payload["format"] = format_schema
        elif json_mode:
            payload["format"] = "json"
        body = json.dumps(payload).encode("utf-8")
        attempts = 1 + self.http_timeout_retries
        last_timeout: BaseException | None = None
        for attempt in range(attempts):
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except TimeoutError as exc:
                last_timeout = exc
                if attempt + 1 < attempts:
                    continue
                self.last_call_metrics = {
                    "latency_ms": (time.perf_counter() - t0) * 1000,
                    "adapter": self.name,
                    "model": self.model,
                    "error": "timeout",
                }
                raise RuntimeError(
                    f"Ollama timed out after {self.timeout_s}s at {self.host}."
                ) from exc
            except urllib.error.URLError as exc:
                if _is_timeout_urlerror(exc):
                    last_timeout = exc
                    if attempt + 1 < attempts:
                        continue
                    self.last_call_metrics = {
                        "latency_ms": (time.perf_counter() - t0) * 1000,
                        "adapter": self.name,
                        "model": self.model,
                        "error": "timeout",
                    }
                    raise RuntimeError(
                        f"Ollama timed out after {self.timeout_s}s at {self.host}."
                    ) from exc
                self.last_call_metrics = {
                    "latency_ms": (time.perf_counter() - t0) * 1000,
                    "adapter": self.name,
                    "model": self.model,
                    "error": str(exc),
                }
                raise RuntimeError(
                    f"Ollama unavailable at {self.host} (model={self.model}). "
                    f"Install/start Ollama and pull the configured model. "
                    f"Underlying error: {exc}"
                ) from exc
            else:
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

        # Unreachable: loop either returns or raises; keep type-checkers happy.
        raise RuntimeError(
            f"Ollama timed out after {self.timeout_s}s at {self.host}."
        ) from last_timeout


def _is_timeout_urlerror(exc: urllib.error.URLError) -> bool:
    """urllib usually wraps socket/TimeoutError inside URLError.reason."""
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    text = f"{reason!s} {exc!s}".lower()
    return "timed out" in text or "timeout" in text

class FallbackAdapter(LlmAdapter):
    """Try primary; on extract failure prefer hybrid/code-nl, else stub.

    Sticky param-extraction flags survive later successful invoice-text calls so the
    UI does not claim live Ollama when params came from code-nl or stub.
    """

    name = "fallback"

    def __init__(self, primary: LlmAdapter, fallback: LlmAdapter | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or StubLlmAdapter()
        self.last_fallback_reason: str | None = None
        self.used_fallback = False
        # Sticky: extract_parameters fallback must survive later successful invoice-text calls
        # so the UI does not claim live Ollama when params actually came from stub/code-nl.
        self.param_extraction_used_fallback = False
        self.param_extraction_fallback_reason: str | None = None
        # "hybrid_code_nl" | "stub" | None — honest sticky labeling for generate UI.
        self.param_extraction_mode: str | None = None
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
                self.param_extraction_mode = None
            self.last_call_metrics = getattr(self.primary, "last_call_metrics", None)
            self.last_raw_output = getattr(self.primary, "last_raw_output", None)
            return result
        except Exception as exc:  # noqa: BLE001 — intentional soft fallback
            reason = f"{self.primary.name} failed: {exc}"
            self.used_fallback = True
            self.last_fallback_reason = reason
            if method == "extract_parameters":
                recovered = self._try_hybrid_code_nl(
                    description_fi=args[0] if args else kwargs.get("description_fi", ""),
                    description_en=args[1] if len(args) > 1 else kwargs.get("description_en", ""),
                    options=args[2] if len(args) > 2 else kwargs.get("options") or {},
                    primary_error=exc,
                )
                if recovered is not None:
                    return recovered
                self.param_extraction_used_fallback = True
                self.param_extraction_fallback_reason = reason
                self.param_extraction_mode = "stub"
            result = getattr(self.fallback, method)(*args, **kwargs)
            self.last_call_metrics = getattr(self.fallback, "last_call_metrics", None)
            self.last_raw_output = getattr(self.fallback, "last_raw_output", None)
            return result

    def _try_hybrid_code_nl(
        self,
        *,
        description_fi: str,
        description_en: str,
        options: dict[str, Any],
        primary_error: BaseException,
    ) -> dict[str, Any] | None:
        """Recover from total Ollama JSON failure via code-stated ∪ assumed defaults."""
        from payloq_llm.nl_stated import build_hybrid_params_from_nl

        combined = f"{description_fi or ''} {description_en or ''}".strip()
        if not combined:
            return None
        try:
            params, _changes = build_hybrid_params_from_nl(
                combined,
                industry=str(options.get("industry") or "") or None,
                company_size=str(options.get("company_size") or "") or None,
                seed=int(options.get("seed") or 42),
                require_starting_cash=True,
            )
        except Exception:  # noqa: BLE001 — fall through to stub heuristics
            return None
        reason = (
            f"{self.primary.name} failed: {primary_error}; "
            "recovered via hybrid/code-nl (stated NL parse + assumed defaults)"
        )
        self.used_fallback = True
        self.last_fallback_reason = reason
        self.param_extraction_used_fallback = True
        self.param_extraction_fallback_reason = reason
        self.param_extraction_mode = "hybrid_code_nl"
        # Strip internal marker before callers validate ParametersFromLanguageModel.
        mode = params.pop("_extraction_mode", "hybrid_code_nl")
        self.last_raw_output = json.dumps(
            {**params, "_extraction_mode": mode}, ensure_ascii=False, indent=2
        )
        self.last_call_metrics = {
            "latency_ms": 0.0,
            "adapter": "hybrid_code_nl",
            "model": "code-nl",
            "tokens_in": max(1, len(combined) // 4),
            "tokens_out": 64,
        }
        return params

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
    name: str = "ollama",
    *,
    fallback_stub: bool = False,
    model: str | None = None,
    host: str | None = None,
    **kwargs: Any,
) -> LlmAdapter:
    """
    Resolve an adapter by name.

    - ollama: local HTTP only for Task A generate (no stub fallback by default)
    - stub: Task B / fixtures only — not used by the generator pipeline

    Ollama-only kwargs (``timeout_s``, ``max_retries``, ``http_timeout_retries``)
    are ignored for the stub so API/chat can pass a shared options bag.
    """
    ollama_only = {"timeout_s", "max_retries", "http_timeout_retries"}
    if name == "stub":
        stub_kwargs = {k: v for k, v in kwargs.items() if k not in ollama_only}
        if "preset" in stub_kwargs:
            return StubLlmAdapter(preset=stub_kwargs["preset"])
        return StubLlmAdapter()
    if name == "ollama":
        ollama_kwargs = dict(kwargs)
        if model is not None:
            ollama_kwargs["model"] = model
        if host is not None:
            ollama_kwargs["host"] = host
        primary = OllamaAdapter(**ollama_kwargs)
        # Pilot fix A/G: never wrap generate path with stub fallback.
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
    seed: int = 42,
) -> dict[str, Any]:
    # One seed must drive every draw: assumed cost shares, starting cash, target
    # cash, and the generator. Callers must pass the run seed here.
    opts: dict[str, Any] = {
        "seed": int(seed),
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
    if adapter is None:
        raise ValueError(
            "Ollama adapter required for from-text generation "
            "(stub keyword extraction removed from the pipeline)."
        )
    # Reject the stub keyword / exact StubLlmAdapter only. Test fakes that subclass
    # StubLlmAdapter but advertise a non-stub name (e.g. digits_leak) may still be used.
    if getattr(adapter, "name", None) == "stub" or type(adapter) is StubLlmAdapter:
        raise ValueError(
            "Keyword stub is not allowed for parameter extraction. Use Ollama."
        )
    if isinstance(adapter, FallbackAdapter):
        # Unwrap: Task A must not succeed via stub.
        adapter = adapter.primary
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
        description_fi = text

    opts = dict(options or default_options_from_text(language=language))
    if "seed" not in opts:
        opts["seed"] = 42
    params = adapter.extract_parameters(description_fi, description_en, opts)
    validated = validate_model(ParametersFromLanguageModel, params)

    # Stamp scenario_id from scenario_shape so engine uses shape, not keywords.
    shape = getattr(validated, "scenario_shape", None) or params.get("scenario_shape")
    if shape and not opts.get("scenario_id"):
        from payloq_llm.extract_pipeline import scenario_id_from_shape

        opts["scenario_id"] = scenario_id_from_shape(str(shape))

    invoice_texts: InvoiceDescriptiveTexts | None = None
    if with_invoice_texts:
        try:
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
        except Exception:
            # Descriptive texts may fall back to built-in FI defaults (texts only).
            from payloq_llm.invoice_text_defaults import default_invoice_texts

            invoice_texts = default_invoice_texts(
                language=str(opts.get("language", language)),
            )

    model_name = getattr(adapter, "model", None) or getattr(adapter, "name", "ollama")
    note = f"parameters via ollama ({model_name})"

    return GeneratorInput(
        meta=ScenarioMeta(fictional=True, note=note, seed=int(opts.get("seed") or 42)),
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
    if adapter is None:
        raise ValueError("Ollama adapter required for from-text generation.")
    if getattr(adapter, "name", None) == "stub" or type(adapter) is StubLlmAdapter:
        raise ValueError("Keyword stub is not allowed for parameter extraction.")
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
