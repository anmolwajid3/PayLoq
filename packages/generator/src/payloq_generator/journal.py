"""Optional §4 journal / accounting-entries dataset (code-owned, synthetic)."""

from __future__ import annotations

from datetime import date

from payloq_schemas.constants import VAT_RATE_FI
from payloq_schemas.models import (
    JournalEntries,
    JournalEntry,
    JournalLine,
    ScenarioMeta,
    ScenarioPack,
)


def _r(value: float) -> float:
    return float(round(value, 2))


def _end_of_month(yyyy_mm: str) -> str:
    y, m = map(int, yyyy_mm.split("-"))
    if m == 12:
        return date(y, 12, 31).isoformat()
    return date.fromordinal(date(y, m + 1, 1).toordinal() - 1).isoformat()



def _line(
    account: str,
    name_fi: str,
    name_en: str,
    *,
    debit: float = 0.0,
    credit: float = 0.0,
) -> JournalLine:
    return JournalLine(
        account=account,
        account_name_fi=name_fi,
        account_name_en=name_en,
        debit=_r(debit),
        credit=_r(credit),
    )


def build_journal_entries(pack: ScenarioPack) -> JournalEntries:
    """
    Derive a simplified double-entry journal from monthly P&L + open invoices.

    Figures stay code-owned. This is a research illustration, not Finnish GAAP
    or an official tilikartta.
    """
    cash = pack.cash_and_invoices
    scenario = pack.input.options.scenario_id or pack.input.meta.scenario or "scenario"
    as_of = cash.meta.as_of or _end_of_month(pack.monthly_reports.months[-1].month)
    entries: list[JournalEntry] = []
    seq = 0

    def _next_id(prefix: str) -> str:
        nonlocal seq
        seq += 1
        return f"{prefix}-{seq:04d}"

    for month in pack.monthly_reports.months:
        is_ = month.income_statement
        d = _end_of_month(month.month)
        rev = is_.revenue
        if rev > 0:
            # Net revenue + VAT on AR side (illustrative)
            vat = _r(rev * VAT_RATE_FI)
            gross = _r(rev + vat)
            entries.append(
                JournalEntry(
                    id=_next_id("JE-REV"),
                    date=d,
                    description_fi=f"Myyntikirjaus {month.month}",
                    description_en=f"Sales recognition {month.month}",
                    source="monthly_pl",
                    lines=[
                        _line("1700", "Myyntisaamiset", "Trade receivables", debit=gross),
                        _line("3000", "Liikevaihto", "Revenue", credit=rev),
                        _line("2940", "ALV-velka", "VAT payable", credit=vat),
                    ],
                )
            )

        mats = is_.materials_and_services
        if mats > 0:
            vat = _r(mats * VAT_RATE_FI)
            gross = _r(mats + vat)
            entries.append(
                JournalEntry(
                    id=_next_id("JE-PUR"),
                    date=d,
                    description_fi=f"Ostot / palvelut {month.month}",
                    description_en=f"Materials & services {month.month}",
                    source="monthly_pl",
                    lines=[
                        _line("4000", "Aineet ja palvelut", "Materials and services", debit=mats),
                        _line("1760", "ALV-saaminen", "VAT receivable", debit=vat),
                        _line("2800", "Ostovelat", "Trade payables", credit=gross),
                    ],
                )
            )

        personnel = is_.personnel_costs
        if personnel > 0:
            entries.append(
                JournalEntry(
                    id=_next_id("JE-PER"),
                    date=d,
                    description_fi=f"Henkilöstökulut {month.month}",
                    description_en=f"Personnel costs {month.month}",
                    source="monthly_pl",
                    lines=[
                        _line("5000", "Henkilöstökulut", "Personnel costs", debit=personnel),
                        _line("1910", "Rahat ja pankkisaamiset", "Cash", credit=personnel),
                    ],
                )
            )

        other = is_.other_operating_costs
        if other > 0:
            entries.append(
                JournalEntry(
                    id=_next_id("JE-OOC"),
                    date=d,
                    description_fi=f"Liiketoiminnan muut kulut {month.month}",
                    description_en=f"Other operating costs {month.month}",
                    source="monthly_pl",
                    lines=[
                        _line(
                            "6000",
                            "Liiketoiminnan muut kulut",
                            "Other operating costs",
                            debit=other,
                        ),
                        _line("1910", "Rahat ja pankkisaamiset", "Cash", credit=other),
                    ],
                )
            )

        dep = is_.depreciation
        if dep > 0:
            entries.append(
                JournalEntry(
                    id=_next_id("JE-DEP"),
                    date=d,
                    description_fi=f"Poistot {month.month}",
                    description_en=f"Depreciation {month.month}",
                    source="monthly_pl",
                    lines=[
                        _line("7000", "Poistot", "Depreciation", debit=dep),
                        _line(
                            "1200",
                            "Pysyvät vastaavat (kertymä)",
                            "Fixed assets (accum. dep.)",
                            credit=dep,
                        ),
                    ],
                )
            )

        tax = is_.income_tax
        if tax > 0:
            entries.append(
                JournalEntry(
                    id=_next_id("JE-TAX"),
                    date=d,
                    description_fi=f"Tulovero {month.month}",
                    description_en=f"Income tax {month.month}",
                    source="monthly_pl",
                    lines=[
                        _line("8900", "Tulovero", "Income tax", debit=tax),
                        _line("2950", "Verovelka", "Tax payable", credit=tax),
                    ],
                )
            )

    invest = pack.input.parameters_from_language_model.special_investment_eur
    if invest and invest > 0:
        entries.append(
            JournalEntry(
                id=_next_id("JE-INV"),
                date=as_of,
                description_fi="Erityisinvestointi (parametri)",
                description_en="Special investment (from parameters)",
                source="investment",
                lines=[
                    _line("1100", "Pysyvät vastaavat", "Fixed assets", debit=invest),
                    _line("1910", "Rahat ja pankkisaamiset", "Cash", credit=invest),
                ],
            )
        )

    for inv in cash.open_invoices:
        amt = inv.amount_incl_vat
        if inv.type == "sales":
            entries.append(
                JournalEntry(
                    id=_next_id("JE-OI"),
                    date=inv.issue_date,
                    description_fi=f"Avoin myyntilasku {inv.id}: {inv.counterparty}",
                    description_en=f"Open sales invoice {inv.id}: {inv.counterparty}",
                    source="open_invoice",
                    lines=[
                        _line("1700", "Myyntisaamiset", "Trade receivables", debit=amt),
                        _line(
                            "3000",
                            "Liikevaihto + ALV (brutto)",
                            "Revenue + VAT (gross)",
                            credit=amt,
                        ),
                    ],
                )
            )
        else:
            entries.append(
                JournalEntry(
                    id=_next_id("JE-OI"),
                    date=inv.issue_date,
                    description_fi=f"Avoin ostolasku {inv.id}: {inv.counterparty}",
                    description_en=f"Open purchase invoice {inv.id}: {inv.counterparty}",
                    source="open_invoice",
                    lines=[
                        _line(
                            "4000",
                            "Ostot sis. ALV (brutto)",
                            "Purchases incl. VAT (gross)",
                            debit=amt,
                        ),
                        _line("2800", "Ostovelat", "Trade payables", credit=amt),
                    ],
                )
            )

    return JournalEntries(
        meta=ScenarioMeta(
            fictional=True,
            dataset="journal_entries",
            currency="EUR",
            scenario=scenario,
            as_of=as_of,
            note="§4 optional journal export — synthetic, code-generated",
        ),
        entries=entries,
    )
