"""Creates simulated X12 EDI files (850, 855, 856, 214, 810).

The buyer is a fictional German manufacturer ("Nordtrade Industrial GmbH")
ordering parts from suppliers in Europe and Asia. Delays, short shipments and
invoice errors are random but depend on supplier reliability, carrier, mode and
season, so the ML model later has something real to learn.
"""
import random
from datetime import timedelta, datetime
from . import config

BUYER_ID, BUYER_NAME = "NORDTRADE", "Nordtrade Industrial GmbH"
START = config.AS_OF.replace(month=1, day=5)

# transit = planned transit days, rel = supplier reliability (0-1)
SUPPLIERS = [
    dict(id="S01", name="Rhein Components GmbH",       city="Duisburg",  rel=0.93, mode="J", transit=2),
    dict(id="S02", name="Silesia Metalworks",          city="Katowice",  rel=0.88, mode="J", transit=3),
    dict(id="S03", name="Moravia Precision s.r.o.",    city="Brno",      rel=0.90, mode="J", transit=3),
    dict(id="S04", name="Lombardia Fasteners S.p.A.",  city="Milan",     rel=0.84, mode="J", transit=4),
    dict(id="S05", name="Anatolia Castings",           city="Izmir",     rel=0.72, mode="J", transit=7),
    dict(id="S06", name="Shenzhen Electro Parts",      city="Shenzhen",  rel=0.78, mode="O", transit=32),
    dict(id="S07", name="Ningbo Hydraulics",           city="Ningbo",    rel=0.70, mode="O", transit=33),
    dict(id="S08", name="Pune Forgings Pvt Ltd",       city="Mumbai",    rel=0.66, mode="O", transit=29),
    dict(id="S09", name="Chennai Auto Components",     city="Chennai",   rel=0.74, mode="O", transit=31),
    dict(id="S10", name="Hanoi Cable Systems",         city="Haiphong",  rel=0.62, mode="O", transit=34),
    dict(id="S11", name="Gdansk Polymers",             city="Gdansk",    rel=0.91, mode="J", transit=3),
    dict(id="S12", name="Kaohsiung Sensor Tech",       city="Kaohsiung", rel=0.82, mode="A", transit=5),
]
CARRIERS = {"J": [("NFRT", 0.92), ("BRLN", 0.85)],
            "O": [("HOLN", 0.80), ("PBSH", 0.72)],
            "A": [("SKLC", 0.90)]}
SKUS = [("BRK-2210", 4.80), ("VLV-0457", 12.40), ("CBL-9921", 2.35), ("SNS-1180", 18.90),
        ("FST-3302", 0.42), ("HYD-7765", 56.00), ("PCB-0031", 9.75), ("GSK-5540", 1.15)]
DCS = [("Hamburg DC", "DEHAM"), ("Frankfurt DC", "DEFRA"), ("Leipzig DC", "DELEJ")]


def d8(d):
    return d.strftime("%Y%m%d")


def seg(*parts):
    return "*".join(str(p) for p in parts) + "~"


def wrap(doc_type, ctrl, body):
    ctrl = f"{ctrl:04d}"
    return [seg("ST", doc_type, ctrl)] + body + [seg("SE", len(body) + 2, ctrl)]


def build_orders(rng, n):
    orders = []
    for i in range(1, n + 1):
        sup = rng.choice(SUPPLIERS)
        mode = sup["mode"]
        carrier, c_rel = rng.choice(CARRIERS[mode])
        po_date = START + timedelta(days=rng.randint(0, 250))
        prod_lead = rng.randint(10, 25) if mode == "O" else rng.randint(7, 21)
        requested = po_date + timedelta(days=prod_lead + sup["transit"] + 3)

        # supplier side
        ack_shift = rng.randint(1, 7) if rng.random() < (1 - sup["rel"]) * 1.2 else 0
        promised = po_date + timedelta(days=prod_lead + ack_shift)
        sup_delay = rng.randint(1, 8) if rng.random() < (1 - sup["rel"]) * 1.5 else 0
        ship = promised + timedelta(days=sup_delay)

        # carrier side (ocean gets worse in the summer peak)
        p_carrier = (1 - c_rel) * 1.5
        if mode == "O" and ship.month in (7, 8, 9):
            p_carrier *= 1.4
        car_delay = 0
        if rng.random() < p_carrier:
            car_delay = rng.randint(1, 9) if mode == "O" else rng.randint(1, 3)
        delivery = ship + timedelta(days=sup["transit"] + car_delay)

        # lines and quantities
        lines = []
        for ln in range(1, rng.choice([1, 1, 2, 3]) + 1):
            sku, base = rng.choice(SKUS)
            price = round(base * rng.uniform(0.95, 1.08), 2)
            qty = rng.randint(2, 60) * 50
            conf = qty if rng.random() > (1 - sup["rel"]) * 0.7 else int(qty * rng.uniform(0.8, 0.95))
            lines.append(dict(no=ln, sku=sku, price=price, qty=qty, conf=conf,
                              status="IA" if conf == qty else "IQ"))
        total_conf = sum(l["conf"] for l in lines)
        ship_ratio = 1.0
        if rng.random() < (1 - sup["rel"]) * 0.35:
            ship_ratio = rng.uniform(0.85, 0.98)
        qty_shipped = int(total_conf * ship_ratio)
        ordered_value = sum(l["qty"] * l["price"] for l in lines)
        avg_price = ordered_value / sum(l["qty"] for l in lines)

        # invoice behaviour
        qty_inv = qty_shipped
        if rng.random() < 0.05:
            qty_inv = total_conf  # supplier billed what was confirmed, not what shipped
        price_factor = rng.uniform(1.03, 1.08) if rng.random() < 0.04 else 1.0
        inv_amount = round(qty_inv * avg_price * price_factor, 2)
        inv_date = delivery + timedelta(days=rng.randint(1, 10))

        dest = rng.choice(DCS[:1] * 3 + DCS[1:]) if mode == "O" else rng.choice(DCS)
        orders.append(dict(
            po=f"4500{i:06d}", sup=sup, po_date=po_date, requested=requested,
            ack_date=po_date + timedelta(days=rng.randint(1, 2)), promised=promised,
            ship=ship, delivery=delivery, carrier=carrier, mode=mode, dest=dest,
            lines=lines, qty_shipped=qty_shipped, inv_qty=qty_inv,
            inv_amount=inv_amount, inv_no=f"INV{7000000 + i}", inv_date=inv_date,
            inv_sent=rng.random() > 0.03, transit=sup["transit"]))
    return orders


def make_850(o):
    body = [seg("BEG", "00", "SA", o["po"], "", d8(o["po_date"])),
            seg("N1", "BY", BUYER_NAME, "92", BUYER_ID),
            seg("N1", "SU", o["sup"]["name"], "92", o["sup"]["id"]),
            seg("DTM", "002", d8(o["requested"]))]
    for l in o["lines"]:
        body.append(seg("PO1", l["no"], l["qty"], "EA", f"{l['price']:.2f}", "", "VP", l["sku"]))
    body.append(seg("CTT", len(o["lines"])))
    return body


def make_855(o):
    body = [seg("BAK", "00", "AC", o["po"], d8(o["ack_date"])),
            seg("N1", "SU", o["sup"]["name"], "92", o["sup"]["id"])]
    for l in o["lines"]:
        body.append(seg("PO1", l["no"], l["qty"], "EA", f"{l['price']:.2f}", "", "VP", l["sku"]))
        body.append(seg("ACK", l["status"], l["conf"], "EA", "068", d8(o["promised"])))
    body.append(seg("CTT", len(o["lines"])))
    return body


def asn_no(o):
    return "ASN" + o["po"][-6:]


def make_856(o):
    return [seg("BSN", "00", asn_no(o), d8(o["ship"]), "0900"),
            seg("HL", 1, "", "S"),
            seg("TD5", "", "2", o["carrier"], o["mode"]),
            seg("N1", "SF", o["sup"]["city"]),
            seg("N1", "ST", o["dest"][0], "UN", o["dest"][1]),
            seg("DTM", "011", d8(o["ship"])),
            seg("HL", 2, 1, "O"),
            seg("PRF", o["po"]),
            seg("SN1", "", o["qty_shipped"], "EA"),
            seg("CTT", 2)]


def make_214(o, as_of):
    ev = [("AF", o["ship"], o["sup"]["city"])]
    mid = o["ship"] + timedelta(days=max(1, o["transit"] // 2))
    ev.append(("X6", mid, "En route"))
    ev.append(("D1", o["delivery"], o["dest"][0]))
    ev = [e for e in ev if e[1] <= as_of]
    body = [seg("B10", asn_no(o), asn_no(o), o["carrier"]), seg("L11", o["po"], "PO")]
    for n, (code, dt, loc) in enumerate(ev, 1):
        body += [seg("LX", n), seg("AT7", code, "NS", "", "", d8(dt), "1200"), seg("MS1", loc)]
    return body


def make_810(o):
    price = o["inv_amount"] / o["inv_qty"]
    return [seg("BIG", d8(o["inv_date"]), o["inv_no"], "", o["po"]),
            seg("N1", "RI", o["sup"]["name"], "92", o["sup"]["id"]),
            seg("IT1", 1, o["inv_qty"], "EA", f"{price:.4f}"),
            seg("TDS", int(round(o["inv_amount"] * 100)))]


def envelope(group, sets, stamp):
    out = [f"ISA*00*          *00*          *ZZ*{BUYER_ID:<15}*ZZ*{'PARTNERS':<15}*"
           f"{stamp:%y%m%d}*{stamp:%H%M}*U*00401*000000001*0*P*>~",
           seg("GS", group, BUYER_ID, "PARTNERS", d8(stamp), f"{stamp:%H%M}", 1, "X", "004010")]
    for s in sets:
        out += s
    out += [seg("GE", len(sets), 1), seg("IEA", 1, "000000001")]
    return "\n".join(out) + "\n"


def generate(out_dir=config.RAW_DIR, n=config.N_ORDERS, seed=config.SEED):
    rng = random.Random(seed)
    as_of = config.AS_OF
    orders = build_orders(rng, n)
    docs = {"850": [], "855": [], "856": [], "214": [], "810": []}
    c = dict.fromkeys(docs, 0)

    def add(t, body):
        c[t] += 1
        docs[t].append(wrap(t, c[t], body))

    for o in orders:
        if o["po_date"] <= as_of:
            add("850", make_850(o))
        if o["ack_date"] <= as_of:
            add("855", make_855(o))
        if o["ship"] <= as_of:
            add("856", make_856(o))
            add("214", make_214(o, as_of))
        if o["inv_sent"] and o["inv_date"] <= as_of:
            add("810", make_810(o))

    out_dir.mkdir(parents=True, exist_ok=True)
    groups = {"850": "PO", "855": "PR", "856": "SH", "214": "QM", "810": "IN"}
    stamp = datetime.combine(as_of, datetime.min.time()).replace(hour=8)
    for t, sets in docs.items():
        (out_dir / f"edi_{t}.edi").write_text(envelope(groups[t], sets, stamp))
    return c


if __name__ == "__main__":
    print(generate())
