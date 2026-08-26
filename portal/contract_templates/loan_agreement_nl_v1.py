"""Source-derived Dutch loan agreement text.

This is a placeholder implementation based on the supplied document. It is not
legal advice and must remain behind the production legal/compliance gate until
approved by Curaçao counsel. No personal data from the supplied example is
included here.
"""


CLAUSES = [
    (
        "Artikel 1 - Hoofdsom en looptijd",
        "De schuldenaar erkent de in deze overeenkomst vermelde hoofdsom te hebben ontvangen en verbindt zich "
        "de totale terugbetaling volgens het betalingsschema te voldoen.",
    ),
    (
        "Artikel 2 - Aflossing",
        "Aflossing vindt plaats volgens het opgenomen betalingsschema. Betaling geschiedt op een door de "
        "schuldeiser schriftelijk opgegeven rekening. Vervroegde gehele of gedeeltelijke terugbetaling is toegestaan "
        "zonder extra rente wegens die vervroegde betaling.",
    ),
    (
        "Artikel 3 - Te late betaling en opeisbaarheid",
        "Bij een niet tijdige betaling kan de overeengekomen dagelijkse vergoeding worden toegepast, voor zover "
        "deze wettelijk is toegestaan. Het openstaande bedrag kan opeisbaar worden bij een betalingsachterstand van "
        "twee maanden of meer, surseance, curatele, beslag, overlijden of duurzaam vertrek uit Curaçao, voor zover "
        "toegestaan door het toepasselijke recht.",
    ),
    (
        "Artikel 4 - Einde dienstverband",
        "Indien de schuldenaar het dienstverband verliest of beëindigt, gelden de afspraken over opeisbaarheid alleen "
        "voor zover deze rechtsgeldig, redelijk en uitdrukkelijk overeengekomen zijn.",
    ),
    (
        "Artikel 5 - Kosten en afronding",
        "Kosten van invordering komen uitsluitend voor rekening van de schuldenaar voor zover deze aantoonbaar, "
        "redelijk en wettelijk verhaalbaar zijn. Na volledige terugbetaling is de lening afgelost.",
    ),
]


def agreement_snapshot() -> str:
    return "\n\n".join(f"{title}\n{text}" for title, text in CLAUSES)
