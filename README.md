# Billit-plugin voor Claude Code

Laat Claude rechtstreeks met je [Billit](https://www.billit.be)-account werken: facturen zoeken en samenvatten,
facturen/creditnota's aanmaken en versturen (Peppol, e-mail, …), betalingen registreren, klanten beheren,
CODA-rekeninguittreksels uitlezen en importeren, betalingen aan openstaande facturen koppelen
en checken of een bedrijf Peppol-facturen kan ontvangen.

Bevat:
- **MCP-server** `billit` (Python 3, geen extra packages) met 20 tools — zie `server/billit_mcp.py` en `server/coda.py`
- **Skill** `billit` — hoe Claude de tools veilig gebruikt (altijd bevestiging vóór aanmaken/versturen)
- **Commands** `/billit:openstaand`, `/billit:factuur` en `/billit:coda`

## 1. Installeren

```bash
claude plugin marketplace add laurensdehoorne/claude_billit_api
```

```bash
claude plugin install billit@billit-local
```

Of in Claude Code: `/plugin marketplace add laurensdehoorne/claude_billit_api` en daarna `/plugin install billit@billit-local`.

## 2. Instellen (configbestand)

De server leest zijn instellingen uit **`~/.config/billit/config.json`**. Zo werkt hij zowel in Claude Code als in Cowork (de desktop-app start geen plugin-servers die plugin-instellingen gebruiken).

```bash
mkdir -p ~/.config/billit
cat > ~/.config/billit/config.json <<'JSON'
{
  "api_key": "PLAK-HIER-JE-SLEUTEL",
  "environment": "production",
  "company": ""
}
JSON
chmod 600 ~/.config/billit/config.json
```

| Sleutel | Wat |
|---|---|
| **api_key** | My Billit → Profiel → API. Het bestand is alleen voor jou leesbaar (`chmod 600`). |
| **environment** | `sandbox` (standaard) of `production`. Sandbox en productie hebben elk een eigen sleutel. Hoofdletters en spaties maken niet uit; `productie`, `prod` en `live` betekenen ook productie, `test` betekent sandbox. Bij een andere waarde geven de tools een foutmelding in plaats van stilletjes de sandbox te gebruiken. |
| **company** (optioneel) | Je **btw-nummer** (bv. `BE0123456789`, puntjes mogen), de **bedrijfsnaam**, of de PartyID. Leeg laten als je maar één bedrijf hebt. |
| **read_only** (optioneel) | `true` om alle tools die iets wijzigen te verbergen. |

Een PartyID opzoeken is dus niet nodig: de plugin vraagt met je sleutel zelf op tot welke bedrijven je toegang hebt.
Werk je voor meerdere bedrijven, zeg dan gewoon tegen Claude voor welk bedrijf (naam of btw-nummer).

Start daarna een **nieuw gesprek** (de server laadt alleen bij het begin van een sessie) en vraag bv. "toon mijn Billit-accountinfo".

> Billit staat API-keys alleen toe voor eigen, niet-commerciële integraties — precies dit gebruik. Begin op de sandbox (https://my.sandbox.billit.be).

<details>
<summary>Alternatief: omgevingsvariabelen</summary>

Omgevingsvariabelen gaan voor op het configbestand:

```bash
export BILLIT_API_KEY="..."
export BILLIT_COMPANY="BE0123456789"   # optioneel: btw-nummer, naam of PartyID
export BILLIT_ENV="sandbox"            # of "production"
export BILLIT_READ_ONLY="true"         # optioneel: enkel lezen, geen schrijf-tools
export BILLIT_CONFIG="/ander/pad.json" # optioneel: ander configbestand
```
</details>

## Tools

| Lezen | Schrijven (vraagt bevestiging) |
|---|---|
| `billit_account_info`, `billit_list_orders`, `billit_get_order`, `billit_list_parties`, `billit_get_party`, `billit_list_products`, `billit_peppol_check`, `billit_company_search`, `billit_download_file`, `billit_raw_request` (GET) | `billit_create_order`, `billit_update_order`, `billit_delete_order`, `billit_send_orders`, `billit_add_payment`, `billit_upsert_party` |
| **Bank / CODA:** `billit_read_coda` (lokaal, uploadt niets), `billit_list_transactions`, `billit_match_payments` (stelt alleen voor) | `billit_import_coda` |

## Voorbeelden

- "Welke klanten zijn meer dan 30 dagen te laat met betalen?"
- "Hoeveel heb ik dit jaar per leverancier uitgegeven?"
- "Maak een factuur voor Acme NV: 8 uur consultancy aan €95, 21% btw, en stuur ze via Peppol."
- "Markeer factuur 2026-0031 als betaald op 5 november."
- "Lees ~/Downloads/KBC_oktober.cod en toon wat er binnenkwam."
- "Welke openstaande facturen zijn betaald volgens de uittreksels in ~/Documents/CODA? Boek ze als betaald."

## CODA

`billit_read_coda` leest CODA 2.x-bestanden (Febelfin-standaard) zonder externe library. Het controleert of
oud saldo + bewegingen = nieuw saldo, herkent gestructureerde mededelingen (+++123/4567/89012+++, met
modulo-97-controle) en houdt rekening met gegroepeerde (geglobaliseerde) bewegingen.
`billit_match_payments` koppelt transacties aan openstaande facturen via gestructureerde mededeling,
factuurnummer in de mededeling, of bedrag + naam tegenpartij — en stelt dat alleen voor; boeken gebeurt pas na je bevestiging.

## Tip: officiële read-only connector

Billit heeft ook een officiële (alleen-lezen) connector in de Claude-connectorendirectory.
Deze plugin doet daarnaast ook schrijfacties (aanmaken, versturen, betalingen).
