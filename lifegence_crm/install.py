import frappe


def after_install():
	_init_settings()
	_create_roles()
	_seed_deal_stages()
	frappe.db.commit()
	print("Lifegence CRM: Installation complete.")


def _init_settings():
	frappe.reload_doc("sales_crm", "doctype", "crm_settings")
	settings = frappe.get_single("CRM Settings")
	if not settings.default_pipeline:
		settings.default_pipeline = "標準パイプライン"
		settings.enable_weighted_forecast = 1
		settings.deal_auto_numbering = 1
		settings.enable_lead_scoring = 1
		settings.min_score_for_hot = 80
		settings.scoring_recalculate_frequency = "Daily"
		settings.auto_activity_reminder = 1
		settings.reminder_days_before = 1
		settings.save(ignore_permissions=True)


def _create_roles():
	for role_name in ("Sales Manager", "Sales User"):
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
			}).insert(ignore_permissions=True)


def _seed_deal_stages():
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
