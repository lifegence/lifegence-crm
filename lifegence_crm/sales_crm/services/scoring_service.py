import frappe


def recalculate_lead_scores():
	"""Recalculate lead scores based on scoring rules."""
	settings = frappe.get_single("CRM Settings")
	if not settings.enable_lead_scoring:
		return

	rules = frappe.get_all(
		"Lead Scoring Rule",
		filters={"is_active": 1},
		fields=["name", "field_name", "operator", "field_value", "score"],
	)
	if not rules:
		return

	leads = frappe.get_all("Lead", fields=["name"])
	for lead_ref in leads:
		try:
			lead = frappe.get_doc("Lead", lead_ref.name)
			total_score = 0
			for rule in rules:
				field_val = getattr(lead, rule.field_name, None)
				if _evaluate_rule(field_val, rule.operator, rule.field_value):
					total_score += rule.score
			lead.db_set("lead_score", max(0, min(100, total_score)), update_modified=False)
		except Exception:
			pass
	frappe.db.commit()


def _evaluate_rule(field_val, operator, rule_value):
	if operator == "is set":
		return bool(field_val)
	if operator == "is not set":
		return not bool(field_val)
	if field_val is None:
		return False
	field_str = str(field_val)
	if operator == "equals":
		return field_str == str(rule_value)
	if operator == "contains":
		return str(rule_value) in field_str
	try:
		fv = float(field_val)
		rv = float(rule_value)
		if operator == "greater than":
			return fv > rv
		if operator == "less than":
			return fv < rv
	except (ValueError, TypeError):
		pass
	return False
