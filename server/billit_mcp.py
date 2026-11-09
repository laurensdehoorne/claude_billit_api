#!/usr/bin/env python3
"""Billit MCP server (stdio, no external dependencies).

Configuration (plugin settings in Claude Code, or environment variables):
  BILLIT_API_KEY    API key from My Billit (required for most tools)
  BILLIT_COMPANY    optional: VAT number, company name or PartyID of the company to act for.
                    Not needed when the API key has access to one company only.
  BILLIT_PARTY_ID   optional, legacy alias for BILLIT_COMPANY
  BILLIT_ENV        "sandbox" (default) or "production"
The plugin passes its settings as BILLIT_CFG_*; those win over the plain variables.
  BILLIT_BASE_URL   optional: override the API base URL
  BILLIT_READ_ONLY  "true" to hide every tool that changes data
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coda  # noqa: E402  (local module, next to this file)

SERVER_NAME = "billit"
SERVER_VERSION = "0.3.0"

def setting(name, default=""):
    """Plugin setting (BILLIT_CFG_*) first, then the plain environment variable."""
    for key in ("BILLIT_CFG_" + name, "BILLIT_" + name):
        val = (os.environ.get(key) or "").strip()
        if val and not val.startswith("${"):  # ignore unexpanded placeholders
            return val
    return default


ENV = setting("ENV", "sandbox").lower()
BASE_URL = os.environ.get("BILLIT_BASE_URL") or (
    "https://api.billit.be" if ENV == "production" else "https://api.sandbox.billit.be"
)
API_KEY = setting("API_KEY")
DEFAULT_COMPANY = setting("COMPANY") or setting("PARTY_ID")
READ_ONLY = os.environ.get("BILLIT_READ_ONLY", "").strip().lower() in ("1", "true", "yes")

MAX_TEXT = 60_000  # keep tool results within a sane size for the model


class BillitError(Exception):
    pass


# --------------------------------------------------------------------------- HTTP


def billit_request(method, path, query=None, body=None, party_id=None, auth=True, extra_headers=None):
    if not path.startswith("/"):
        path = "/" + path
    url = BASE_URL.rstrip("/") + path
    if query:
        q = {k: v for k, v in query.items() if v not in (None, "")}
        if q:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)

    headers = {"Accept": "application/json", "User-Agent": f"billit-claude-plugin/{SERVER_VERSION}"}
    if auth:
        if not API_KEY:
            raise BillitError(
                "No Billit API key configured. Set it in the plugin settings (/plugin -> billit -> "
                "configure) or export BILLIT_API_KEY before starting Claude Code. See the README."
            )
        headers["ApiKey"] = API_KEY
        pid = resolve_party_id(party_id)
        if pid:
            headers["PartyID"] = pid
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:4000]
        raise BillitError(f"Billit API {method.upper()} {path} -> HTTP {e.code}: {detail or e.reason}")
    except urllib.error.URLError as e:
        raise BillitError(f"Could not reach Billit API at {BASE_URL}: {e.reason}")

    if not raw:
        return {"status": status, "result": "OK (empty response)"}
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return {"status": status, "raw": raw.decode("utf-8", "replace")}


_companies_cache = None


def norm(text):
    return re.sub(r"[^0-9a-z]", "", str(text or "").lower())


def list_companies():
    global _companies_cache
    if _companies_cache is None:
        info = billit_request("GET", "/v1/account/accountInformation", party_id="-")
        _companies_cache = (info or {}).get("Companies") or []
    return _companies_cache


def resolve_party_id(company):
    """Turn a PartyID, VAT number or company name into a PartyID.

    "-" means: send no PartyID header (used for the account lookup itself).
    """
    company = str(company or DEFAULT_COMPANY or "").strip()
    if company == "-":
        return ""
    if company.isdigit() and len(company) < 9:  # a PartyID
        return company
    companies = list_companies()
    if not company:
        if len(companies) == 1:
            return str(companies[0].get("PartyID"))
        if not companies:
            return ""
        raise BillitError(
            "This API key has access to several companies; choose one by VAT number or name "
            "(plugin setting 'company', or the party_id argument): "
            + "; ".join(f"{c.get('Name')} ({c.get('VATNumber')}, PartyID {c.get('PartyID')})" for c in companies)
        )
    want = norm(company)
    want_digits = re.sub(r"\D", "", company)
    if len(want_digits) >= 9:  # looks like a VAT / company number
        for c in companies:
            if re.sub(r"\D", "", str(c.get("VATNumber") or "")).lstrip("0") == want_digits.lstrip("0"):
                return str(c.get("PartyID"))
        if company.isdigit():  # long number that is no known VAT number: treat as PartyID
            return company
    matches = [c for c in companies
               if want and (want in norm(c.get("Name")) or want in norm(c.get("CommercialName")))]
    if len(matches) == 1:
        return str(matches[0].get("PartyID"))
    names = ", ".join(f"{c.get('Name')} ({c.get('VATNumber')})" for c in (matches or companies))
    raise BillitError(f"Company '{company}' not found unambiguously. Available: {names}")


def odata_query(args):
    q = {}
    for key in ("filter", "orderby", "top", "skip"):
        if args.get(key) not in (None, ""):
            q["$" + key] = args[key]
    if args.get("search"):
        q["fullTextSearch"] = args["search"]
    return q


def and_filter(*parts):
    parts = [p for p in parts if p]
    return " and ".join(f"({p})" if " or " in p else p for p in parts) or None


# --------------------------------------------------------------------------- slimming helpers

ORDER_SUMMARY_FIELDS = (
    "OrderID", "OrderNumber", "OrderType", "OrderDirection", "OrderDate", "ExpiryDate",
    "TotalExcl", "TotalVAT", "TotalIncl", "ToPay", "Paid", "Currency", "OrderStatus",
    "IsSent", "Overdue", "DaysOverdue", "PaymentReference", "LastModified",
)


def summarize_order(o):
    s = {k: o.get(k) for k in ORDER_SUMMARY_FIELDS if k in o}
    cp = o.get("CounterParty") or {}
    if cp:
        s["CounterParty"] = {
            "PartyID": cp.get("PartyID"),
            "Name": cp.get("DisplayName") or cp.get("Name"),
            "VATNumber": cp.get("VATNumber"),
        }
    if (o.get("OrderPDF") or {}).get("FileID"):
        s["PdfFileID"] = o["OrderPDF"]["FileID"]
    delivery = o.get("CurrentDocumentDeliveryDetails")
    if delivery:
        s["Delivery"] = delivery
    return s


def summarize_party(p):
    keys = ("PartyID", "DisplayName", "Name", "PartyType", "VATNumber", "Email", "Phone",
            "Street", "StreetNumber", "Box", "Zipcode", "City", "CountryCode", "IBAN", "LastModified")
    return {k: p.get(k) for k in keys if p.get(k) not in (None, "")}


def page(result, mapper, compact):
    if not isinstance(result, dict) or "Items" not in result:
        return result
    items = result.get("Items") or []
    out = {"Count": len(items), "Items": [mapper(i) for i in items] if compact else items}
    if result.get("NextPageLink"):
        out["NextPageLink"] = result["NextPageLink"]
        out["Hint"] = "More results exist: call again with skip=<offset> (page size is 120)."
    return out


# --------------------------------------------------------------------------- tool implementations

PARTY_ARG = {
    "party_id": {
        "type": "string",
        "description": "Optional company to act for: PartyID, VAT number or company name "
                       "(defaults to the configured company). billit_account_info lists the companies you can access.",
    }
}
ODATA_ARGS = {
    "filter": {"type": "string", "description": "OData $filter, e.g. \"OrderDate ge DateTime'2026-01-01' and Paid eq false\""},
    "orderby": {"type": "string", "description": "OData $orderby, e.g. 'OrderDate desc'"},
    "top": {"type": "integer", "description": "Max records (page size is capped at 120)"},
    "skip": {"type": "integer", "description": "Records to skip, for paging"},
    "search": {"type": "string", "description": "Free-text search (fullTextSearch)"},
}


def t_account_info(a):
    info = billit_request("GET", "/v1/account/accountInformation", party_id="-")
    companies = (info or {}).get("Companies") or []
    return {
        "User": " ".join(filter(None, [info.get("FirstName"), info.get("LastName")])) or info.get("Email"),
        "Email": info.get("Email"),
        "Environment": ENV,
        "Companies": [{k: c.get(k) for k in ("PartyID", "Name", "CommercialName", "VATNumber", "City", "PeppolIdentifier")}
                      for c in companies],
    }


def t_list_orders(a):
    extra = []
    if a.get("direction"):
        extra.append(f"OrderDirection eq '{a['direction']}'")
    if a.get("order_type"):
        extra.append(f"OrderType eq '{a['order_type']}'")
    if a.get("unpaid_only"):
        extra.append("Paid eq false")
    if a.get("date_from"):
        extra.append(f"OrderDate ge DateTime'{a['date_from']}'")
    if a.get("date_to"):
        extra.append(f"OrderDate le DateTime'{a['date_to']}'")
    args = dict(a)
    args["filter"] = and_filter(*extra, a.get("filter"))
    if not args.get("orderby"):
        args["orderby"] = "OrderDate desc"
    res = billit_request("GET", "/v1/orders", query=odata_query(args), party_id=a.get("party_id"))
    return page(res, summarize_order, a.get("compact", True))


def t_get_order(a):
    return billit_request("GET", f"/v1/orders/{int(a['order_id'])}", party_id=a.get("party_id"))


def t_list_parties(a):
    args = dict(a)
    if a.get("party_type"):
        args["filter"] = and_filter(f"PartyType eq '{a['party_type']}'", a.get("filter"))
    res = billit_request("GET", "/v1/parties", query=odata_query(args), party_id=a.get("party_id"))
    return page(res, summarize_party, a.get("compact", True))


def t_get_party(a):
    return billit_request("GET", f"/v1/parties/{int(a['id'])}", party_id=a.get("party_id"))


def t_list_products(a):
    res = billit_request("GET", "/v1/products", query=odata_query(a), party_id=a.get("party_id"))
    return page(res, lambda x: x, False)


def t_peppol_check(a):
    ident = urllib.parse.quote(a["identifier"].replace(" ", "").replace(".", ""), safe=":")
    return billit_request("GET", f"/v1/peppol/participantInformation/{ident}", auth=False)


def t_company_search(a):
    kw = urllib.parse.quote(a["keywords"], safe="")
    return billit_request("GET", f"/v1/misc/companysearch/{kw}", party_id=a.get("party_id"))


def t_download_file(a):
    res = billit_request("GET", f"/v1/files/{a['file_id']}", party_id=a.get("party_id"))
    content = res.get("FileContent") if isinstance(res, dict) else None
    if not content:
        return res
    name = res.get("FileName") or f"{a['file_id']}.bin"
    target = a.get("save_to") or os.path.join(os.getcwd(), name)
    if os.path.isdir(target):
        target = os.path.join(target, name)
    with open(target, "wb") as fh:
        fh.write(base64.b64decode(content))
    return {"saved_to": os.path.abspath(target), "FileName": name, "MimeType": res.get("MimeType")}


def t_create_order(a):
    order = a["order"]
    if isinstance(order, str):
        order = json.loads(order)
    headers = {"Idempotent-Key": a.get("idempotency_key") or str(uuid.uuid4())}
    res = billit_request("POST", "/v1/orders", body=order, party_id=a.get("party_id"), extra_headers=headers)
    return {"created_order_id": res, "environment": ENV,
            "next": "Inspect with billit_get_order; send with billit_send_orders after the user confirms."}


def t_update_order(a):
    changes = a["changes"]
    if isinstance(changes, str):
        changes = json.loads(changes)
    return billit_request("PATCH", f"/v1/orders/{int(a['order_id'])}", body=changes, party_id=a.get("party_id"))


def t_delete_order(a):
    return billit_request("DELETE", f"/v1/orders/{int(a['order_id'])}", party_id=a.get("party_id"))


def t_send_orders(a):
    body = {"OrderIDs": [int(i) for i in a["order_ids"]], "TransportType": a["transport_type"]}
    return billit_request("POST", "/v1/orders/commands/send", body=body, party_id=a.get("party_id"))


def t_add_payment(a):
    body = {"Amount": a["amount"], "Date": a["date"], "Description": a.get("description", "")}
    return billit_request("POST", f"/v1/orders/{int(a['order_id'])}/payments", body=body, party_id=a.get("party_id"))


def t_upsert_party(a):
    party = a["party"]
    if isinstance(party, str):
        party = json.loads(party)
    return billit_request("POST", "/v1/parties", body=party, party_id=a.get("party_id"))


def t_raw_request(a):
    method = a["method"].upper()
    if READ_ONLY and method != "GET":
        raise BillitError("Read-only mode (BILLIT_READ_ONLY=true): only GET requests are allowed.")
    body = a.get("body")
    if isinstance(body, str) and body.strip():
        body = json.loads(body)
    return billit_request(method, a["path"], query=a.get("query") or None, body=body,
                          party_id=a.get("party_id"))


# --------------------------------------------------------------------------- bank / CODA


def fetch_all(path, query, party_id, max_pages=25):
    """Follow Billit paging ($skip, page size 120) and return all Items."""
    items, skip = [], 0
    for _ in range(max_pages):
        q = dict(query)
        if skip:
            q["$skip"] = skip
        res = billit_request("GET", path, query=q, party_id=party_id)
        batch = (res or {}).get("Items") or [] if isinstance(res, dict) else []
        items.extend(batch)
        if not batch or not (isinstance(res, dict) and res.get("NextPageLink")):
            break
        skip += len(batch)
    return items


TX_KEYS = ("value_date", "amount", "counterparty_name", "counterparty_account", "structured_reference",
           "communication", "info", "client_reference", "bank_reference", "transaction_code", "is_detail")


def t_read_coda(a):
    files = coda.coda_files(a["path"])
    if not files:
        raise BillitError(f"No CODA files found at {a['path']}")
    search = (a.get("search") or "").lower()
    direction = a.get("direction")
    out = []
    for f in files:
        try:
            statements = coda.read_coda_file(f)
        except (OSError, ValueError) as e:
            out.append({"file": f, "error": str(e)})
            continue
        for st in statements:
            txs = st.pop("transactions")
            if not st.get("free_messages"):
                st.pop("free_messages", None)
            if a.get("include_transactions", True):
                sel = []
                for t in txs:
                    if t["is_detail"] and not a.get("include_details"):
                        continue
                    if direction == "credit" and t["amount"] <= 0 or direction == "debit" and t["amount"] >= 0:
                        continue
                    if search and search not in json.dumps(t, ensure_ascii=False).lower():
                        continue
                    sel.append({k: t[k] for k in TX_KEYS if t.get(k) not in (None, False, "")})
                st["transactions"] = sel
            out.append(st)
    return {"statements": out, "files": len(files)}


def summarize_tx(t):
    keys = ("BankAccountTransactionID", "ValueDate", "TotalAmount", "Currency", "NameCounterParty",
            "IBANCounterParty", "Description", "FreeMessage", "ClientReference", "BankReference",
            "IBAN", "Note", "AssignedEntities")
    return {k: t.get(k) for k in keys if t.get(k) not in (None, "", [])}


def t_list_transactions(a):
    extra = []
    if a.get("date_from"):
        extra.append(f"ValueDate ge DateTime'{a['date_from']}'")
    if a.get("date_to"):
        extra.append(f"ValueDate le DateTime'{a['date_to']}'")
    args = dict(a)
    args["filter"] = and_filter(*extra, a.get("filter"))
    if not args.get("orderby"):
        args["orderby"] = "ValueDate desc"
    res = billit_request("GET", "/v1/financialTransactions", query=odata_query(args), party_id=a.get("party_id"))
    return page(res, summarize_tx, a.get("compact", True))


def t_import_coda(a):
    files = coda.coda_files(a["path"])
    if not files:
        raise BillitError(f"No CODA files found at {a['path']}")
    results = []
    for f in files:
        try:
            statements = coda.read_coda_file(f)  # validate before uploading
        except (OSError, ValueError) as e:
            results.append({"file": f, "status": "skipped", "reason": str(e)})
            continue
        with open(f, "rb") as fh:
            content = base64.b64encode(fh.read()).decode("ascii")
        body = {"FileName": os.path.basename(f), "MimeType": "text/plain", "FileContent": content}
        try:
            res = billit_request("POST", "/v1/financialTransactions/importFile", body=body,
                                 party_id=a.get("party_id"))
            status = "imported"
        except BillitError as e:
            res, status = str(e), "error"
        results.append({
            "file": f, "status": status, "response": res,
            "statements": [{"account": s.get("account"), "statement_sequence": s.get("statement_sequence"),
                            "transactions": s.get("transaction_count"), "new_balance": s.get("new_balance"),
                            "new_balance_date": s.get("new_balance_date")} for s in statements],
        })
    return {"environment": ENV, "results": results}


def _digits(x):
    return re.sub(r"\D", "", str(x or ""))


def _name_tokens(x):
    stop = {"nv", "bv", "bvba", "sa", "srl", "sprl", "vzw", "cv", "comm", "v", "the", "de", "het", "en"}
    return {w for w in re.findall(r"[a-z0-9]{3,}", str(x or "").lower()) if w not in stop}


def t_match_payments(a):
    party = a.get("party_id")
    # 1. bank transactions: from CODA file(s) or from Billit
    txs = []
    if a.get("coda_path"):
        for f in coda.coda_files(a["coda_path"]):
            for st in coda.read_coda_file(f):
                for t in st["transactions"]:
                    if t["is_detail"]:
                        continue
                    txs.append({
                        "source": os.path.basename(f), "date": t["value_date"] or t["entry_date"],
                        "amount": t["amount"], "counterparty": t["counterparty_name"],
                        "account": t["counterparty_account"], "ogm": t["structured_reference"],
                        "text": " ".join(filter(None, [t["communication"], t["info"], t["client_reference"]])),
                    })
    else:
        q = {}
        flt = []
        if a.get("date_from"):
            flt.append(f"ValueDate ge DateTime'{a['date_from']}'")
        if a.get("date_to"):
            flt.append(f"ValueDate le DateTime'{a['date_to']}'")
        if flt:
            q["$filter"] = " and ".join(flt)
        for t in fetch_all("/v1/financialTransactions", q, party):
            text = " ".join(filter(None, [t.get("Description"), t.get("FreeMessage"), t.get("ClientReference")]))
            txs.append({
                "source": f"billit:{t.get('BankAccountTransactionID')}", "date": (t.get("ValueDate") or "")[:10],
                "amount": t.get("TotalAmount") or 0, "counterparty": t.get("NameCounterParty"),
                "account": t.get("IBANCounterParty"), "ogm": coda.find_ogm(text), "text": text,
            })

    # 2. open invoices / credit notes (sales and purchases)
    orders = fetch_all("/v1/orders", {"$filter": "Paid eq false"}, party)
    orders = [o for o in orders if (o.get("ToPay") or 0) != 0]
    by_ogm = {}
    for o in orders:
        d = _digits(o.get("PaymentReference"))
        if len(d) == 12:
            by_ogm.setdefault(d, []).append(o)

    tol = float(a.get("amount_tolerance", 0.01))
    matches, unmatched, used = [], [], set()
    for t in txs:
        amt = round(float(t["amount"]), 2)
        if amt == 0:
            continue
        direction = "Income" if amt > 0 else "Cost"
        cands = [o for o in orders if o.get("OrderDirection") == direction and o["OrderID"] not in used]
        hit, how = None, None
        if t["ogm"]:
            same = [o for o in by_ogm.get(_digits(t["ogm"]), []) if o in cands]
            if same:
                hit, how = same[0], "structured reference"
        if not hit:
            text_digits = _digits(t["text"])
            text_norm = norm(t["text"])
            for o in cands:
                num = norm(o.get("OrderNumber"))
                if len(num) >= 4 and (num in text_norm or (num.isdigit() and num in text_digits)):
                    hit, how = o, "invoice number in communication"
                    break
        if not hit:
            same_amt = [o for o in cands if abs(abs(amt) - abs(o.get("ToPay") or 0)) <= tol]
            tokens = _name_tokens(t["counterparty"]) | _name_tokens(t["text"])
            named = [o for o in same_amt if tokens & _name_tokens(((o.get("CounterParty") or {}).get("DisplayName")))]
            if len(named) == 1:
                hit, how = named[0], "amount + counterparty name"
            elif len(same_amt) == 1 and a.get("allow_amount_only"):
                hit, how = same_amt[0], "amount only (check!)"
        if not hit:
            unmatched.append(t)
            continue
        used.add(hit["OrderID"])
        to_pay = abs(hit.get("ToPay") or 0)
        paid = abs(amt)
        coverage = "full" if abs(paid - to_pay) <= tol else ("partial" if paid < to_pay else "overpaid")
        matches.append({
            "match": how,
            "coverage": coverage,
            "transaction": {k: t[k] for k in ("source", "date", "amount", "counterparty", "ogm") if t.get(k)},
            "order": {"OrderID": hit["OrderID"], "OrderNumber": hit.get("OrderNumber"),
                      "Direction": hit.get("OrderDirection"), "Type": hit.get("OrderType"),
                      "CounterParty": (hit.get("CounterParty") or {}).get("DisplayName"),
                      "ToPay": hit.get("ToPay"), "PaymentReference": hit.get("PaymentReference")},
            "suggested_action": {"tool": "billit_add_payment",
                                 "arguments": {"order_id": hit["OrderID"], "amount": paid, "date": t["date"],
                                               "description": f"Bank {t['source']}"}},
        })
    return {
        "note": "Proposals only — nothing was changed. Confirm with the user before calling billit_add_payment.",
        "transactions_checked": len(txs), "open_documents": len(orders),
        "matches": matches,
        "unmatched_count": len(unmatched),
        "unmatched": unmatched[: int(a.get("max_unmatched", 30))],
    }


# --------------------------------------------------------------------------- tool registry


def tool(name, description, props, required, fn, write=False):
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {**props, **PARTY_ARG}, "required": required},
        "annotations": {"readOnlyHint": not write, "destructiveHint": write},
        "_fn": fn,
        "_write": write,
    }


TOOLS = [
    tool("billit_account_info",
         "Get the Billit account information: the current user and the companies (with PartyID) it can act for.",
         {}, [], t_account_info),
    tool("billit_list_orders",
         "List invoices / credit notes / quotes (sales and purchase). Returns a compact summary per document "
         "(number, dates, counterparty, totals, paid/to pay, status). Supports convenience filters plus raw OData.",
         {
             "direction": {"type": "string", "enum": ["Income", "Cost"], "description": "Income = sales, Cost = purchase"},
             "order_type": {"type": "string", "description": "e.g. Invoice, CreditNote, Offer"},
             "unpaid_only": {"type": "boolean"},
             "date_from": {"type": "string", "description": "YYYY-MM-DD (OrderDate >=)"},
             "date_to": {"type": "string", "description": "YYYY-MM-DD (OrderDate <=)"},
             "compact": {"type": "boolean", "description": "Default true; false returns the raw list items"},
             **ODATA_ARGS,
         }, [], t_list_orders),
    tool("billit_get_order", "Get one order/invoice in full detail (lines, VAT, payment and delivery status, files).",
         {"order_id": {"type": "integer"}}, ["order_id"], t_get_order),
    tool("billit_list_parties", "List customers and/or suppliers.",
         {"party_type": {"type": "string", "enum": ["Customer", "Supplier"]},
          "compact": {"type": "boolean"}, **ODATA_ARGS}, [], t_list_parties),
    tool("billit_get_party", "Get one customer/supplier in detail.",
         {"id": {"type": "integer", "description": "PartyID of the customer/supplier"}}, ["id"], t_get_party),
    tool("billit_list_products", "List products in Billit.", dict(ODATA_ARGS), [], t_list_products),
    tool("billit_peppol_check",
         "Check whether a company can receive e-invoices over Peppol. Accepts a VAT number (BE0123456789), "
         "a Belgian company number, or scheme:identifier (e.g. 0088:5430003799999).",
         {"identifier": {"type": "string"}}, ["identifier"], t_peppol_check),
    tool("billit_company_search", "Search companies (Belgian registry) by name or VAT number.",
         {"keywords": {"type": "string"}}, ["keywords"], t_company_search),
    tool("billit_download_file",
         "Download a Billit file (invoice PDF, UBL, attachment) by FileID and save it to disk.",
         {"file_id": {"type": "string"},
          "save_to": {"type": "string", "description": "File or directory path; defaults to the current directory"}},
         ["file_id"], t_download_file),
    tool("billit_raw_request",
         "Call any Billit API endpoint directly (see https://api.billit.be/swagger/ui/index). "
         "Use for things the other tools don't cover, e.g. GET /v1/reports or GET /v1/peppol/inbox.",
         {"method": {"type": "string", "enum": ["GET", "POST", "PATCH", "PUT", "DELETE"]},
          "path": {"type": "string", "description": "e.g. /v1/reports"},
          "query": {"type": "object", "description": "Query parameters"},
          "body": {"type": "object", "description": "JSON body"}},
         ["method", "path"], t_raw_request),
    tool("billit_read_coda",
         "Read Belgian CODA bank statement file(s) from disk (a .cod file or a folder of them) without uploading: "
         "account, old/new balance (with a balance check), and every transaction with date, amount, counterparty, "
         "IBAN, structured reference (+++.../.../...+++) and communication.",
         {"path": {"type": "string", "description": "CODA file or directory"},
          "direction": {"type": "string", "enum": ["credit", "debit"], "description": "Only incoming or outgoing money"},
          "search": {"type": "string", "description": "Only transactions containing this text"},
          "include_transactions": {"type": "boolean", "description": "Default true; false gives only statement totals"},
          "include_details": {"type": "boolean", "description": "Also list the detail lines of globalised (grouped) movements"}},
         ["path"], t_read_coda),
    tool("billit_list_transactions",
         "List bank transactions known in Billit (from imported CODA files or bank links).",
         {"date_from": {"type": "string", "description": "YYYY-MM-DD (ValueDate >=)"},
          "date_to": {"type": "string", "description": "YYYY-MM-DD (ValueDate <=)"},
          "compact": {"type": "boolean"}, **ODATA_ARGS}, [], t_list_transactions),
    tool("billit_match_payments",
         "Match bank transactions (from a CODA file, or from Billit for a date range) to unpaid sales and purchase "
         "invoices, using the structured payment reference, the invoice number in the communication, or amount + "
         "counterparty name. Read-only: returns proposals with a ready billit_add_payment call for each.",
         {"coda_path": {"type": "string", "description": "CODA file or folder; omit to use Billit's transactions"},
          "date_from": {"type": "string", "description": "YYYY-MM-DD, when using Billit's transactions"},
          "date_to": {"type": "string"},
          "amount_tolerance": {"type": "number", "description": "Default 0.01"},
          "allow_amount_only": {"type": "boolean", "description": "Also propose matches on a unique amount alone (less reliable)"},
          "max_unmatched": {"type": "integer"}},
         [], t_match_payments),
    # ---- write tools
    tool("billit_import_coda",
         "Upload CODA bank statement file(s) to Billit and import the transactions. Each file is validated locally "
         "first. Confirm with the user before calling.",
         {"path": {"type": "string", "description": "CODA file or directory"}}, ["path"], t_import_coda, write=True),
    tool("billit_create_order",
         "Create (or update, when OrderID is included) an invoice, credit note or quote. Does NOT send it. "
         "Pass the Billit order JSON, e.g. {\"OrderType\":\"Invoice\",\"OrderDirection\":\"Income\",\"OrderNumber\":\"2026-001\","
         "\"OrderDate\":\"2026-11-09\",\"ExpiryDate\":\"2026-12-09\",\"Customer\":{\"Name\":\"Acme\",\"VATNumber\":\"BE0123456789\","
         "\"PartyType\":\"Customer\",\"Addresses\":[...]},\"OrderLines\":[{\"Quantity\":1,\"UnitPriceExcl\":100,"
         "\"Description\":\"Consultancy\",\"VATPercentage\":21}]}. An Idempotent-Key header is added automatically.",
         {"order": {"type": "object"}, "idempotency_key": {"type": "string"}}, ["order"], t_create_order, write=True),
    tool("billit_update_order", "Patch fields of an existing order (e.g. {\"Paid\": true, \"PaidDate\": \"2026-11-09\"}).",
         {"order_id": {"type": "integer"}, "changes": {"type": "object"}}, ["order_id", "changes"], t_update_order, write=True),
    tool("billit_delete_order", "Delete an order (only possible for documents that are not sent/booked).",
         {"order_id": {"type": "integer"}}, ["order_id"], t_delete_order, write=True),
    tool("billit_send_orders",
         "SEND one or more invoices to the customer via Peppol, email (SMTP), letter, ... "
         "This is irreversible on production: always confirm with the user first.",
         {"order_ids": {"type": "array", "items": {"type": "integer"}},
          "transport_type": {"type": "string", "enum": ["Peppol", "SMTP", "Letter", "SDI", "KSeF", "Chorus", "Anaf", "OSA", "SAT", "MyInvois"]}},
         ["order_ids", "transport_type"], t_send_orders, write=True),
    tool("billit_add_payment", "Register a (partial) payment on an order.",
         {"order_id": {"type": "integer"}, "amount": {"type": "number"},
          "date": {"type": "string", "description": "YYYY-MM-DD"}, "description": {"type": "string"}},
         ["order_id", "amount", "date"], t_add_payment, write=True),
    tool("billit_upsert_party", "Create a customer/supplier, or update one when PartyID is included in the JSON.",
         {"party": {"type": "object"}}, ["party"], t_upsert_party, write=True),
]

if READ_ONLY:
    TOOLS = [t for t in TOOLS if not t["_write"]]
TOOL_BY_NAME = {t["name"]: t for t in TOOLS}


def public_tool(t):
    return {k: v for k, v in t.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- MCP protocol


def text_result(obj, is_error=False):
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=1, default=str)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + f"\n... [truncated, {len(text)} chars total — narrow the query with filter/top]"
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle(msg):
    method = msg.get("method")
    params = msg.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                f"Billit API ({ENV}, {BASE_URL}). "
                + ("Read-only mode. " if READ_ONLY else "")
                + "Amounts are EUR unless Currency says otherwise. Never send invoices "
                  "or change data without explicit user confirmation."
            ),
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [public_tool(t) for t in TOOLS]}
    if method == "tools/call":
        t = TOOL_BY_NAME.get(params.get("name"))
        if not t:
            return text_result(f"Unknown tool: {params.get('name')}", True)
        try:
            return text_result(t["_fn"](params.get("arguments") or {}))
        except BillitError as e:
            return text_result(str(e), True)
        except OSError as e:
            return text_result(f"File error: {e}", True)
        except (KeyError, ValueError, TypeError) as e:
            return text_result(f"Invalid arguments: {e!r}", True)
    raise LookupError(method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:  # notification
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except LookupError:
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32601, "message": f"Method not found: {msg.get('method')}"}}
        except Exception as e:  # never crash the server
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
