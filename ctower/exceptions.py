"""Rule-based exception engine. Each rule returns a type, severity and a readable detail."""
import pandas as pd

from . import config

SEV_RANK = {"High": 0, "Medium": 1, "Low": 2}


def find_exceptions(o, as_of=config.AS_OF):
    as_of = pd.Timestamp(as_of)
    rows = []

    def add(r, typ, sev, detail, value):
        rows.append({"po_number": r.po_number, "supplier_name": r.supplier_name,
                     "exception_type": typ, "severity": sev, "detail": detail,
                     "value_eur": round(float(value), 2)})

    for r in o.itertuples():
        if r.status == "Delivered" and r.delay_days > 0:
            sev = "High" if r.delay_days >= 5 else "Medium" if r.delay_days >= 2 else "Low"
            add(r, "LATE_DELIVERY", sev,
                f"Delivered {int(r.delay_days)} day(s) after requested date "
                f"(shipped {int(r.ship_delay_days)} day(s) after promise, carrier {r.carrier})", r.ordered_value)

        if r.status == "In transit" and r.delay_prob >= config.RISK_MEDIUM:
            sev = "High" if r.delay_prob >= config.RISK_HIGH else "Medium"
            add(r, "AT_RISK_SHIPMENT", sev,
                f"{r.delay_prob:.0%} delay probability, {r.mode} via {r.carrier} to {r.destination}, "
                f"last status {r.last_status}", r.ordered_value)

        if r.status == "Open" and r.promised_ship_date < as_of:
            over = (as_of - r.promised_ship_date).days
            sev = "High" if over >= 7 else "Medium" if over >= 3 else "Low"
            add(r, "OVERDUE_SHIPMENT", sev,
                f"No ASN received, promised ship date was {over} day(s) ago", r.ordered_value)

        if r.status != "Open" and r.ship_short_pct > config.SHORT_SHIP_TOL:
            sev = "High" if r.ship_short_pct > 0.15 else "Medium"
            add(r, "SHORT_SHIPMENT", sev,
                f"Shipped {int(r.qty_shipped)} of {int(r.qty_ordered)} units ({r.ship_short_pct:.0%} short)",
                r.ordered_value * r.ship_short_pct)

        if pd.notna(r.invoice_number):
            if r.invoice_qty_diff != 0:
                add(r, "INVOICE_QTY_MISMATCH", "High" if abs(r.invoice_qty_diff) > 100 else "Medium",
                    f"Invoice {r.invoice_number} bills {int(r.qty_invoiced)} units, ASN shows {int(r.qty_shipped)}",
                    abs(r.invoice_amount - r.expected_invoice))
            elif abs(r.invoice_var_pct) > config.INVOICE_PRICE_TOL:
                add(r, "INVOICE_PRICE_MISMATCH", "High" if abs(r.invoice_var_pct) > 0.05 else "Medium",
                    f"Invoice {r.invoice_number} is {r.invoice_var_pct:+.1%} versus PO price",
                    abs(r.invoice_amount - r.expected_invoice))
        elif r.status == "Delivered" and (as_of - r.delivery_date).days > 14:
            add(r, "MISSING_INVOICE", "Low",
                f"Delivered {(as_of - r.delivery_date).days} days ago, no invoice received", r.ordered_value)

    cols = ["po_number", "supplier_name", "exception_type", "severity", "detail", "value_eur"]
    ex = pd.DataFrame(rows, columns=cols)
    ex["rank"] = ex.severity.map(SEV_RANK)
    return ex.sort_values(["rank", "value_eur"], ascending=[True, False]).drop(columns="rank").reset_index(drop=True)
