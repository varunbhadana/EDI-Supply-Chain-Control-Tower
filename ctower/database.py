import sqlite3
from . import config


def connect(path=config.DB_PATH):
    return sqlite3.connect(path)


def build_database(tables, path=config.DB_PATH):
    """Recreate the SQLite file from schema.sql and load the parsed tables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = connect(path)
    conn.executescript((config.ROOT / "sql" / "schema.sql").read_text())
    # parents first so foreign keys make sense
    for name in ["purchase_orders", "po_lines", "acknowledgements",
                 "shipments", "shipment_events", "invoices"]:
        tables[name].to_sql(name, conn, if_exists="append", index=False)
    conn.commit()
    return conn
