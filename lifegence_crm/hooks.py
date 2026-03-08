app_name = "lifegence_crm"
app_title = "Lifegence CRM"
app_publisher = "Lifegence"
app_description = "Sales management for Lifegence Company OS"
app_email = "info@lifegence.co.jp"
app_license = "mit"

required_apps = ["frappe", "erpnext"]

export_python_type_annotations = True

# AI Agent Skills (F4 plugin)
chat_agent_skills = ["lifegence_crm.sales_crm.skills.crm_skills"]

after_install = "lifegence_crm.install.after_install"

add_to_apps_screen = [
	{
		"name": "lifegence_crm",
		"logo": "/assets/lifegence_crm/images/crm-logo.svg",
		"title": "営業管理",
		"route": "/app/crm",
	},
]

doc_events = {
	"Lead": {
		"after_insert": "lifegence_crm.sales_crm.events.lead.on_lead_created",
	},
}

scheduler_events = {
	"daily": [
		"lifegence_crm.sales_crm.services.reminder_service.send_activity_reminders",
		"lifegence_crm.sales_crm.services.scoring_service.recalculate_lead_scores",
	],
}

fixtures = [
	"Sales CRM Settings",
	{
		"dt": "Deal Stage",
		"filters": [["stage_name", "like", "%"]],
	},
]
