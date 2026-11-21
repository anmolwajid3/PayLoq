"""Pydantic models for PayLoq scenario packs (v0 — free to evolve)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ParamSource = Literal["stated", "assumed"]


class ScenarioMeta(BaseModel):
    fictional: bool = True
    note: str | None = None
    dataset: str | None = None
    currency: str | None = None
    scenario: str | None = None
    as_of: str | None = None
    # Work order C: seed stamped into every output meta when present.
    seed: int | None = None


class ScenarioDescription(BaseModel):
    fi: str
    en: str


class Options(BaseModel):
    industry: str
    company_size: str
    months: int = Field(ge=12, le=24)
    language: Literal["fi", "en"] = "fi"
    currency: Literal["EUR"] = "EUR"
    # Optional profile hint for generator behaviour (good | weak | cash_critical | custom)
    scenario_id: str | None = None
    as_of: str | None = Field(
        default=None,
        description="Anchor date YYYY-MM-DD for cash history / projection (default: last day of final month).",
    )


class CostShares(BaseModel):
    materials: float = Field(ge=0, le=1)
    services: float = Field(ge=0, le=1)
    personnel: float = Field(ge=0, le=1)
    other: float = Field(ge=0, le=1)


class ExtractedCostShares(BaseModel):
    """LLM extract shape: each cost share may be null when unstated (Run #19)."""

    materials: float | None = Field(default=None, ge=0, le=1)
    services: float | None = Field(default=None, ge=0, le=1)
    personnel: float | None = Field(default=None, ge=0, le=1)
    other: float | None = Field(default=None, ge=0, le=1)


class OneOffCashEvent(BaseModel):
    """Structured one-off cash event (capex, roof repair, grant, etc.)."""

    type: str = Field(
        default="other",
        description="Event type (capex, grant, repair, other). CAPEX is always an outflow.",
    )
    amount_eur: float = Field(gt=0)
    month_index: int = Field(
        ge=1,
        le=24,
        description="1-based index into the generated monthly_reports series",
    )
    direction: Literal["inflow", "outflow"] = "outflow"
    label: str | None = None

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction_in(cls, value: object) -> object:
        if value is None:
            return value
        direction = str(value).strip().lower()
        if direction in {"in", "inflow"}:
            return "inflow"
        if direction in {"out", "outflow"}:
            return "outflow"
        return direction

    @model_validator(mode="after")
    def _capex_and_direction(self) -> OneOffCashEvent:
        direction = self.direction
        event_type = (self.type or "other").strip().lower() or "other"
        if event_type in {"capex", "capital_expenditure", "investment"}:
            event_type = "capex"
            direction = "outflow"
        if direction not in {"inflow", "outflow"}:
            raise ValueError("one_off_events.direction must be inflow or outflow")
        if self.month_index is None:
            raise ValueError("one_off_events.month_index is required")
        object.__setattr__(self, "type", event_type)
        object.__setattr__(self, "direction", direction)
        return self


class ExtractedOneOffCashEvent(BaseModel):
    """
    LLM extract shape for one-offs: incomplete rows may carry null amount/month/direction.

    Incomplete events are dropped after extract (work order B); only complete rows
    become ``OneOffCashEvent``.
    """

    type: str | None = "other"
    amount_eur: float | None = None
    month_index: int | None = None
    direction: Literal["inflow", "outflow"] | None = None
    label: str | None = None

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction_in(cls, value: object) -> object:
        if value is None or value == "":
            return None
        direction = str(value).strip().lower()
        if direction in {"in", "inflow"}:
            return "inflow"
        if direction in {"out", "outflow"}:
            return "outflow"
        return direction


class ParametersFromLanguageModel(BaseModel):
    """Generator parameters. Legacy names are the serialization keys; WO aliases accepted."""

    monthly_revenue_start_eur: float = Field(
        gt=0,
        description="Month-1 revenue in EUR (alias: revenue_monthly_start_eur / revenue_monthly_eur).",
    )
    monthly_revenue_growth: float = Field(
        description="MoM growth fraction; 0.003 means 0.3% (alias: growth_per_month_fraction).",
    )
    cost_shares_of_revenue: CostShares
    days_sales_outstanding: float = Field(
        gt=0, description="DSO in days (alias: dso_days)."
    )
    days_payables_outstanding: float = Field(
        gt=0, description="DPO in days (alias: dpo_days)."
    )
    target_cash_at_end_eur: float = Field(
        description="Ending / covenant cash target EUR (alias: covenant_min_cash_eur).",
    )
    # Work order A/C: opening cash. Optional on hand-authored packs; required after LLM extract.
    starting_cash_eur: float | None = Field(
        default=None,
        description="Opening cash EUR. Must be stated for LLM extraction; assumed only via code table.",
    )
    # Explicit WO alias field (mirrors target when set).
    covenant_min_cash_eur: float | None = Field(
        default=None,
        description="Optional covenant floor; when set, mirrors/overrides target_cash_at_end_eur.",
    )
    special_investment_eur: float = 0.0
    # 1-based month index for special_investment_eur (default 2 → second monthly report).
    special_investment_month: int = Field(default=2, ge=1, le=24)
    # Calendar-month seasonality: index 0=Jan … 11=Dec. Applied to monthly revenue.
    monthly_revenue_factors: list[float] | None = Field(
        default=None,
        description="Twelve floats (Jan–Dec); e.g. summer 1.0, winter 0.3 for hotel collapse.",
    )
    # Extra structured events; special_investment_* is also applied as an outflow.
    one_off_events: list[OneOffCashEvent] = Field(default_factory=list)
    notes: str | None = None
    # When True, personnel/other are partly fixed to start-month levels (weak/critical).
    partly_fixed_costs: bool = False
    # Work order A/B: per-field provenance. Keys use legacy serialization names.
    field_sources: dict[str, ParamSource] = Field(default_factory=dict)
    # Pilot fix §B/D: exact quotes for stated fields + optional stated numeric snapshot.
    field_quotes: dict[str, str] = Field(default_factory=dict)
    stated_values: dict[str, Any] = Field(default_factory=dict)
    scenario_shape: str | None = None
    scenario_shape_quote: str | None = None
    # Optional annual revenue before code conversion to monthly.
    revenue_annual_eur: float | None = None
    # Model / extract metadata stamped into input.json
    llm_model_name: str | None = None
    extraction_seed: int | None = None
    conversion_notes: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("monthly_revenue_factors")
    @classmethod
    def _factors_len(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return v
        if len(v) != 12:
            raise ValueError("monthly_revenue_factors must have exactly 12 floats (Jan–Dec)")
        return [float(x) for x in v]

    @model_validator(mode="before")
    @classmethod
    def _accept_wo_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        alias_map = {
            "revenue_monthly_start_eur": "monthly_revenue_start_eur",
            "revenue_monthly_eur": "monthly_revenue_start_eur",
            "growth_per_month_fraction": "monthly_revenue_growth",
            "dso_days": "days_sales_outstanding",
            "dpo_days": "days_payables_outstanding",
        }
        for alias, canonical in alias_map.items():
            if out.get(canonical) is None and out.get(alias) is not None:
                out[canonical] = out[alias]
        # Fill missing covenant from target only. Do NOT copy covenant → target
        # (stated covenant must not force target_cash equal to it).
        if out.get("covenant_min_cash_eur") is None and out.get("target_cash_at_end_eur") is not None:
            out["covenant_min_cash_eur"] = out["target_cash_at_end_eur"]
        return out


class ExtractedParameters(BaseModel):
    """
    LLM extraction shape (work order A): only stated values; unstated fields are null.
    The LLM must never invent defaults. Code assumes missing optional fields later.

    Nested cost shares and one-off event numerics are also nullable so Ollama can
    return null for unstated sub-fields without Pydantic rejecting the whole payload
    (Run #19 regression).
    """

    monthly_revenue_start_eur: float | None = None
    monthly_revenue_growth: float | None = None
    cost_shares_of_revenue: ExtractedCostShares | None = None
    days_sales_outstanding: float | None = None
    days_payables_outstanding: float | None = None
    target_cash_at_end_eur: float | None = None
    starting_cash_eur: float | None = None
    covenant_min_cash_eur: float | None = None
    special_investment_eur: float | None = None
    special_investment_month: int | None = None
    monthly_revenue_factors: list[float] | None = None
    one_off_events: list[ExtractedOneOffCashEvent] | None = None
    notes: str | None = None
    partly_fixed_costs: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_wo_aliases(cls, data: Any) -> Any:
        return ParametersFromLanguageModel._accept_wo_aliases(data)


class InvoiceDescriptiveTexts(BaseModel):
    """LLM-authored FI/EN invoice labels. Amounts stay in the generator."""

    sales_counterparties: list[str] = Field(min_length=1)
    purchase_counterparties: list[str] = Field(min_length=1)
    sales_descriptions: list[str] = Field(min_length=1)
    purchase_descriptions: list[str] = Field(min_length=1)
    language: Literal["fi", "en"] = "fi"
    notes: str | None = None


class GeneratorInput(BaseModel):
    meta: ScenarioMeta = Field(default_factory=ScenarioMeta)
    scenario_description: ScenarioDescription
    options: Options
    parameters_from_language_model: ParametersFromLanguageModel
    # Optional; when set, generator uses these instead of built-in FI default lists.
    invoice_texts: InvoiceDescriptiveTexts | None = None


class IncomeStatement(BaseModel):
    revenue: float
    materials_and_services: float
    personnel_costs: float
    other_operating_costs: float
    depreciation: float
    operating_profit: float
    interest_expense: float
    profit_before_tax: float
    income_tax: float
    net_result: float


class Assets(BaseModel):
    fixed_assets: float
    inventory: float
    receivables: float
    cash: float
    total_assets: float


class EquityAndLiabilities(BaseModel):
    equity: float
    loans: float
    payables: float
    other_current_liabilities: float
    total_equity_and_liabilities: float


class BalanceSheet(BaseModel):
    assets: Assets
    equity_and_liabilities: EquityAndLiabilities


class MonthlyReport(BaseModel):
    month: str  # YYYY-MM
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet


class MonthlyReports(BaseModel):
    meta: ScenarioMeta
    months: list[MonthlyReport]


class BalanceHistoryPoint(BaseModel):
    week: int = Field(ge=1, description="1..26 week index within the balance history")
    date: str  # YYYY-MM-DD
    balance: float


class OpenInvoice(BaseModel):
    id: str
    type: Literal["sales", "purchase"]
    counterparty: str
    description: str
    issue_date: str
    due_date: str
    amount_incl_vat: float  # gross (legacy / primary field; SRS amount_gross_eur)
    amount_net_eur: float | None = None
    vat_eur: float | None = None
    status: Literal["open", "overdue"]


class ProjectionWeek(BaseModel):
    week: int
    week_end: str
    sales_inflow: float
    purchase_outflow: float
    projected_balance: float


class CashAndInvoices(BaseModel):
    meta: ScenarioMeta
    balance_history: list[BalanceHistoryPoint]
    open_invoices: list[OpenInvoice]
    projection_from_open_invoices: list[ProjectionWeek]

    @field_validator("balance_history")
    @classmethod
    def _history_len(cls, v: list[BalanceHistoryPoint]) -> list[BalanceHistoryPoint]:
        if len(v) < 1:
            raise ValueError("balance_history must not be empty")
        return v


class ScenarioPack(BaseModel):
    """Full generated pack (in-memory)."""

    input: GeneratorInput
    monthly_reports: MonthlyReports
    cash_and_invoices: CashAndInvoices
