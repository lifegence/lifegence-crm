"""Tests for sales_skills.py — AI agent skills for B2B sales management.

Mock-based: no DB fixtures required. Mirrors test_crm_skills.py style.
"""

import unittest
from unittest.mock import MagicMock, patch


MODULE = "lifegence_crm.sales_crm.skills.sales_skills"


class TestSalesLookupCustomer(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_returns_customer_with_credit_and_recent_orders(self, mock_frappe):
        # _resolve_customer: exact match found
        mock_frappe.db.exists.return_value = True

        cust = MagicMock(
            name="Cust",
            customer_name="トヨタ自動車部品株式会社",
            customer_group="自動車",
            territory="Japan",
            default_currency="JPY",
        )
        cust.name = "トヨタ自動車部品株式会社"
        cust.credit_limits = [
            MagicMock(company="Lifegence Corporation", credit_limit=5_000_000),
        ]
        mock_frappe.get_doc.return_value = cust
        mock_frappe.defaults.get_user_default.return_value = "Lifegence Corporation"
        # outstanding query + max_overdue query
        mock_frappe.db.sql.side_effect = [
            [[1_040_000]],  # outstanding
            [[0]],           # max_overdue
        ]
        mock_frappe.get_all.return_value = [
            {"name": "SO-001", "transaction_date": "2026-05-04",
             "grand_total": 1_040_000, "status": "Completed", "delivery_date": "2026-05-11"},
        ]

        from lifegence_crm.sales_crm.skills.sales_skills import sales_lookup_customer
        result = sales_lookup_customer(query="トヨタ自動車部品株式会社")

        self.assertTrue(result["success"])
        self.assertEqual(result["customer"]["customer_name"], "トヨタ自動車部品株式会社")
        self.assertEqual(result["credit"]["limit"], 5_000_000)
        self.assertEqual(result["credit"]["used"], 1_040_000)
        self.assertEqual(result["payment_health"]["status"], "good")
        self.assertEqual(len(result["recent_orders"]), 1)

    @patch(f"{MODULE}.frappe")
    def test_returns_error_when_customer_not_found(self, mock_frappe):
        mock_frappe.db.exists.return_value = False
        mock_frappe.db.sql.return_value = []

        from lifegence_crm.sales_crm.skills.sales_skills import sales_lookup_customer
        result = sales_lookup_customer(query="存在しない会社")

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    @patch(f"{MODULE}.frappe")
    def test_overdue_payment_marks_status_warning_or_critical(self, mock_frappe):
        mock_frappe.db.exists.return_value = True

        cust = MagicMock()
        cust.name = "X"
        cust.customer_name = "X"
        cust.customer_group = "電機"
        cust.territory = "Japan"
        cust.default_currency = "JPY"
        cust.credit_limits = []
        mock_frappe.get_doc.return_value = cust
        mock_frappe.defaults.get_user_default.return_value = "Lifegence Corporation"
        mock_frappe.db.sql.side_effect = [
            [[500_000]],  # outstanding
            [[45]],        # max_overdue_days = 45 → critical
        ]
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.skills.sales_skills import sales_lookup_customer
        result = sales_lookup_customer(query="X")
        self.assertEqual(result["payment_health"]["status"], "critical")


class TestSalesLookupItem(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_returns_item_with_stock_breakdown(self, mock_frappe):
        mock_frappe.db.exists.return_value = True

        item = MagicMock()
        item.item_code = "DEMO-SVM-300"
        item.item_name = "サーボモーター SVM-300"
        item.item_group = "動力機器"
        item.standard_rate = 17_000
        item.valuation_rate = 10_200
        item.stock_uom = "Nos"
        item.is_stock_item = 1
        mock_frappe.get_doc.return_value = item

        # First sql: stock_rows. Second sql: last_sold
        mock_frappe.db.sql.side_effect = [
            [
                {"warehouse": "本社倉庫 - LC", "actual_qty": 75,
                 "projected_qty": 60, "reserved_qty": 15},
                {"warehouse": "大阪倉庫 - LC", "actual_qty": 30,
                 "projected_qty": 30, "reserved_qty": 0},
            ],
            [{"rate": 17_000, "transaction_date": "2026-05-06",
              "customer": "ファナック株式会社"}],
        ]

        from lifegence_crm.sales_crm.skills.sales_skills import sales_lookup_item
        result = sales_lookup_item(query="DEMO-SVM-300")

        self.assertTrue(result["success"])
        self.assertEqual(result["stock"]["total_qty"], 105)
        self.assertEqual(result["stock"]["available_qty"], 90)
        self.assertEqual(len(result["stock"]["by_warehouse"]), 2)
        self.assertIsNotNone(result["last_sold"])


class TestSalesCheckStock(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_specific_item_returns_warehouse_breakdown(self, mock_frappe):
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.sql.side_effect = [
            [{"warehouse": "本社倉庫 - LC", "actual_qty": 18,
              "reserved_qty": 0, "projected_qty": 18}],
            [{"warehouse": "本社倉庫 - LC", "warehouse_reorder_level": 50}],
        ]

        from lifegence_crm.sales_crm.skills.sales_skills import sales_check_stock
        result = sales_check_stock(item_code="DEMO-CTL-100")

        self.assertTrue(result["success"])
        self.assertTrue(result["warehouses"][0]["below_reorder"])
        self.assertEqual(result["warehouses"][0]["reorder_level"], 50)

    @patch(f"{MODULE}.frappe")
    def test_below_reorder_mode_returns_critical_items(self, mock_frappe):
        # First sql: low-stock aggregate. Then per-item outflow query.
        mock_frappe.db.sql.side_effect = [
            [
                {"item_code": "DEMO-SNS-200", "item_name": "温度センサー SNS-200",
                 "total_qty": 8, "reserved_qty": 0, "reorder_level": 30},
            ],
            [[50]],  # outflow for SNS-200 last 30 days
        ]

        from lifegence_crm.sales_crm.skills.sales_skills import sales_check_stock
        result = sales_check_stock(below_reorder=True, limit=5)

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["low_stock_items"][0]["item_code"], "DEMO-SNS-200")
        # days_remaining = 8 / (50/30) = 4.8
        self.assertAlmostEqual(result["low_stock_items"][0]["days_remaining"], 4.8, places=1)
        # suggested order = reorder*2 - current = 60-8 = 52
        self.assertEqual(result["low_stock_items"][0]["suggested_order_qty"], 52)

    def test_no_input_returns_error(self):
        from lifegence_crm.sales_crm.skills.sales_skills import sales_check_stock
        result = sales_check_stock()
        self.assertFalse(result["success"])
        self.assertIn("item_code", result["error"])


class TestSalesCreateQuotation(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_creates_draft_quotation_with_default_rate(self, mock_frappe):
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.sql.return_value = []
        mock_frappe.defaults.get_user_default.return_value = "Lifegence Corporation"
        mock_frappe.db.get_value.return_value = 17_000  # standard_rate

        item_row = MagicMock(item_code="DEMO-SVM-300", qty=50, rate=17_000, amount=850_000)
        doc = MagicMock(name="QTN-001", grand_total=807_500, total_qty=50,
                        valid_till="2026-06-11", items=[item_row])
        doc.name = "SAL-QTN-2026-00011"
        mock_frappe.get_doc.return_value = doc

        from lifegence_crm.sales_crm.skills.sales_skills import sales_create_quotation
        result = sales_create_quotation(
            customer="DEMO-CUST", items=[{"item_code": "DEMO-SVM-300", "qty": 50}],
            discount_percentage=5,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "Draft")
        self.assertEqual(result["grand_total"], 807_500)
        doc.insert.assert_called_once()
        doc.submit.assert_not_called()  # default submit=False

    @patch(f"{MODULE}.frappe")
    def test_unknown_customer_returns_error(self, mock_frappe):
        mock_frappe.db.exists.return_value = False
        mock_frappe.db.sql.return_value = []
        from lifegence_crm.sales_crm.skills.sales_skills import sales_create_quotation
        result = sales_create_quotation(customer="不明", items=[{"item_code": "X", "qty": 1}])
        self.assertFalse(result["success"])


class TestSalesCreateOrder(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_from_quotation_uses_make_sales_order(self, mock_frappe):
        mock_frappe.db.exists.return_value = True
        mock_frappe.defaults.get_user_default.return_value = "Lifegence Corporation"

        doc = MagicMock()
        doc.name = "SAL-ORD-001"
        doc.status = "To Deliver and Bill"
        doc.customer = "トヨタ自動車部品株式会社"
        doc.delivery_date = "2026-05-26"
        doc.grand_total = 807_500
        doc.total_qty = 50
        doc.items = [MagicMock(item_code="DEMO-SVM-300", qty=50, rate=17_000, amount=850_000)]

        with patch(f"erpnext.selling.doctype.quotation.quotation.make_sales_order",
                   return_value=doc):
            from lifegence_crm.sales_crm.skills.sales_skills import sales_create_order
            result = sales_create_order(from_quotation="QTN-001")

        self.assertTrue(result["success"])
        self.assertEqual(result["sales_order"], "SAL-ORD-001")
        doc.insert.assert_called_once()
        doc.submit.assert_called_once()  # default submit=True

    def test_missing_inputs_returns_error(self):
        from lifegence_crm.sales_crm.skills.sales_skills import sales_create_order
        result = sales_create_order()
        self.assertFalse(result["success"])


class TestSalesCreateInvoice(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_from_delivery_note(self, mock_frappe):
        mock_frappe.db.exists.return_value = True

        doc = MagicMock()
        doc.name = "ACC-SINV-001"
        doc.status = "Unpaid"
        doc.customer = "三菱電機株式会社"
        doc.posting_date = "2026-05-12"
        doc.due_date = "2026-06-11"
        doc.grand_total = 1_155_000
        doc.outstanding_amount = 1_155_000
        doc.items = [MagicMock(item_code="DEMO-PWR-1000", qty=12, rate=65_000, amount=780_000)]

        with patch(f"erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
                   return_value=doc):
            from lifegence_crm.sales_crm.skills.sales_skills import sales_create_invoice
            result = sales_create_invoice(from_delivery_note="DN-001", due_days=30)

        self.assertTrue(result["success"])
        self.assertEqual(result["sales_invoice"], "ACC-SINV-001")
        self.assertEqual(result["outstanding_amount"], 1_155_000)

    def test_missing_inputs_returns_error(self):
        from lifegence_crm.sales_crm.skills.sales_skills import sales_create_invoice
        result = sales_create_invoice()
        self.assertFalse(result["success"])


class TestSalesCustomerSummary(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_returns_revenue_open_sos_unbilled_dns_and_top_items(self, mock_frappe):
        mock_frappe.db.exists.return_value = True

        # 4 SQL calls: revenue / open SOs / unbilled DNs / top items
        # (_resolve_customer returns early since db.exists is True)
        mock_frappe.db.sql.side_effect = [
            [{"total_billed": 1_716_000, "total_outstanding": 0, "invoice_count": 2}],
            [{"name": "SO-005", "transaction_date": "2026-05-08",
              "delivery_date": "2026-05-15", "grand_total": 1_155_000,
              "status": "To Bill", "per_delivered": 100, "per_billed": 0}],
            [{"name": "DN-005", "posting_date": "2026-05-15",
              "grand_total": 1_155_000, "per_billed": 0}],
            [{"item_code": "DEMO-CTL-200", "item_name": "制御基板 CTL-200",
              "total_qty": 20, "total_amount": 960_000}],
        ]

        from lifegence_crm.sales_crm.skills.sales_skills import sales_customer_summary
        result = sales_customer_summary(customer="三菱電機株式会社", lookback_days=90)

        self.assertTrue(result["success"])
        self.assertEqual(result["revenue"]["total_billed"], 1_716_000)
        self.assertEqual(len(result["open_sales_orders"]), 1)
        self.assertEqual(len(result["unbilled_delivery_notes"]), 1)


class TestSalesPeriodReport(unittest.TestCase):
    @patch(f"{MODULE}.frappe")
    def test_groups_by_customer_with_mom_comparison(self, mock_frappe):
        # Two sql calls: current period rows, then prev period rows
        mock_frappe.db.sql.side_effect = [
            [
                {"key_field": "日立", "label": "日立", "invoice_count": 1,
                 "amount": 2_540_000},
                {"key_field": "トヨタ", "label": "トヨタ", "invoice_count": 2,
                 "amount": 1_720_000},
            ],
            [
                {"key_field": "日立", "amount": 2_350_000},
                {"key_field": "トヨタ", "amount": 935_000},
            ],
        ]

        from lifegence_crm.sales_crm.skills.sales_skills import sales_period_report
        result = sales_period_report(period="this_month", group_by="customer", top_n=5)

        self.assertTrue(result["success"])
        self.assertEqual(result["total_current"], 4_260_000)
        self.assertEqual(result["total_prev"], 3_285_000)
        # 日立: +8.1% → flat (between -10 and +10)
        hitachi = next(r for r in result["top"] if r["key_field"] == "日立")
        self.assertEqual(hitachi["trend"], "flat")
        # トヨタ: +83.9% → up
        toyota = next(r for r in result["top"] if r["key_field"] == "トヨタ")
        self.assertEqual(toyota["trend"], "up")


if __name__ == "__main__":
    unittest.main()
