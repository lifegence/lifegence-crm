"""Tests for reminder_service.py — send_activity_reminders."""

import unittest
from unittest.mock import patch, MagicMock, call


class TestSendActivityReminders(unittest.TestCase):
    """Unit tests for send_activity_reminders."""

    MODULE = "lifegence_crm.sales_crm.services.reminder_service"

    @patch(f"lifegence_crm.sales_crm.services.reminder_service.frappe")
    def test_reminders_disabled_returns_early(self, mock_frappe):
        """If auto_activity_reminder is falsy, no mail is sent."""
        mock_settings = MagicMock()
        mock_settings.auto_activity_reminder = False
        mock_frappe.get_single.return_value = mock_settings

        from lifegence_crm.sales_crm.services.reminder_service import send_activity_reminders
        send_activity_reminders()

        mock_frappe.get_all.assert_not_called()
        mock_frappe.sendmail.assert_not_called()
        mock_frappe.db.commit.assert_not_called()

    @patch(f"lifegence_crm.sales_crm.services.reminder_service.frappe")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.add_days", return_value="2026-04-01")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.nowdate", return_value="2026-03-31")
    def test_sends_mail_for_activities_with_assigned_to(self, mock_nowdate, mock_add_days, mock_frappe):
        """Should send email for each activity that has assigned_to."""
        mock_settings = MagicMock()
        mock_settings.auto_activity_reminder = True
        mock_settings.reminder_days_before = 1
        mock_frappe.get_single.return_value = mock_settings

        activity1 = MagicMock()
        activity1.assigned_to = "tanaka@example.com"
        activity1.subject = "見積フォロー"
        activity1.next_action = "電話"
        activity1.next_action_date = "2026-04-01"

        activity2 = MagicMock()
        activity2.assigned_to = None  # No assignee — should be skipped
        activity2.subject = "訪問"
        activity2.next_action = "訪問"
        activity2.next_action_date = "2026-04-01"

        mock_frappe.get_all.return_value = [activity1, activity2]

        from lifegence_crm.sales_crm.services.reminder_service import send_activity_reminders
        send_activity_reminders()

        # Only one mail sent (activity2 has no assigned_to)
        self.assertEqual(mock_frappe.sendmail.call_count, 1)
        sent_call = mock_frappe.sendmail.call_args
        self.assertEqual(sent_call[1]["recipients"], ["tanaka@example.com"])
        self.assertIn("電話", sent_call[1]["subject"])
        mock_frappe.db.commit.assert_called_once()

    @patch(f"lifegence_crm.sales_crm.services.reminder_service.frappe")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.add_days", return_value="2026-04-03")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.nowdate", return_value="2026-03-31")
    def test_reminder_days_before_setting_used(self, mock_nowdate, mock_add_days, mock_frappe):
        """reminder_days_before from settings should be passed to add_days."""
        mock_settings = MagicMock()
        mock_settings.auto_activity_reminder = True
        mock_settings.reminder_days_before = 3
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.services.reminder_service import send_activity_reminders
        send_activity_reminders()

        mock_add_days.assert_called_once_with("2026-03-31", 3)

    @patch(f"lifegence_crm.sales_crm.services.reminder_service.frappe")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.add_days", return_value="2026-04-01")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.nowdate", return_value="2026-03-31")
    def test_no_activities_no_mail(self, mock_nowdate, mock_add_days, mock_frappe):
        """When no activities match, no mail is sent but commit still happens."""
        mock_settings = MagicMock()
        mock_settings.auto_activity_reminder = True
        mock_settings.reminder_days_before = 1
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.services.reminder_service import send_activity_reminders
        send_activity_reminders()

        mock_frappe.sendmail.assert_not_called()
        mock_frappe.db.commit.assert_called_once()

    @patch(f"lifegence_crm.sales_crm.services.reminder_service.frappe")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.add_days", return_value="2026-04-01")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.nowdate", return_value="2026-03-31")
    def test_default_reminder_days_is_1(self, mock_nowdate, mock_add_days, mock_frappe):
        """When reminder_days_before is 0/None, defaults to 1."""
        mock_settings = MagicMock()
        mock_settings.auto_activity_reminder = True
        mock_settings.reminder_days_before = 0  # falsy
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.services.reminder_service import send_activity_reminders
        send_activity_reminders()

        mock_add_days.assert_called_once_with("2026-03-31", 1)

    @patch(f"lifegence_crm.sales_crm.services.reminder_service.frappe")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.add_days", return_value="2026-04-01")
    @patch(f"lifegence_crm.sales_crm.services.reminder_service.nowdate", return_value="2026-03-31")
    def test_get_all_called_with_correct_filters(self, mock_nowdate, mock_add_days, mock_frappe):
        """get_all should filter on next_action_date and next_action is set."""
        mock_settings = MagicMock()
        mock_settings.auto_activity_reminder = True
        mock_settings.reminder_days_before = 1
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe.get_all.return_value = []

        from lifegence_crm.sales_crm.services.reminder_service import send_activity_reminders
        send_activity_reminders()

        call_args = mock_frappe.get_all.call_args
        self.assertEqual(call_args[0][0], "Activity")
        filters = call_args[1]["filters"]
        self.assertEqual(filters["next_action_date"], "2026-04-01")
        self.assertEqual(filters["next_action"], ["is", "set"])


if __name__ == "__main__":
    unittest.main()
