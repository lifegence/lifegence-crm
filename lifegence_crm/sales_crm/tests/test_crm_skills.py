"""Tests for crm_skills.py — AI agent skills for CRM."""

import unittest
from unittest.mock import patch, MagicMock


MODULE = "lifegence_crm.sales_crm.skills.crm_skills"


class TestCrmDealSummary(unittest.TestCase):
    """Tests for crm_deal_summary skill."""

    @patch(f"{MODULE}.frappe")
    def test_returns_pipeline_and_recent_deals(self, mock_frappe):
        """Basic call returns pipeline summary, recent deals, and this_month stats."""
        # Pipeline summary
        mock_frappe.db.sql.return_value = [
            {"stage": "提案", "count": 5, "total_value": 5000000, "total_weighted": 2000000},
        ]
        # Recent deals
        mock_frappe.get_all.return_value = [
            {"name": "DEAL-001", "deal_name": "Test", "stage": "提案",
             "deal_value": 1000000, "weighted_value": 400000, "customer": "ABC", "modified": "2026-03-30"},
        ]
        mock_frappe.db.count.side_effect = [3, 1, 10]  # won, lost, total

        from lifegence_crm.sales_crm.skills.crm_skills import crm_deal_summary
        result = crm_deal_summary()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["pipeline"]), 1)
        self.assertEqual(result["this_month"]["won"], 3)
        self.assertEqual(result["this_month"]["lost"], 1)
        self.assertEqual(result["total_deals"], 10)

    @patch(f"{MODULE}.frappe")
    def test_stage_filter_passed(self, mock_frappe):
        """When stage is specified, filters dict should contain it."""
        mock_frappe.db.sql.return_value = []
        mock_frappe.get_all.return_value = []
        mock_frappe.db.count.side_effect = [0, 0, 0]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_deal_summary
        result = crm_deal_summary(stage="交渉中")

        self.assertTrue(result["success"])
        # Verify stage filter in SQL
        sql_call = mock_frappe.db.sql.call_args
        self.assertIn("stage", sql_call[0][1])

    @patch(f"{MODULE}.frappe")
    def test_limit_capped_at_50(self, mock_frappe):
        """limit parameter should be capped at 50."""
        mock_frappe.db.sql.return_value = []
        mock_frappe.get_all.return_value = []
        mock_frappe.db.count.side_effect = [0, 0, 0]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_deal_summary
        crm_deal_summary(limit=100)

        get_all_call = mock_frappe.get_all.call_args
        self.assertLessEqual(get_all_call[1]["limit_page_length"], 50)


class TestCrmSuggestNextAction(unittest.TestCase):
    """Tests for crm_suggest_next_action skill."""

    @patch(f"{MODULE}.frappe")
    def test_deal_not_found(self, mock_frappe):
        """Returns error when deal does not exist."""
        mock_frappe.db.exists.return_value = False

        from lifegence_crm.sales_crm.skills.crm_skills import crm_suggest_next_action
        result = crm_suggest_next_action("DEAL-NONEXIST")

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    @patch(f"{MODULE}.frappe")
    def test_urgent_when_inactive_over_14_days(self, mock_frappe):
        """Deal inactive > 14 days should be urgent."""
        mock_frappe.db.exists.return_value = True
        mock_deal = MagicMock()
        mock_deal.name = "DEAL-001"
        mock_deal.deal_name = "Test Deal"
        mock_deal.stage = "提案"
        mock_deal.deal_value = 1000000
        mock_deal.customer = "ABC Corp"
        mock_deal.creation = "2026-01-01"
        mock_frappe.get_doc.return_value = mock_deal

        # Activity 20 days ago
        mock_frappe.get_all.return_value = [
            MagicMock(activity_type="電話", subject="Call", activity_date="2026-03-11", status="Completed"),
        ]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_suggest_next_action
        result = crm_suggest_next_action("DEAL-001")

        self.assertTrue(result["success"])
        self.assertEqual(result["urgency"], "urgent")
        self.assertGreater(result["days_inactive"], 14)

    @patch(f"{MODULE}.frappe")
    def test_warning_when_inactive_8_to_14_days(self, mock_frappe):
        """Deal inactive 8-14 days should be warning."""
        mock_frappe.db.exists.return_value = True
        mock_deal = MagicMock()
        mock_deal.name = "DEAL-001"
        mock_deal.deal_name = "Test Deal"
        mock_deal.stage = "見積提出"
        mock_deal.deal_value = 500000
        mock_deal.customer = "XYZ Corp"
        mock_deal.creation = "2026-01-01"
        mock_frappe.get_doc.return_value = mock_deal

        # Activity 10 days ago
        mock_frappe.get_all.return_value = [
            MagicMock(activity_type="メール", subject="Estimate", activity_date="2026-03-21", status="Open"),
        ]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_suggest_next_action
        result = crm_suggest_next_action("DEAL-001")

        self.assertTrue(result["success"])
        self.assertEqual(result["urgency"], "warning")

    @patch(f"{MODULE}.frappe")
    def test_normal_when_recent_activity(self, mock_frappe):
        """Deal with activity within 7 days should be normal."""
        mock_frappe.db.exists.return_value = True
        mock_deal = MagicMock()
        mock_deal.name = "DEAL-001"
        mock_deal.deal_name = "Fresh Deal"
        mock_deal.stage = "リード"
        mock_deal.deal_value = 100000
        mock_deal.customer = "New Corp"
        mock_deal.creation = "2026-03-25"
        mock_frappe.get_doc.return_value = mock_deal

        # Activity 2 days ago
        mock_frappe.get_all.return_value = [
            MagicMock(activity_type="電話", subject="Initial call", activity_date="2026-03-29", status="Completed"),
        ]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_suggest_next_action
        result = crm_suggest_next_action("DEAL-001")

        self.assertTrue(result["success"])
        self.assertEqual(result["urgency"], "normal")

    @patch(f"{MODULE}.frappe")
    def test_no_activities_uses_creation_date(self, mock_frappe):
        """When no activities exist, days_inactive uses deal creation."""
        mock_frappe.db.exists.return_value = True
        mock_deal = MagicMock()
        mock_deal.name = "DEAL-002"
        mock_deal.deal_name = "New Deal"
        mock_deal.stage = "リード"
        mock_deal.deal_value = 200000
        mock_deal.customer = "New Corp"
        mock_deal.creation = "2026-03-01"
        mock_frappe.get_doc.return_value = mock_deal
        mock_frappe.get_all.return_value = []  # No activities

        from lifegence_crm.sales_crm.skills.crm_skills import crm_suggest_next_action
        result = crm_suggest_next_action("DEAL-002")

        self.assertTrue(result["success"])
        self.assertGreater(result["days_inactive"], 14)
        self.assertEqual(result["urgency"], "urgent")

    @patch(f"{MODULE}.frappe")
    def test_stage_suggestion_present(self, mock_frappe):
        """Suggestion should contain stage-specific advice."""
        mock_frappe.db.exists.return_value = True
        mock_deal = MagicMock()
        mock_deal.name = "DEAL-003"
        mock_deal.deal_name = "Negotiation Deal"
        mock_deal.stage = "交渉中"
        mock_deal.deal_value = 3000000
        mock_deal.customer = "Big Corp"
        mock_deal.creation = "2026-03-30"
        mock_frappe.get_doc.return_value = mock_deal
        mock_frappe.get_all.return_value = [
            MagicMock(activity_type="訪問", subject="Meeting", activity_date="2026-03-30", status="Completed"),
        ]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_suggest_next_action
        result = crm_suggest_next_action("DEAL-003")

        self.assertIn("決裁者", result["suggestion"])


class TestCrmLeadQualification(unittest.TestCase):
    """Tests for crm_lead_qualification skill."""

    @patch(f"{MODULE}.frappe")
    def test_empty_leads(self, mock_frappe):
        """No leads returns empty list with zero summary."""
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.skills.crm_skills import crm_lead_qualification
        result = crm_lead_qualification()

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["summary"]["hot"], 0)

    @patch(f"{MODULE}.frappe")
    def test_hot_lead_scoring(self, mock_frappe):
        """Lead with company, high source, recent, engaged, and assigned should be Hot."""
        mock_frappe.get_all.return_value = [
            MagicMock(
                name="LEAD-001",
                lead_name="Hot Lead",
                company_name="Big Corp",
                status="Open",
                source="Referral",
                creation="2026-03-28",  # 3 days ago
                modified="2026-03-30",
                lead_owner="admin@example.com",
            ),
        ]
        mock_frappe.db.count.return_value = 5  # 5 communications

        from lifegence_crm.sales_crm.skills.crm_skills import crm_lead_qualification
        result = crm_lead_qualification()

        self.assertEqual(result["count"], 1)
        lead = result["leads"][0]
        self.assertEqual(lead["priority"], "Hot")
        self.assertGreaterEqual(lead["score"], 70)

    @patch(f"{MODULE}.frappe")
    def test_cold_lead_scoring(self, mock_frappe):
        """Lead with no company, no source, old, no engagement, no owner should be Cold."""
        mock_frappe.get_all.return_value = [
            MagicMock(
                name="LEAD-002",
                lead_name="Cold Lead",
                company_name=None,
                status="Open",
                source=None,
                creation="2025-01-01",  # very old
                modified="2025-01-01",
                lead_owner=None,
            ),
        ]
        mock_frappe.db.count.return_value = 0

        from lifegence_crm.sales_crm.skills.crm_skills import crm_lead_qualification
        result = crm_lead_qualification()

        lead = result["leads"][0]
        self.assertEqual(lead["priority"], "Cold")
        self.assertLess(lead["score"], 40)

    @patch(f"{MODULE}.frappe")
    def test_status_filter_passed(self, mock_frappe):
        """When status is given, it should appear in filters."""
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.skills.crm_skills import crm_lead_qualification
        crm_lead_qualification(status="Lead")

        call_args = mock_frappe.get_all.call_args
        self.assertEqual(call_args[1]["filters"]["status"], "Lead")

    @patch(f"{MODULE}.frappe")
    def test_results_sorted_by_score_desc(self, mock_frappe):
        """Results should be sorted by score descending."""
        mock_frappe.get_all.return_value = [
            MagicMock(name="L1", lead_name="Low", company_name=None, status="Open",
                      source=None, creation="2025-01-01", modified="2025-01-01", lead_owner=None),
            MagicMock(name="L2", lead_name="High", company_name="Corp", status="Open",
                      source="Referral", creation="2026-03-28", modified="2026-03-30", lead_owner="admin"),
        ]
        mock_frappe.db.count.side_effect = [0, 5]

        from lifegence_crm.sales_crm.skills.crm_skills import crm_lead_qualification
        result = crm_lead_qualification()

        self.assertGreater(result["leads"][0]["score"], result["leads"][1]["score"])

    @patch(f"{MODULE}.frappe")
    def test_limit_capped_at_50(self, mock_frappe):
        """limit parameter should be capped at 50."""
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.skills.crm_skills import crm_lead_qualification
        crm_lead_qualification(limit=100)

        call_args = mock_frappe.get_all.call_args
        self.assertLessEqual(call_args[1]["limit_page_length"], 50)


if __name__ == "__main__":
    unittest.main()
