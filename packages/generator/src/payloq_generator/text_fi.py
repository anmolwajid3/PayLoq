"""Finnish/English stub descriptive texts for invoices (no LLM required)."""

from __future__ import annotations

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


def pick(items: list[str], index: int) -> str:
    return items[index % len(items)]
