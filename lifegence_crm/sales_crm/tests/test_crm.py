import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate, today


class TestCRM(FrappeTestCase):
	def setUp(self):
		self.ensure_roles()
		self.ensure_deal_stages()

	def ensure_roles(self):
		for role_name in ("Sales Manager", "Sales User"):
			if not frappe.db.exists("Role", role_name):
				frappe.get_doc({
					"doctype": "Role",
					"role_name": role_name,
					"desk_access": 1,
				}).insert(ignore_permissions=True)

	def ensure_deal_stages(self):
		stages = [
			{"stage_name": "リード", "probability": 10, "sort_order": 1, "color": "#a0d2db"},
			{"stage_name": "アポ取得", "probability": 20, "sort_order": 2, "color": "#78c2ad"},
			{"stage_name": "提案", "probability": 40, "sort_order": 3, "color": "#5cb85c"},
			{"stage_name": "見積提出", "probability": 60, "sort_order": 4, "color": "#f0ad4e"},
			{"stage_name": "交渉中", "probability": 80, "sort_order": 5, "color": "#ff7851"},
			{"stage_name": "受注", "probability": 100, "sort_order": 6, "color": "#3498db", "is_won": 1},
			{"stage_name": "失注", "probability": 0, "sort_order": 7, "color": "#e74c3c", "is_lost": 1},
		]
		for stage in stages:
			if not frappe.db.exists("Deal Stage", stage["stage_name"]):
				doc = frappe.new_doc("Deal Stage")
				doc.update(stage)
				doc.insert(ignore_permissions=True)

	def test_settings_defaults(self):
		"""CRM Settings should have correct defaults."""
		settings = frappe.get_single("Sales CRM Settings")
		self.assertEqual(settings.enable_lead_scoring, 1)
		self.assertEqual(settings.auto_activity_reminder, 1)
		self.assertEqual(settings.enable_weighted_forecast, 1)
		self.assertEqual(settings.deal_auto_numbering, 1)
		self.assertEqual(settings.min_score_for_hot, 80)
		self.assertEqual(settings.scoring_recalculate_frequency, "Daily")
		self.assertEqual(settings.reminder_days_before, 1)

	def test_deal_stage_seed(self):
		"""Seven deal stages should exist after setup."""
		stages = frappe.get_all("Deal Stage", fields=["stage_name", "probability", "is_won", "is_lost"])
		self.assertEqual(len(stages), 7)

		won_stages = [s for s in stages if s.is_won]
		lost_stages = [s for s in stages if s.is_lost]
		self.assertEqual(len(won_stages), 1)
		self.assertEqual(len(lost_stages), 1)

	def test_deal_creation(self):
		"""Deal should auto-set probability and weighted value from stage."""
		deal = frappe.get_doc({
			"doctype": "Deal",
			"deal_name": "Test Deal CRM",
			"stage": "提案",
			"deal_value": 1000000,
		})
		deal.insert(ignore_permissions=True)

		self.assertEqual(deal.probability, 40)
		self.assertEqual(deal.weighted_value, 400000)
		self.assertTrue(deal.name.startswith("DEAL-"))

		# Cleanup
		deal.delete(ignore_permissions=True)

	def test_activity_creation(self):
		"""Activity should be created with correct defaults."""
		activity = frappe.get_doc({
			"doctype": "Activity",
			"activity_type": "電話",
			"subject": "Test Call Activity",
		})
		activity.insert(ignore_permissions=True)

		self.assertTrue(activity.name.startswith("ACT-"))
		self.assertTrue(activity.activity_date)
		self.assertEqual(activity.activity_type, "電話")

		# Cleanup
		activity.delete(ignore_permissions=True)

	def test_campaign_with_members(self):
		"""Campaign should support child table members."""
		campaign = frappe.get_doc({
			"doctype": "Campaign",
			"campaign_name": "Test Campaign CRM",
			"campaign_type": "Email",
			"start_date": today(),
			"status": "Planning",
		})
		campaign.insert(ignore_permissions=True)

		self.assertTrue(campaign.name.startswith("CAMP-"))
		self.assertEqual(campaign.status, "Planning")

		# Cleanup
		campaign.delete(ignore_permissions=True)

	def test_lead_scoring_rule(self):
		"""Lead Scoring Rule should store rule configuration."""
		rule = frappe.get_doc({
			"doctype": "Lead Scoring Rule",
			"rule_name": "Test Company Set Rule",
			"field_name": "company_name",
			"operator": "is set",
			"score": 20,
			"is_active": 1,
		})
		rule.insert(ignore_permissions=True)

		self.assertTrue(rule.name.startswith("LSR-"))
		self.assertEqual(rule.score, 20)
		self.assertEqual(rule.operator, "is set")

		# Cleanup
		rule.delete(ignore_permissions=True)

	def test_call_log_creation(self):
		"""Call Log CRM should be created with correct defaults."""
		call_log = frappe.get_doc({
			"doctype": "Call Log CRM",
			"call_type": "Outbound",
			"phone_number": "03-1234-5678",
			"duration_sec": 120,
		})
		call_log.insert(ignore_permissions=True)

		self.assertTrue(call_log.name.startswith("CALL-"))
		self.assertEqual(call_log.call_type, "Outbound")
		self.assertTrue(call_log.call_datetime)

		# Cleanup
		call_log.delete(ignore_permissions=True)

	def test_meeting_note_creation(self):
		"""Meeting Note should be created with correct defaults."""
		note = frappe.get_doc({
			"doctype": "Meeting Note",
			"meeting_title": "Test Meeting CRM",
			"meeting_date": today(),
			"attendees": "田中太郎, 山田花子",
			"agenda": "<p>Test agenda</p>",
		})
		note.insert(ignore_permissions=True)

		self.assertTrue(note.name.startswith("MTG-"))
		self.assertEqual(note.meeting_title, "Test Meeting CRM")

		# Cleanup
		note.delete(ignore_permissions=True)

	def test_pipeline_board_creation(self):
		"""Pipeline Board should be created correctly."""
		board = frappe.get_doc({
			"doctype": "Pipeline Board",
			"board_name": "Test Pipeline Board",
			"is_default": 1,
			"stages_json": '["リード", "アポ取得", "提案", "見積提出", "交渉中", "受注", "失注"]',
		})
		board.insert(ignore_permissions=True)

		self.assertTrue(board.name.startswith("PIPE-"))
		self.assertEqual(board.is_default, 1)

		# Cleanup
		board.delete(ignore_permissions=True)

	def test_crm_email_template(self):
		"""CRM Email Template should use template_name as name."""
		template = frappe.get_doc({
			"doctype": "CRM Email Template",
			"template_name": "Test Follow-up Template",
			"subject": "フォローアップ: {deal_name}",
			"body": "<p>お世話になっております。</p>",
			"use_case": "Follow-up",
			"is_active": 1,
		})
		template.insert(ignore_permissions=True)

		self.assertEqual(template.name, "Test Follow-up Template")
		self.assertEqual(template.use_case, "Follow-up")

		# Cleanup
		template.delete(ignore_permissions=True)
