---
description: Overzicht van openstaande (onbetaalde) verkoopfacturen in Billit, met vervallen facturen eerst
argument-hint: "[klantnaam of periode, optioneel]"
---
Gebruik de billit-tools om alle onbetaalde verkoopfacturen op te halen (`billit_list_orders` met direction=Income, order_type=Invoice, unpaid_only=true; haal alle pagina's op).
Extra wens van de gebruiker: $ARGUMENTS

Toon:
1. Een tabel gesorteerd op dagen vervallen (meest vervallen eerst): factuurnummer, klant, factuurdatum, vervaldatum, te betalen, dagen vervallen.
2. Totaal openstaand, totaal vervallen, en een top 5 klanten op openstaand bedrag.
Verander niets in Billit.
