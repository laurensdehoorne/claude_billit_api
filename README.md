# Billit-plugin voor Claude Code

Laat Claude rechtstreeks met je [Billit](https://www.billit.be)-account werken: facturen zoeken en samenvatten,
facturen/creditnota's aanmaken en versturen (Peppol, e-mail, …), betalingen registreren, klanten beheren
en checken of een bedrijf Peppol-facturen kan ontvangen.

Bevat:
- **MCP-server** `billit` (Python 3, geen extra packages) met 16 tools — zie `server/billit_mcp.py`
- **Skill** `billit` — hoe Claude de tools veilig gebruikt (altijd bevestiging vóór aanmaken/versturen)
- **Commands** `/billit:openstaand` en `/billit:factuur`

## 1. API-sleutel en PartyID

In My Billit: je **API key** (Profiel → API) en de **PartyID** van je bedrijf.
Sandbox en productie hebben elk een eigen sleutel en PartyID. Begin op de sandbox (https://my.sandbox.billit.be).

> Billit staat API-keys alleen toe voor eigen, niet-commerciële integraties — precies dit gebruik.

## 2. Omgevingsvariabelen

Zet ze in je shellprofiel (bv. `~/.zshrc`) zodat Claude Code ze meekrijgt:

```bash
export BILLIT_API_KEY="..."
export BILLIT_PARTY_ID="123456"
export BILLIT_ENV="sandbox"        # of "production"
# export BILLIT_READ_ONLY="true"   # optioneel: enkel lezen, geen schrijf-tools
```

## 3. Installeren

```bash
claude plugin marketplace add laurensdehoorne/claude_billit_api
claude plugin install billit@billit-local
```

Of in Claude Code: `/plugin marketplace add laurensdehoorne/claude_billit_api` en daarna `/plugin install billit@billit-local`.
Herstart Claude Code en check met `/mcp` dat de `billit`-server verbonden is.

## Tools

| Lezen | Schrijven (vraagt bevestiging) |
|---|---|
| `billit_account_info`, `billit_list_orders`, `billit_get_order`, `billit_list_parties`, `billit_get_party`, `billit_list_products`, `billit_peppol_check`, `billit_company_search`, `billit_download_file`, `billit_raw_request` (GET) | `billit_create_order`, `billit_update_order`, `billit_delete_order`, `billit_send_orders`, `billit_add_payment`, `billit_upsert_party` |

## Voorbeelden

- "Welke klanten zijn meer dan 30 dagen te laat met betalen?"
- "Hoeveel heb ik dit jaar per leverancier uitgegeven?"
- "Maak een factuur voor Acme NV: 8 uur consultancy aan €95, 21% btw, en stuur ze via Peppol."
- "Markeer factuur 2026-0031 als betaald op 5 november."

## Tip: officiële read-only connector

Billit heeft ook een officiële (alleen-lezen) connector in de Claude-connectorendirectory.
Deze plugin doet daarnaast ook schrijfacties (aanmaken, versturen, betalingen).
