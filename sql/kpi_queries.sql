-- Example analytical queries on the raw EDI tables (SQLite / PostgreSQL friendly).

-- 1) On-time delivery by supplier (delivered = has a D1 event)
SELECT p.supplier_name,
       COUNT(*)                                                     AS delivered_orders,
       ROUND(100.0 * SUM(CASE WHEN e.event_date <= p.requested_date THEN 1 ELSE 0 END) / COUNT(*), 1) AS otd_pct
FROM purchase_orders p
JOIN shipments s        ON s.po_number = p.po_number
JOIN shipment_events e  ON e.asn_number = s.asn_number AND e.status_code = 'D1'
GROUP BY p.supplier_name
ORDER BY otd_pct;

-- 2) Quantity discrepancy: ordered vs confirmed vs shipped
SELECT p.po_number,
       SUM(l.qty_ordered)    AS ordered,
       SUM(a.qty_confirmed)  AS confirmed,
       MAX(s.qty_shipped)    AS shipped
FROM purchase_orders p
JOIN po_lines l          ON l.po_number = p.po_number
JOIN acknowledgements a  ON a.po_number = l.po_number AND a.line_no = l.line_no
JOIN shipments s         ON s.po_number = p.po_number
GROUP BY p.po_number
HAVING MAX(s.qty_shipped) < SUM(l.qty_ordered)
ORDER BY SUM(l.qty_ordered) - MAX(s.qty_shipped) DESC
LIMIT 20;

-- 3) Invoices where billed quantity differs from the ASN quantity (3-way match failure)
SELECT i.invoice_number, i.po_number, s.qty_shipped, i.qty_invoiced,
       i.qty_invoiced - s.qty_shipped AS qty_diff
FROM invoices i
JOIN shipments s ON s.po_number = i.po_number
WHERE i.qty_invoiced <> s.qty_shipped;

-- 4) Average transit time per carrier and mode
SELECT s.carrier, s.mode,
       COUNT(*) AS shipments,
       ROUND(AVG(julianday(e.event_date) - julianday(s.ship_date)), 1) AS avg_transit_days
FROM shipments s
JOIN shipment_events e ON e.asn_number = s.asn_number AND e.status_code = 'D1'
GROUP BY s.carrier, s.mode;
-- (PostgreSQL: replace julianday(a) - julianday(b) with (a - b))
