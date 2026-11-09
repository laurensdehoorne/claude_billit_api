"""Parser for Belgian CODA bank statement files (version 2.x), standard library only.

A CODA file is plain text with fixed-width records of 128 characters. One file
can hold several statements (record 0 ... record 9). The record types used here:

  0   header                       1   old balance / account
  21  movement, part 1             22  movement, part 2
  23  movement, part 3 (counterparty)
  31/32/33  information records    4   free communication
  8   new balance                  9   trailer

Positions below are 0-based Python slices of the 1-based positions in the
Febelfin CODA 2.x specification.
"""

import os
import re
from datetime import datetime

STRUCTURED_TYPES = ("101", "102")  # Belgian structured payment reference (OGM/VCS)


def _date(text):
    text = text.strip()
    if not text or text == "000000":
        return None
    try:
        return datetime.strptime(text, "%d%m%y").date().isoformat()
    except ValueError:
        return None


def _amount(sign, digits):
    digits = digits.strip()
    if not digits:
        return 0.0
    value = int(digits) / 1000.0
    return -value if sign == "1" else value


def _clean(text):
    return re.sub(r"\s+", " ", text).strip()


def format_ogm(digits):
    digits = re.sub(r"\D", "", digits or "")
    if len(digits) != 12:
        return None
    return f"+++{digits[0:3]}/{digits[3:7]}/{digits[7:12]}+++"


def is_valid_ogm(digits):
    digits = re.sub(r"\D", "", digits or "")
    if len(digits) != 12:
        return False
    check = int(digits[:10]) % 97 or 97
    return check == int(digits[10:])


def find_ogm(*texts):
    """Find a valid structured payment reference (+++123/4567/89012+++) in free text."""
    for text in texts:
        if not text:
            continue
        # 12 digits as a standalone token, optionally written as 123/4567/89012 (with +++ or ***)
        for candidate in re.findall(r"(?<![\d/])\d{3}[/ .-]?\d{4}[/ .-]?\d{5}(?![\d/])", str(text)):
            digits = re.sub(r"\D", "", candidate)
            if is_valid_ogm(digits):
                return format_ogm(digits)
    return None


def _account(line, structure):
    """Account number and currency from record 1 (positions 6-42) or record 8 (5-41)."""
    if structure == "0":    # Belgian BBAN
        return line[0:12].strip(), line[13:16].strip()
    if structure == "1":    # foreign BBAN
        return line[0:34].strip(), line[34:37].strip()
    if structure == "2":    # Belgian IBAN
        return line[0:16].strip(), line[34:37].strip()
    return line[0:34].strip(), line[34:37].strip()   # "3": foreign IBAN


def parse_coda_text(text):
    statements = []
    st = None
    move = None
    info_target = None

    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        line = line.ljust(128)
        rec = line[0]

        if rec == "0":
            st = {
                "creation_date": _date(line[5:11]),
                "bank_id": line[11:14].strip(),
                "duplicate": line[16] == "D",
                "addressee": _clean(line[34:60]),
                "bic": line[60:71].strip(),
                "company_number": line[71:82].strip(),
                "version": line[127],
                "transactions": [],
                "free_messages": [],
            }
            statements.append(st)
            move = None
        elif st is None:
            raise ValueError("Not a CODA file: first record is not a header (record type 0).")
        elif rec == "1":
            structure = line[1]
            st["account"], st["currency"] = _account(line[5:42], structure)
            st["paper_sequence"] = line[2:5].strip()
            st["old_balance"] = _amount(line[42], line[43:58])
            st["old_balance_date"] = _date(line[58:64])
            st["account_holder"] = _clean(line[64:90])
            st["account_description"] = _clean(line[90:125])
            st["statement_sequence"] = line[125:128].strip()
        elif rec == "2":
            kind = line[1]
            if kind == "1":
                structured = line[61] == "1"
                comm_type = line[62:65] if structured else ""
                if structured and comm_type in STRUCTURED_TYPES:
                    communication = format_ogm(line[65:77]) or _clean(line[65:115])
                else:
                    communication = _clean(line[65:115] if structured else line[62:115])
                move = {
                    "sequence": line[2:6],
                    "detail": line[6:10],
                    "bank_reference": line[10:31].strip(),
                    "amount": _amount(line[31], line[32:47]),
                    "value_date": _date(line[47:53]),
                    "transaction_code": line[53:61],
                    "structured_reference": communication if structured and comm_type in STRUCTURED_TYPES else None,
                    "communication": communication,
                    "entry_date": _date(line[115:121]),
                    "globalisation_code": line[124].strip() or "0",
                    "counterparty_name": None,
                    "counterparty_account": None,
                    "counterparty_bic": None,
                    "client_reference": None,
                    "info": [],
                }
                st["transactions"].append(move)
                info_target = move
            elif kind == "2" and move is not None:
                extra = _clean(line[10:63])
                if extra and not move["structured_reference"]:
                    move["communication"] = _clean(move["communication"] + " " + extra)
                move["client_reference"] = line[63:98].strip() or None
                move["counterparty_bic"] = line[98:109].strip() or None
            elif kind == "3" and move is not None:
                if line[22] == " ":   # BBAN
                    move["counterparty_account"] = line[10:22].strip() or None
                else:                 # IBAN
                    move["counterparty_account"] = line[10:44].strip() or None
                move["counterparty_name"] = _clean(line[47:82]) or None
                extra = _clean(line[82:125])
                if extra and not move["structured_reference"]:
                    move["communication"] = _clean(move["communication"] + " " + extra)
        elif rec == "3":
            target = info_target
            if line[1] == "1":
                text_part = _clean(line[40:113])
            else:
                text_part = _clean(line[10:115])
            if target is not None and text_part:
                target["info"].append(text_part)
        elif rec == "4":
            msg = _clean(line[32:112])
            if msg:
                st["free_messages"].append(msg)
        elif rec == "8":
            st["new_balance"] = _amount(line[41], line[42:57])
            st["new_balance_date"] = _date(line[57:63])
        elif rec == "9":
            st["trailer_record_count"] = int(line[16:22] or 0) if line[16:22].strip().isdigit() else None
            st["trailer_debit"] = _amount("0", line[22:37])
            st["trailer_credit"] = _amount("0", line[37:52])

    if not statements:
        raise ValueError("Not a CODA file: no header record found.")
    for st in statements:
        if st.get("version") != "2":
            st["warning"] = f"CODA version '{st.get('version')}' — this parser supports version 2 only."

    for st in statements:
        _finish(st)
    return statements


def _finish(st):
    # Globalised movements: the detail lines (detail != 0000) repeat the global amount.
    # Only the top-level lines (detail 0000) count for the totals / balance check.
    for t in st["transactions"]:
        t["is_detail"] = t["detail"] != "0000"
        t["info"] = " | ".join(t["info"]) or None
        if not t["structured_reference"]:
            t["structured_reference"] = find_ogm(t["communication"], t["client_reference"])
        t["communication"] = t["communication"] or None
    top = [t for t in st["transactions"] if not t["is_detail"]]
    credit = round(sum(t["amount"] for t in top if t["amount"] > 0), 2)
    debit = round(-sum(t["amount"] for t in top if t["amount"] < 0), 2)
    st["total_credit"] = credit
    st["total_debit"] = debit
    st["transaction_count"] = len(top)
    if "old_balance" in st and "new_balance" in st:
        expected = round(st["old_balance"] + credit - debit, 2)
        st["balance_check"] = "ok" if abs(expected - st["new_balance"]) < 0.005 else (
            f"MISMATCH: old balance + movements = {expected}, new balance = {st['new_balance']}")


def read_coda_file(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    statements = parse_coda_text(text)
    for st in statements:
        st["file"] = os.path.abspath(path)
    return statements


def coda_files(path):
    """A single file, or every CODA-looking file in a directory."""
    path = os.path.expanduser(path)
    if os.path.isdir(path):
        out = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isfile(full) and (
                name.lower().endswith((".cod", ".coda", ".txt", ".cda")) or "coda" in name.lower()
            ):
                out.append(full)
        return out
    return [path]
