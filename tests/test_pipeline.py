import tempfile
import unittest
from pathlib import Path

from ctower import analytics, database, edi_parser, exceptions, generate_edi


class ParserTests(unittest.TestCase):
    def test_850_basic(self):
        text = ("ISA*00~ST*850*0001~BEG*00*SA*4500000001**20260105~N1*SU*Test Supplier*92*S01~"
                "DTM*002*20260201~PO1*1*100*EA*2.50**VP*ABC-1~CTT*1~SE*7*0001~IEA*1*1~")
        docs = edi_parser.split_transactions(text)
        po, lines = edi_parser.parse_850(docs[0])
        self.assertEqual(po["po_number"], "4500000001")
        self.assertEqual(po["requested_date"], "2026-02-01")
        self.assertEqual(lines[0]["qty_ordered"], 100)

    def test_bad_segment_count_is_rejected(self):
        text = "ST*850*0001~BEG*00*SA*45~SE*9*0001~"
        with self.assertRaises(edi_parser.EDIError):
            edi_parser.split_transactions(text)


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        raw = Path(cls.tmp.name) / "raw"
        cls.counts = generate_edi.generate(raw, n=150, seed=7)
        cls.tables, cls.rejected = edi_parser.parse_all(raw)
        cls.conn = database.build_database(cls.tables, Path(cls.tmp.name) / "t.db")
        cls.orders = analytics.order_table(cls.conn)

    def test_nothing_rejected(self):
        self.assertEqual(self.rejected, [])

    def test_row_counts_match_documents(self):
        self.assertEqual(len(self.tables["purchase_orders"]), self.counts["850"])
        self.assertEqual(len(self.tables["shipments"]), self.counts["856"])
        self.assertEqual(len(self.tables["invoices"]), self.counts["810"])

    def test_one_row_per_po(self):
        self.assertEqual(len(self.orders), self.counts["850"])
        self.assertTrue(self.orders.po_number.is_unique)

    def test_delivered_orders_have_delay(self):
        d = self.orders[self.orders.status == "Delivered"]
        self.assertTrue(d.delay_days.notna().all())

    def test_exceptions_have_known_severity(self):
        o = self.orders.copy()
        o["delay_prob"] = float("nan")
        ex = exceptions.find_exceptions(o)
        self.assertTrue(set(ex.severity) <= {"High", "Medium", "Low"})


if __name__ == "__main__":
    unittest.main()
