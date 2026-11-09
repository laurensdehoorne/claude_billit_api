---
description: Maak een verkoopfactuur in Billit (en verstuur ze na bevestiging)
argument-hint: "<klant, wat, hoeveel, prijs...>"
---
Maak een verkoopfactuur in Billit op basis van: $ARGUMENTS

Werkwijze (volg de billit-skill):
1. Zoek de klant op met `billit_list_parties` (search). Bestaat die niet, gebruik `billit_company_search` voor naam/BTW/adres.
2. Vraag wat ontbreekt (prijs, BTW-tarief, vervaldatum — standaard 30 dagen).
3. Toon een samenvatting (klant, lijnen, BTW, totaal excl./incl., vervaldatum) en wacht op bevestiging.
4. Maak de factuur met `billit_create_order` en toon het resultaat met `billit_get_order`.
5. Check met `billit_peppol_check` of de klant via Peppol kan ontvangen en stel het kanaal voor (Peppol of e-mail). Verstuur pas na een expliciete "ja" met `billit_send_orders`.
