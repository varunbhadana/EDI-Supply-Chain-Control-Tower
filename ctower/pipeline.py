"""End-to-end run: generate EDI -> parse -> load DB -> analyse -> train -> score -> exceptions."""
import logging

from . import config, analytics, database, edi_parser, exceptions, generate_edi, model


def run(regenerate=True):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if regenerate:
        counts = generate_edi.generate()
        print("EDI documents written:", counts)

    tables, rejected = edi_parser.parse_all(config.RAW_DIR)
    print("Parsed rows:", {k: len(v) for k, v in tables.items()}, "| rejected sets:", len(rejected))

    conn = database.build_database(tables)
    orders = analytics.order_table(conn)

    pipe, metrics = model.train(orders)
    print(f"Model: AUC {metrics['roc_auc']}, precision {metrics['precision']}, recall {metrics['recall']}")

    orders = model.score(orders, pipe)
    ex = exceptions.find_exceptions(orders)
    print("Exceptions raised:", len(ex))

    orders.to_sql("order_facts", conn, if_exists="replace", index=False)
    ex.to_sql("exceptions", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()
    print("Database written to", config.DB_PATH)


if __name__ == "__main__":
    run()
