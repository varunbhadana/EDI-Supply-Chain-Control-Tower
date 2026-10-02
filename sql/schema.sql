-- Core tables filled from the parsed EDI documents.
-- Written in plain ANSI SQL so it also runs on PostgreSQL (psql -f sql/schema.sql).

CREATE TABLE purchase_orders (            -- EDI 850
    po_number       VARCHAR(20) PRIMARY KEY,
    po_date         DATE NOT NULL,
    supplier_id     VARCHAR(10) NOT NULL,
    supplier_name   VARCHAR(100) NOT NULL,
    requested_date  DATE NOT NULL
);

CREATE TABLE po_lines (                   -- EDI 850 PO1 segments
    po_number       VARCHAR(20) NOT NULL REFERENCES purchase_orders(po_number),
    line_no         INTEGER NOT NULL,
    sku             VARCHAR(20) NOT NULL,
    qty_ordered     INTEGER NOT NULL,
    unit_price      NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (po_number, line_no)
);

CREATE TABLE acknowledgements (           -- EDI 855
    po_number           VARCHAR(20) NOT NULL REFERENCES purchase_orders(po_number),
    line_no             INTEGER NOT NULL,
    ack_status          VARCHAR(2) NOT NULL,   -- IA accepted, IQ accepted with qty change
    qty_confirmed       INTEGER NOT NULL,
    promised_ship_date  DATE,
    ack_date            DATE,
    PRIMARY KEY (po_number, line_no)
);

CREATE TABLE shipments (                  -- EDI 856
    asn_number     VARCHAR(20) PRIMARY KEY,
    po_number      VARCHAR(20) NOT NULL REFERENCES purchase_orders(po_number),
    carrier        VARCHAR(10),
    mode           VARCHAR(10),
    origin         VARCHAR(50),
    destination    VARCHAR(50),
    ship_date      DATE,
    qty_shipped    INTEGER
);

CREATE TABLE shipment_events (            -- EDI 214 (AF departed, X6 in transit, D1 delivered)
    asn_number     VARCHAR(20) NOT NULL REFERENCES shipments(asn_number),
    po_number      VARCHAR(20),
    seq            INTEGER NOT NULL,
    status_code    VARCHAR(3) NOT NULL,
    event_date     DATE,
    location       VARCHAR(50),
    PRIMARY KEY (asn_number, seq)
);

CREATE TABLE invoices (                   -- EDI 810
    invoice_number  VARCHAR(20) PRIMARY KEY,
    po_number       VARCHAR(20) NOT NULL REFERENCES purchase_orders(po_number),
    invoice_date    DATE,
    qty_invoiced    INTEGER,
    invoice_amount  NUMERIC(14,2)
);

CREATE INDEX idx_ship_po ON shipments(po_number);
CREATE INDEX idx_inv_po ON invoices(po_number);
