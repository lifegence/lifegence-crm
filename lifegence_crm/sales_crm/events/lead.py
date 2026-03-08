import frappe


def on_lead_created(doc, method):
	"""Auto-score new leads if scoring is enabled."""
	settings = frappe.get_single("CRM Settings")
	if not settings.enable_lead_scoring:
		return
	# Scoring will be done by the daily job; just log creation
	frappe.logger().info(f"CRM: New lead created: {doc.name}")
