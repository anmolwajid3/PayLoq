"""Pydantic models for PayLoq scenario packs (v0 — free to evolve)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScenarioMeta(BaseModel):
    fictional: bool = True
    note: str | None = None
    dataset: str | None = None
    currency: str | None = None
    scenario: str | None = None
    as_of: str | None = None


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


class ParametersFromLanguageModel(BaseModel):
    monthly_revenue_start_eur: float = Field(gt=0)
    monthly_revenue_growth: float
    cost_shares_of_revenue: CostShares
    days_sales_outstanding: float = Field(gt=0)
    days_payables_outstanding: float = Field(gt=0)
    target_cash_at_end_eur: float
    special_investment_eur: float = 0.0
    notes: str | None = None
    # When True, personnel/other are partly fixed to start-month levels (weak/critical).
    partly_fixed_costs: bool = False


class GeneratorInput(BaseModel):
    meta: ScenarioMeta = Field(default_factory=ScenarioMeta)
    scenario_description: ScenarioDescription
    options: Options
    parameters_from_language_model: ParametersFromLanguageModel


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
    date: str  # YYYY-MM-DD
    balance: float


class OpenInvoice(BaseModel):
    id: str
    type: Literal["sales", "purchase"]
    counterparty: str
    description: str
    issue_date: str
    due_date: str
    amount_incl_vat: float
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
