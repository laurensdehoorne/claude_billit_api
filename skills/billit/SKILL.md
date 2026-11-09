---
name: billit
description: Use this skill whenever the user asks about their Billit account or invoicing through Billit — sales or purchase invoices ("facturen", "aankoopfacturen", "creditnota"), unpaid or overdue invoices ("openstaande facturen", "wie moet nog betalen"), customers/suppliers ("klanten", "leveranciers"), creating or sending an invoice ("maak een factuur", "verstuur via Peppol"), registering a payment ("markeer als betaald"), or checking whether a company can receive Peppol e-invoices. Uses the billit MCP server tools (billit_*).
---

# Billit

The `billit` MCP server (tools named `billit_*`) talks to the Billit REST API.
Environment (sandbox/production) is set by `BILLIT_ENV`; the server's instructions say which one is active. Mention it when you create or send something.

## Reading data

- Start with `billit_account_info` if you don't know which company (PartyID) to use, or if the user has several companies.
- `billit_list_orders` is the main search tool. Prefer its convenience args:
  - `direction`: `Income` (verkoop) or `Cost` (aankoop)
  - `order_type`: `Invoice`, `CreditNote`, `Offer`
  - `unpaid_only`, `date_from`, `date_to` (YYYY-MM-DD), `search` (free text)
  - Raw OData in `filter` for the rest, e.g. `CounterParty/VATNumber eq 'BE0563846944'`, `TotalIncl gt 1000`, `LastModified ge DateTime'2026-01-01'`.
  - Page size is 120. If the result has `NextPageLink`, call again with `skip` to get everything before you total amounts.
- `billit_get_order` for lines, VAT breakdown, delivery status (Peppol/e-mail), and file IDs (PDF/UBL). Download with `billit_download_file`.
- `billit_peppol_check` with a VAT number before sending via Peppol. Only send via Peppol when `Registered` is true **and** `DocumentTypes` contains `BISv3Invoice` (or `BISv3CreditNote` for credit notes). Otherwise suggest `SMTP` (e-mail).
- `billit_raw_request` covers the rest of the API (reports, Peppol inbox, webhooks, documents…). Swagger: https://api.billit.be/swagger/ui/index

Present lists as compact tables (nummer, datum, klant/leverancier, totaal incl., te betalen, status). Answer in the user's language (usually Dutch).

## Changing data — always confirm first

Creating, updating, deleting, paying and especially **sending** have real consequences on production (sending over Peppol cannot be undone).

1. Show the user exactly what you will do (the order JSON summarised: customer, lines, VAT, totals, due date; or which invoice IDs go out via which channel).
2. Wait for an explicit "ja"/"ok" before calling a write tool.
3. Create and send are separate steps: `billit_create_order` → show the result via `billit_get_order` → after confirmation `billit_send_orders`.

### Creating an invoice

Minimal sales invoice body for `billit_create_order`:

```json
{
  "OrderType": "Invoice",
  "OrderDirection": "Income",
  "OrderNumber": "2026-0042",
  "OrderDate": "2026-11-09",
  "ExpiryDate": "2026-12-09",
  "Customer": {
    "Name": "Acme NV",
    "VATNumber": "BE0123456789",
    "PartyType": "Customer",
    "Email": "boekhouding@acme.be",
    "Addresses": [
      { "AddressType": "InvoiceAddress", "Name": "Acme NV", "Street": "Kerkstraat", "StreetNumber": "1",
        "Zipcode": "9000", "City": "Gent", "CountryCode": "BE" }
    ]
  },
  "OrderLines": [
    { "Quantity": 8, "UnitPriceExcl": 95.0, "Description": "Consultancy oktober", "VATPercentage": 21 }
  ]
}
```

Notes:
- Leave `OrderNumber` out to let Billit use the next number in the sequence, unless the user gives one.
- Billit calculates totals itself; don't send TotalExcl/TotalIncl.
- Existing customers are matched on VAT number/e-mail, so you don't need to create the party first.
- Credit note: `"OrderType": "CreditNote"` with positive amounts; reference the original invoice number in `"About"` or `"Reference"` when known.
- Private person: omit `VATNumber`.

### Payments

- Partial/full payment: `billit_add_payment` (amount, date).
- Just flag as paid: `billit_update_order` with `{"Paid": true, "PaidDate": "YYYY-MM-DD"}`.

## Errors

- "BILLIT_API_KEY is not set": tell the user to export `BILLIT_API_KEY` and `BILLIT_PARTY_ID` (see the plugin README) and restart Claude Code.
- HTTP 401/403: wrong key, wrong PartyID, or a sandbox key used against production (or vice versa).
- Validation errors on send: show Billit's message, fix the invoice with `billit_update_order`, then retry.
