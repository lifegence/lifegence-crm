import frappe


def recalculate_lead_scores():
	"""Recalculate lead scores based on scoring rules."""
	settings = frappe.get_single("Sales CRM Settings")
	if not settings.enable_lead_scoring:
		return

	rules = frappe.get_all(
		"Lead Scoring Rule",
		filters={"is_active": 1},
		fields=["name", "field_name", "operator", "field_value", "score"],
	)
	if not rules:
		return

	# Collect all field names needed by rules to fetch in a single query
	rule_fields = list({rule.field_name for rule in rules})
	lead_fields = ["name"] + [f for f in rule_fields if f != "name"]

	leads = frappe.get_all("Lead", fields=lead_fields)
	for lead in leads:
		try:
			total_score = 0
			for rule in rules:
				field_val = lead.get(rule.field_name)
				if _evaluate_rule(field_val, rule.operator, rule.field_value):
					total_score += rule.score
			frappe.db.set_value(
				"Lead", lead.name, "lead_score",
				max(0, min(100, total_score)), update_modified=False,
			)
		except Exception:
			frappe.log_error(title="CRM Scoring: Failed to score lead {0}".format(lead.get("name", "unknown")))
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
