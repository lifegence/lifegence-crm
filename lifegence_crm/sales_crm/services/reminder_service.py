import frappe
from frappe.utils import add_days, nowdate


def send_activity_reminders():
	"""Send reminders for activities with upcoming next_action_date."""
	settings = frappe.get_single("Sales CRM Settings")
	if not settings.auto_activity_reminder:
		return

	reminder_date = add_days(nowdate(), settings.reminder_days_before or 1)
	activities = frappe.get_all(
		"Activity",
		filters={
			"next_action_date": reminder_date,
			"next_action": ["is", "set"],
		},
		fields=["name", "subject", "next_action", "next_action_date", "assigned_to"],
	)
	for activity in activities:
		if activity.assigned_to:
			frappe.sendmail(
				recipients=[activity.assigned_to],
				subject=f"リマインダー: {activity.next_action}",
				message=f"活動「{activity.subject}」の次アクション「{activity.next_action}」が{activity.next_action_date}に予定されています。",
			)
	frappe.db.commit()
