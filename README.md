# Billit-plugin voor Claude Code

Laat Claude rechtstreeks met je [Billit](https://www.billit.be)-account werken: facturen zoeken en samenvatten,
facturen/creditnota's aanmaken en versturen (Peppol, e-mail, …), betalingen registreren, klanten beheren
en checken of een bedrijf Peppol-facturen kan ontvangen.

Bevat:
- **MCP-server** `billit` (Python 3, geen extra packages) met 16 tools — zie `server/billit_mcp.py`
- **Skill** `billit` — hoe Claude de tools veilig gebruikt (altijd bevestiging vóór aanmaken/versturen)
- **Commands** `/billit:openstaand` en `/billit:factuur`

## 1. Installeren

```bash
claude plugin marketplace add laurensdehoorne/claude_billit_api
```

```bash
claude plugin install billit@billit-local
```

Of in Claude Code: `/plugin marketplace add laurensdehoorne/claude_billit_api` en daarna `/plugin install billit@billit-local`.

## 2. Instellen (in Claude Code zelf)

Bij het inschakelen vraagt Claude Code drie instellingen. Later aanpassen kan via `/plugin` → billit → configureren.

| Instelling | Wat |
|---|---|
| **Billit API-sleutel** | My Billit → Profiel → API. Wordt veilig bewaard (keychain), niet in een tekstbestand. |
| **Omgeving** | `sandbox` (standaard) of `production`. Sandbox en productie hebben elk een eigen sleutel. |
| **Bedrijf** (optioneel) | Je **btw-nummer** (bv. `BE0123456789`, puntjes mogen), de **bedrijfsnaam**, of de PartyID. Leeg laten als je maar één bedrijf hebt. |

Een PartyID opzoeken is dus niet nodig: de plugin vraagt met je sleutel zelf op tot welke bedrijven je toegang hebt.
Werk je voor meerdere bedrijven, zeg dan gewoon tegen Claude voor welk bedrijf (naam of btw-nummer).

Herstart Claude Code en check met `/mcp` dat de `billit`-server verbonden is. Vraag daarna bv. "toon mijn Billit-accountinfo".

> Billit staat API-keys alleen toe voor eigen, niet-commerciële integraties — precies dit gebruik. Begin op de sandbox (https://my.sandbox.billit.be).

<details>
<summary>Alternatief: omgevingsvariabelen</summary>

Als je de plugin-instellingen leeg laat, leest de server deze variabelen uit je shell:

```bash
export BILLIT_API_KEY="..."
export BILLIT_COMPANY="BE0123456789"   # optioneel: btw-nummer, naam of PartyID
export BILLIT_ENV="sandbox"            # of "production"
export BILLIT_READ_ONLY="true"         # optioneel: enkel lezen, geen schrijf-tools
```
</details>

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
