"""Small X12 parser for the five transaction sets used in this project.

It is not a full X12 implementation (no loops validation, no 997 handling),
but it checks the SE segment count and skips malformed sets instead of
crashing, which is how a real inbound EDI job should behave.
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
MODES = {"J": "Truck", "O": "Ocean", "A": "Air"}


class EDIError(Exception):
    pass


def _iso(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else None


def el(seg, i):
    return seg[i] if len(seg) > i else ""


def split_transactions(text):
    """Cut a raw EDI file into transaction sets (ST ... SE)."""
    flat = text.replace("\r", "").replace("\n", "")
    segs = [s.split("*") for s in flat.split("~") if s.strip()]
    docs, cur = [], None
    for s in segs:
        if s[0] == "ST":
            cur = {"type": el(s, 1), "control": el(s, 2), "segments": []}
        elif s[0] == "SE":
            if cur is None:
                raise EDIError("SE segment without matching ST")
            declared, actual = int(el(s, 1)), len(cur["segments"]) + 2
            if declared != actual:
                raise EDIError(f"set {cur['control']}: SE says {declared} segments, found {actual}")
            docs.append(cur)
            cur = None
        elif cur is not None:
            cur["segments"].append(s)
    return docs


def parse_850(doc):
    po, lines = {}, []
    for s in doc["segments"]:
        tag = s[0]
        if tag == "BEG":
            po["po_number"], po["po_date"] = el(s, 3), _iso(el(s, 5))
        elif tag == "N1" and el(s, 1) == "SU":
            po["supplier_name"], po["supplier_id"] = el(s, 2), el(s, 4)
        elif tag == "DTM" and el(s, 1) == "002":
            po["requested_date"] = _iso(el(s, 2))
        elif tag == "PO1":
            lines.append({"line_no": int(el(s, 1)), "sku": el(s, 7),
                          "qty_ordered": int(float(el(s, 2))), "unit_price": float(el(s, 4))})
    if not po.get("po_number"):
        raise EDIError("850 without BEG segment")
    for l in lines:
        l["po_number"] = po["po_number"]
    return po, lines


def parse_855(doc):
    po_number, ack_date, line_no, rows = "", None, None, []
    for s in doc["segments"]:
        if s[0] == "BAK":
            po_number, ack_date = el(s, 3), _iso(el(s, 4))
        elif s[0] == "PO1":
            line_no = int(el(s, 1))
        elif s[0] == "ACK":
            rows.append({"po_number": po_number, "line_no": line_no, "ack_status": el(s, 1),
                         "qty_confirmed": int(float(el(s, 2))),
                         "promised_ship_date": _iso(el(s, 5)), "ack_date": ack_date})
    if not po_number:
        raise EDIError("855 without BAK segment")
    return rows


def parse_856(doc):
    r = {}
    for s in doc["segments"]:
        t = s[0]
        if t == "BSN":
            r["asn_number"] = el(s, 2)
        elif t == "TD5":
            r["carrier"], r["mode"] = el(s, 3), MODES.get(el(s, 4), el(s, 4))
        elif t == "N1" and el(s, 1) == "SF":
            r["origin"] = el(s, 2)
        elif t == "N1" and el(s, 1) == "ST":
            r["destination"] = el(s, 2)
        elif t == "DTM" and el(s, 1) == "011":
            r["ship_date"] = _iso(el(s, 2))
        elif t == "PRF":
            r["po_number"] = el(s, 1)
        elif t == "SN1":
            r["qty_shipped"] = int(float(el(s, 2)))
    if "asn_number" not in r or "po_number" not in r:
        raise EDIError("856 missing BSN or PRF")
    return r


def parse_214(doc):
    asn, po, loc, seq, rows = "", "", "", 0, []
    pending = None
    for s in doc["segments"]:
        t = s[0]
        if t == "B10":
            asn = el(s, 2)
        elif t == "L11" and el(s, 2) == "PO":
            po = el(s, 1)
        elif t == "LX":
            seq = int(el(s, 1))
        elif t == "AT7":
            pending = {"asn_number": asn, "po_number": po, "seq": seq,
                       "status_code": el(s, 1), "event_date": _iso(el(s, 5)), "location": ""}
            rows.append(pending)
        elif t == "MS1" and pending is not None:
            pending["location"] = el(s, 1)
    if not asn:
        raise EDIError("214 without B10")
    return rows


def parse_810(doc):
    r = {}
    for s in doc["segments"]:
        t = s[0]
        if t == "BIG":
            r["invoice_date"], r["invoice_number"], r["po_number"] = _iso(el(s, 1)), el(s, 2), el(s, 4)
        elif t == "IT1":
            r["qty_invoiced"] = int(float(el(s, 2)))
        elif t == "TDS":
            r["invoice_amount"] = int(el(s, 1)) / 100
    if "invoice_number" not in r or "invoice_amount" not in r:
        raise EDIError("810 missing BIG or TDS")
    return r


def parse_all(raw_dir):
    """Parse every .edi file in raw_dir. Returns (dict of DataFrames, list of rejected sets)."""
    pos, lines, acks, ships, events, invs, rejected = [], [], [], [], [], [], []
    for path in sorted(Path(raw_dir).glob("*.edi")):
        try:
            docs = split_transactions(path.read_text())
        except EDIError as e:
            rejected.append((path.name, str(e)))
            log.warning("%s rejected: %s", path.name, e)
            continue
        for d in docs:
            try:
                if d["type"] == "850":
                    p, l = parse_850(d)
                    pos.append(p)
                    lines += l
                elif d["type"] == "855":
                    acks += parse_855(d)
                elif d["type"] == "856":
                    ships.append(parse_856(d))
                elif d["type"] == "214":
                    events += parse_214(d)
                elif d["type"] == "810":
                    invs.append(parse_810(d))
                else:
                    log.warning("unknown transaction set %s", d["type"])
            except (EDIError, ValueError) as e:
                rejected.append((f"{path.name}:{d['control']}", str(e)))
                log.warning("set %s in %s skipped: %s", d["control"], path.name, e)

    def frame(rows, key):
        return pd.DataFrame(rows).drop_duplicates(subset=key, keep="last").reset_index(drop=True)

    tables = {
        "purchase_orders": frame(pos, ["po_number"]),
        "po_lines": frame(lines, ["po_number", "line_no"]),
        "acknowledgements": frame(acks, ["po_number", "line_no"]),
        "shipments": frame(ships, ["asn_number"]),
        "shipment_events": frame(events, ["asn_number", "seq"]),
        "invoices": frame(invs, ["invoice_number"]),
    }
    return tables, rejected
