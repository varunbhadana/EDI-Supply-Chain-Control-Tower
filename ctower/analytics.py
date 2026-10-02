"""Joins the EDI tables into one row per PO and computes KPIs and scorecards."""
import pandas as pd


def order_table(conn):
    po = pd.read_sql("SELECT * FROM purchase_orders", conn, parse_dates=["po_date", "requested_date"])

    lines = pd.read_sql("SELECT po_number, qty_ordered, unit_price FROM po_lines", conn)
    lines["value"] = lines.qty_ordered * lines.unit_price
    lines = lines.groupby("po_number").agg(qty_ordered=("qty_ordered", "sum"),
                                           ordered_value=("value", "sum"),
                                           n_lines=("qty_ordered", "size")).reset_index()

    ack = pd.read_sql("SELECT * FROM acknowledgements", conn, parse_dates=["promised_ship_date"])
    ack = ack.groupby("po_number").agg(qty_confirmed=("qty_confirmed", "sum"),
                                       promised_ship_date=("promised_ship_date", "max"),
                                       ack_changed=("ack_status", lambda s: int((s != "IA").any()))).reset_index()

    ship = pd.read_sql("SELECT * FROM shipments", conn, parse_dates=["ship_date"])
    ev = pd.read_sql("SELECT * FROM shipment_events", conn, parse_dates=["event_date"])
    delivered = (ev[ev.status_code == "D1"].groupby("asn_number").event_date.max()
                 .rename("delivery_date").reset_index())
    last = (ev.sort_values(["asn_number", "seq"]).groupby("asn_number").tail(1)
            [["asn_number", "status_code", "location"]]
            .rename(columns={"status_code": "last_status", "location": "last_location"}))

    inv = pd.read_sql("SELECT * FROM invoices", conn, parse_dates=["invoice_date"])

    o = (po.merge(lines, on="po_number", how="left")
           .merge(ack, on="po_number", how="left")
           .merge(ship, on="po_number", how="left")
           .merge(delivered, on="asn_number", how="left")
           .merge(last, on="asn_number", how="left")
           .merge(inv, on="po_number", how="left"))

    o["status"] = "Open"
    o.loc[o.ship_date.notna(), "status"] = "In transit"
    o.loc[o.delivery_date.notna(), "status"] = "Delivered"

    days = lambda a, b: (o[a] - o[b]).dt.days
    o["delay_days"] = days("delivery_date", "requested_date")
    o["is_late"] = (o.delay_days > 0).astype(float).where(o.delay_days.notna())
    o["lead_time_days"] = days("delivery_date", "po_date")
    o["transit_days"] = days("delivery_date", "ship_date")
    o["ship_delay_days"] = days("ship_date", "promised_ship_date")
    o["slack_days"] = days("requested_date", "promised_ship_date")
    o["ship_month"] = o.ship_date.dt.month
    o["ack_short_pct"] = 1 - o.qty_confirmed / o.qty_ordered
    o["ship_short_pct"] = 1 - o.qty_shipped / o.qty_ordered
    o["expected_invoice"] = o.ordered_value * o.qty_shipped / o.qty_ordered
    o["invoice_var_pct"] = (o.invoice_amount - o.expected_invoice) / o.expected_invoice
    o["invoice_qty_diff"] = o.qty_invoiced - o.qty_shipped
    return o


def kpis(o):
    d = o[o.status == "Delivered"]
    inv = o[o.invoice_number.notna()]
    bad_inv = ((inv.invoice_qty_diff != 0) | (inv.invoice_var_pct.abs() > 0.01)).sum()
    out = {
        "orders_total": int(len(o)),
        "open_not_shipped": int((o.status == "Open").sum()),
        "in_transit": int((o.status == "In transit").sum()),
        "delivered": int(len(d)),
        "on_time_delivery_pct": round(100 * (d.delay_days <= 0).mean(), 1) if len(d) else None,
        "avg_delay_days_late_orders": round(d.loc[d.delay_days > 0, "delay_days"].mean(), 1) if len(d) else None,
        "avg_lead_time_days": round(d.lead_time_days.mean(), 1) if len(d) else None,
        "avg_transit_days": round(d.transit_days.mean(), 1) if len(d) else None,
        "fill_rate_pct": round(100 * o.qty_shipped.sum() / o.loc[o.qty_shipped.notna(), "qty_ordered"].sum(), 1),
        "invoice_accuracy_pct": round(100 * (1 - bad_inv / max(len(inv), 1)), 1),
    }
    if "delay_prob" in o:
        risky = o[(o.status == "In transit") & (o.delay_prob >= 0.4)]
        out["shipments_at_risk"] = int(len(risky))
        out["value_at_risk_eur"] = round(float(risky.ordered_value.sum()), 0)
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in out.items()}


def supplier_scorecard(o):
    d = o[o.status == "Delivered"]
    g = d.groupby(["supplier_id", "supplier_name"])
    s = g.agg(orders=("po_number", "size"),
              otd_pct=("delay_days", lambda x: 100 * (x <= 0).mean()),
              avg_delay_days=("delay_days", lambda x: x.clip(lower=0).mean()),
              avg_lead_time=("lead_time_days", "mean")).reset_index()
    fill = d.groupby("supplier_id").apply(lambda x: 100 * x.qty_shipped.sum() / x.qty_ordered.sum(),
                                          include_groups=False).rename("fill_rate_pct")
    bad = d[d.invoice_number.notna()].groupby("supplier_id").apply(
        lambda x: 100 * ((x.invoice_qty_diff != 0) | (x.invoice_var_pct.abs() > 0.01)).mean(),
        include_groups=False).rename("invoice_error_pct")
    s = s.merge(fill, on="supplier_id").merge(bad, on="supplier_id", how="left").fillna({"invoice_error_pct": 0})
    # simple weighted score, weights chosen by me: delivery matters most
    s["score"] = (0.5 * s.otd_pct + 0.3 * s.fill_rate_pct + 0.2 * (100 - s.invoice_error_pct)).round(1)
    return s.sort_values("score").round(1).reset_index(drop=True)


def carrier_scorecard(o):
    d = o[o.status == "Delivered"].copy()
    return (d.groupby(["carrier", "mode"]).agg(shipments=("po_number", "size"),
                                              otd_pct=("delay_days", lambda x: 100 * (x <= 0).mean()),
                                              avg_transit_days=("transit_days", "mean"))
              .round(1).reset_index().sort_values("otd_pct"))


def monthly_otd(o):
    d = o[o.status == "Delivered"].copy()
    d["month"] = d.delivery_date.dt.to_period("M").astype(str)
    return (d.groupby("month").agg(deliveries=("po_number", "size"),
                                   otd_pct=("delay_days", lambda x: round(100 * (x <= 0).mean(), 1)))
              .reset_index())
