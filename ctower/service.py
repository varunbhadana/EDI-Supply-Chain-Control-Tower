"""Read-side access to the finished database. Used by the API and the dashboard."""
import json

import pandas as pd

from . import analytics, config, database

DATE_COLS = ["po_date", "requested_date", "promised_ship_date", "ship_date",
             "delivery_date", "invoice_date"]


class ControlTower:
    def __init__(self, path=config.DB_PATH):
        conn = database.connect(path)
        self.orders = pd.read_sql("SELECT * FROM order_facts", conn, parse_dates=DATE_COLS)
        self.exceptions = pd.read_sql("SELECT * FROM exceptions", conn)
        conn.close()

    def kpis(self):
        return analytics.kpis(self.orders)

    def suppliers(self):
        return analytics.supplier_scorecard(self.orders)

    def carriers(self):
        return analytics.carrier_scorecard(self.orders)

    def monthly_otd(self):
        return analytics.monthly_otd(self.orders)

    def in_transit(self):
        d = self.orders[self.orders.status == "In transit"]
        return d.sort_values("delay_prob", ascending=False)

    def order(self, po_number):
        r = self.orders[self.orders.po_number == po_number]
        return None if r.empty else r.iloc[0]

    def order_exceptions(self, po_number):
        return self.exceptions[self.exceptions.po_number == po_number]

    def model_metrics(self):
        if config.METRICS_PATH.exists():
            return json.loads(config.METRICS_PATH.read_text())
        return {}
