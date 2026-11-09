---
description: Lees CODA-rekeninguittreksels en koppel de betalingen aan openstaande facturen in Billit
argument-hint: "<pad naar .cod-bestand of map>"
---
CODA-bestand(en): $ARGUMENTS

Volg de billit-skill (sectie Bank statements):
1. Lees de bestanden met `billit_read_coda`. Toon per uittreksel: rekening, periode, oud saldo, inkomsten, uitgaven, nieuw saldo en of de saldocontrole klopt.
2. Zoek koppelingen met `billit_match_payments` (coda_path = hetzelfde pad). Toon de voorstellen in een tabel (datum, bedrag, tegenpartij, factuurnummer, open bedrag, soort match, volledig/gedeeltelijk), en daaronder de niet-gekoppelde transacties.
3. Vraag welke voorstellen geboekt mogen worden. Pas na een expliciete bevestiging: `billit_add_payment` per gekozen voorstel.
4. Vraag apart of de bestanden ook in Billit geïmporteerd moeten worden (`billit_import_coda`); doe dat niet automatisch.
