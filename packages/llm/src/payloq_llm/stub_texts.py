"""Built-in FI/EN invoice descriptive text packs (no LLM required)."""

from __future__ import annotations

from payloq_schemas.models import InvoiceDescriptiveTexts

SALES_COUNTERPARTIES_FI = [
    "Pohjanranta Teollisuus Oy",
    "Kaarna Koneistus Oy",
    "Meriniitty Laitetekniikka Oy",
    "Alavuori Metalli Oy",
    "Kivikangas Konepaja Oy",
    "Lehtoranta Tekniikka Oy",
    "Salmenkallio Oy",
    "Harmaakivi Asennus Oy",
    "Vesikari Tuotanto Oy",
    "Tuulisuo Teollisuuspalvelu Oy",
]

PURCHASE_COUNTERPARTIES_FI = [
    "Teräs-Esimerkki Oy",
    "Sähkö ja Energia Testiyhtiö Oy",
    "Työkalu-Varasto Oy",
    "Kuljetus Testi Oy",
    "Pintakäsittely Esimerkki Oy",
    "Kiinteistö Esimerkki Oy (vuokra)",
    "Huolto ja Kunnossapito Testi Oy",
    "Pakkaus ja Tarvike Oy",
    "Vakuutus Esimerkki Oy",
    "IT-palvelut Testi Oy",
]

SALES_DESCRIPTIONS_FI = [
    "Koneistetut osat, erä",
    "Hitsauskokoonpano",
    "Sarjatuotanto, kuukausilasku",
    "Prototyyppityö",
    "Työstö ja pintakäsittely",
    "Varaosatoimitus",
    "Huoltotyö",
    "Kokoonpanotyö",
]

PURCHASE_DESCRIPTIONS_FI = [
    "Teräslevyt ja profiilit",
    "Sähkö, kuukausilasku",
    "Työkalut ja kulutustarvikkeet",
    "Rahtikulut",
    "Pintakäsittely, alihankinta",
    "Toimitilan vuokra",
    "Koneiden huolto",
    "Pakkausmateriaalit",
    "Vakuutusmaksu",
    "IT-palvelut ja ohjelmistolisenssit",
]

SALES_COUNTERPARTIES_EN = [
    "Northshore Industrial Ltd (fictional)",
    "Pinebark Machining Ltd (fictional)",
    "Seameadow Equipment Ltd (fictional)",
    "Lowhill Metals Ltd (fictional)",
    "Stoneheath Workshop Ltd (fictional)",
    "Leafshore Tech Ltd (fictional)",
    "Salmoncliff Ltd (fictional)",
    "Greyrock Assembly Ltd (fictional)",
    "Waterreef Production Ltd (fictional)",
    "Windmarsh Industrial Services Ltd (fictional)",
]

PURCHASE_COUNTERPARTIES_EN = [
    "Steel Example Ltd (fictional)",
    "Power & Energy Test Co (fictional)",
    "Tool Depot Ltd (fictional)",
    "Freight Test Ltd (fictional)",
    "Surface Treatment Example Ltd (fictional)",
    "Property Example Ltd (rent)",
    "Maintenance Test Ltd (fictional)",
    "Packaging & Supplies Ltd (fictional)",
    "Insurance Example Ltd (fictional)",
    "IT Services Test Ltd (fictional)",
]

SALES_DESCRIPTIONS_EN = [
    "Machined parts, batch",
    "Welded assembly",
    "Series production, monthly invoice",
    "Prototype work",
    "Machining and surface treatment",
    "Spare parts delivery",
    "Service work",
    "Assembly work",
]

PURCHASE_DESCRIPTIONS_EN = [
    "Steel sheets and profiles",
    "Electricity, monthly invoice",
    "Tools and consumables",
    "Freight costs",
    "Surface treatment, subcontract",
    "Premises rent",
    "Machine maintenance",
    "Packaging materials",
    "Insurance premium",
    "IT services and software licences",
]


def stub_invoice_texts(*, language: str = "fi") -> InvoiceDescriptiveTexts:
    if language == "en":
        return InvoiceDescriptiveTexts(
            sales_counterparties=list(SALES_COUNTERPARTIES_EN),
            purchase_counterparties=list(PURCHASE_COUNTERPARTIES_EN),
            sales_descriptions=list(SALES_DESCRIPTIONS_EN),
            purchase_descriptions=list(PURCHASE_DESCRIPTIONS_EN),
            language="en",
            notes="stub EN descriptive texts",
        )
    return InvoiceDescriptiveTexts(
        sales_counterparties=list(SALES_COUNTERPARTIES_FI),
        purchase_counterparties=list(PURCHASE_COUNTERPARTIES_FI),
        sales_descriptions=list(SALES_DESCRIPTIONS_FI),
        purchase_descriptions=list(PURCHASE_DESCRIPTIONS_FI),
        language="fi",
        notes="stub FI descriptive texts",
    )
