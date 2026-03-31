"""Tests for scoring_service N+1 fix.

Verifies that recalculate_lead_scores uses batch queries
instead of per-lead get_doc calls.
"""

import unittest
from unittest.mock import patch, MagicMock, call

from lifegence_crm.sales_crm.services.scoring_service import (
	recalculate_lead_scores,
	_evaluate_rule,
)


class TestEvaluateRule(unittest.TestCase):
	"""Unit tests for _evaluate_rule (pure logic, no frappe dependency)."""

	def test_is_set_true(self):
		self.assertTrue(_evaluate_rule("hello", "is set", None))

	def test_is_set_false(self):
		self.assertFalse(_evaluate_rule(None, "is set", None))
		self.assertFalse(_evaluate_rule("", "is set", None))

	def test_is_not_set_true(self):
		self.assertTrue(_evaluate_rule(None, "is not set", None))
		self.assertTrue(_evaluate_rule("", "is not set", None))

	def test_is_not_set_false(self):
		self.assertFalse(_evaluate_rule("hello", "is not set", None))

	def test_equals(self):
		self.assertTrue(_evaluate_rule("tokyo", "equals", "tokyo"))
		self.assertFalse(_evaluate_rule("osaka", "equals", "tokyo"))

	def test_contains(self):
		self.assertTrue(_evaluate_rule("hello world", "contains", "world"))
		self.assertFalse(_evaluate_rule("hello", "contains", "world"))

	def test_greater_than(self):
		self.assertTrue(_evaluate_rule(10, "greater than", 5))
		self.assertFalse(_evaluate_rule(3, "greater than", 5))

	def test_less_than(self):
		self.assertTrue(_evaluate_rule(3, "less than", 5))
		self.assertFalse(_evaluate_rule(10, "less than", 5))

	def test_none_field_val_returns_false(self):
		self.assertFalse(_evaluate_rule(None, "equals", "x"))

	def test_non_numeric_comparison_returns_false(self):
		self.assertFalse(_evaluate_rule("abc", "greater than", "5"))


class TestRecalculateLeadScoresBatch(unittest.TestCase):
	"""Verify recalculate_lead_scores does NOT call get_doc per lead."""

	@patch("lifegence_crm.sales_crm.services.scoring_service.frappe")
	def test_no_get_doc_called(self, mock_frappe):
		"""recalculate_lead_scores should use get_all with fields, not get_doc."""
		# Setup: settings with scoring enabled
		mock_settings = MagicMock()
		mock_settings.enable_lead_scoring = True
		mock_frappe.get_single.return_value = mock_settings

		# Rules
		rule1 = MagicMock()
		rule1.field_name = "company_name"
		rule1.operator = "is set"
		rule1.field_value = None
		rule1.score = 20

		# Leads returned by get_all (with field values already included)
		lead1 = {"name": "LEAD-001", "company_name": "Acme Corp"}
		lead2 = {"name": "LEAD-002", "company_name": None}

		mock_frappe.get_all.side_effect = [
			[rule1],  # First call: rules
			[MagicMock(**lead1, get=lead1.get), MagicMock(**lead2, get=lead2.get)],  # Second call: leads
		]

		recalculate_lead_scores()

		# get_doc should NOT have been called for individual leads
		for c in mock_frappe.get_doc.call_args_list:
			self.assertNotEqual(c[0][0] if c[0] else None, "Lead",
				"get_doc should not be called with 'Lead' doctype")

		# get_all should have been called twice (rules + leads)
		self.assertEqual(mock_frappe.get_all.call_count, 2)

		# Second get_all call should include rule field names
		lead_call_args = mock_frappe.get_all.call_args_list[1]
		fields_arg = lead_call_args[1].get("fields") or lead_call_args[0][1] if len(lead_call_args[0]) > 1 else lead_call_args[1].get("fields")
		self.assertIn("company_name", fields_arg)

	@patch("lifegence_crm.sales_crm.services.scoring_service.frappe")
	def test_scoring_disabled_returns_early(self, mock_frappe):
		mock_settings = MagicMock()
		mock_settings.enable_lead_scoring = False
		mock_frappe.get_single.return_value = mock_settings

		recalculate_lead_scores()

		mock_frappe.get_all.assert_not_called()

	@patch("lifegence_crm.sales_crm.services.scoring_service.frappe")
	def test_no_rules_returns_early(self, mock_frappe):
		mock_settings = MagicMock()
		mock_settings.enable_lead_scoring = True
		mock_frappe.get_single.return_value = mock_settings
		mock_frappe.get_all.return_value = []

		recalculate_lead_scores()

		# Only one get_all call for rules, no second call for leads
		self.assertEqual(mock_frappe.get_all.call_count, 1)

	@patch("lifegence_crm.sales_crm.services.scoring_service.frappe")
	def test_score_clamped_to_0_100(self, mock_frappe):
		"""Score should be clamped between 0 and 100."""
		mock_settings = MagicMock()
		mock_settings.enable_lead_scoring = True
		mock_frappe.get_single.return_value = mock_settings

		# Create rules that total > 100
		rules = []
		for i in range(6):
			rule = MagicMock()
			rule.field_name = "company_name"
			rule.operator = "is set"
			rule.field_value = None
			rule.score = 25
			rules.append(rule)

		lead = {"name": "LEAD-001", "company_name": "Test"}
		mock_frappe.get_all.side_effect = [
			rules,
			[MagicMock(**lead, get=lead.get)],
		]

		recalculate_lead_scores()

		# db.set_value should be called with clamped value of 100
		mock_frappe.db.set_value.assert_called_once()
		args = mock_frappe.db.set_value.call_args
		self.assertEqual(args[0][3], 100)  # max(0, min(100, 150)) == 100
