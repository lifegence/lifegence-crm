# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

import frappe
from lifegence_agent.skills.registry import register_skill


@register_skill(
	skill_name="crm_deal_summary",
	description="Get a summary of the sales pipeline: deal counts by stage, total/weighted value, recent deals, and forecast. Use when the user asks about sales status, pipeline overview, or revenue forecast.",
	parameters={
		"type": "object",
		"properties": {
			"stage": {
				"type": "string",
				"description": "Filter by deal stage name (e.g., '提案', '交渉中'). Leave empty for all stages.",
			},
			"limit": {
				"type": "integer",
				"description": "Max number of recent deals to return (default: 10)",
			},
		},
		"required": [],
	},
	risk_level="Low",
	skill_type="Custom",
)
def crm_deal_summary(stage=None, limit=10):
	"""Summarize the CRM deal pipeline."""
	filters = {}
	if stage:
		filters["stage"] = stage

	# Pipeline summary by stage
	pipeline = frappe.db.sql(
		"""
		SELECT stage, COUNT(*) as count,
			SUM(deal_value) as total_value,
			SUM(weighted_value) as total_weighted
		FROM `tabDeal`
		WHERE docstatus < 2
		{stage_filter}
		GROUP BY stage
		ORDER BY FIELD(stage, 'リード','アポ取得','提案','見積提出','交渉中','受注','失注')
		""".format(
			stage_filter=f"AND stage = %(stage)s" if stage else ""
		),
		filters,
		as_dict=True,
	)

	# Recent deals
	recent = frappe.get_all(
		"Deal",
		filters=filters,
		fields=["name", "deal_name", "stage", "deal_value", "weighted_value", "customer", "modified"],
		order_by="modified desc",
		limit_page_length=min(limit, 50),
	)

	# Won/lost stats this month
	from frappe.utils import get_first_day, get_last_day, today

	month_start = get_first_day(today())
	month_end = get_last_day(today())

	won_count = frappe.db.count("Deal", {"stage": "受注", "modified": ["between", [month_start, month_end]]})
	lost_count = frappe.db.count("Deal", {"stage": "失注", "modified": ["between", [month_start, month_end]]})

	return {
		"success": True,
		"pipeline": pipeline,
		"recent_deals": recent,
		"this_month": {"won": won_count, "lost": lost_count},
		"total_deals": frappe.db.count("Deal", filters),
	}


@register_skill(
	skill_name="crm_suggest_next_action",
	description="Analyze a deal's history and suggest the next best action. Provide a deal name to get recommendations based on the deal's stage, last activity date, and deal value.",
	parameters={
		"type": "object",
		"properties": {
			"deal_name": {
				"type": "string",
				"description": "The Deal document name (ID) to analyze",
			},
		},
		"required": ["deal_name"],
	},
	risk_level="Low",
	skill_type="Custom",
)
def crm_suggest_next_action(deal_name):
	"""Suggest next action for a deal based on its current state."""
	if not frappe.db.exists("Deal", deal_name):
		return {"success": False, "error": f"Deal '{deal_name}' not found"}

	deal = frappe.get_doc("Deal", deal_name)

	# Get recent activities
	activities = frappe.get_all(
		"Activity",
		filters={"deal": deal_name},
		fields=["activity_type", "subject", "activity_date", "status"],
		order_by="activity_date desc",
		limit_page_length=10,
	)

	# Calculate days since last activity
	from frappe.utils import date_diff, today

	days_inactive = 0
	if activities:
		days_inactive = date_diff(today(), activities[0].activity_date)
	else:
		days_inactive = date_diff(today(), deal.creation)

	# Stage-based recommendations
	stage_actions = {
		"リード": "初回コンタクトを取りましょう。電話またはメールでニーズをヒアリングしてください。",
		"アポ取得": "訪問日程を確定し、提案資料を準備してください。",
		"提案": "提案内容のフォローアップを行い、質問や懸念点を確認してください。",
		"見積提出": "見積の検討状況を確認し、必要に応じて条件調整を行ってください。",
		"交渉中": "最終条件の合意に向けて、決裁者との面談を調整してください。",
		"受注": "契約書の締結と導入スケジュールの確定を進めてください。",
		"失注": "失注理由を分析し、再アプローチの可能性を検討してください。",
	}

	suggestion = stage_actions.get(deal.stage, "現在のステージに適したアクションを検討してください。")

	if days_inactive > 14:
		urgency = "urgent"
		suggestion = f"⚠ {days_inactive}日間活動がありません。早急にフォローアップが必要です。\n{suggestion}"
	elif days_inactive > 7:
		urgency = "warning"
		suggestion = f"注意: {days_inactive}日間活動がありません。\n{suggestion}"
	else:
		urgency = "normal"

	return {
		"success": True,
		"deal": {
			"name": deal.name,
			"deal_name": deal.deal_name,
			"stage": deal.stage,
			"deal_value": deal.deal_value,
			"customer": deal.customer,
		},
		"days_inactive": days_inactive,
		"urgency": urgency,
		"suggestion": suggestion,
		"recent_activities": activities[:5],
	}


@register_skill(
	skill_name="crm_lead_qualification",
	description="Score and qualify leads based on available data. Returns a list of leads with their qualification status and recommended priority.",
	parameters={
		"type": "object",
		"properties": {
			"limit": {
				"type": "integer",
				"description": "Max leads to analyze (default: 20)",
			},
			"status": {
				"type": "string",
				"description": "Filter by lead status (e.g., 'Lead', 'Open', 'Replied')",
			},
		},
		"required": [],
	},
	risk_level="Low",
	skill_type="Custom",
)
def crm_lead_qualification(limit=20, status=None):
	"""Score and qualify leads based on their data."""
	filters = {}
	if status:
		filters["status"] = status

	leads = frappe.get_all(
		"Lead",
		filters=filters,
		fields=[
			"name", "lead_name", "company_name", "status", "source",
			"creation", "modified", "lead_owner",
		],
		order_by="creation desc",
		limit_page_length=min(limit, 50),
	)

	qualified = []
	for lead in leads:
		score = 0
		reasons = []

		# Company name provided
		if lead.company_name:
			score += 20
			reasons.append("企業名あり")

		# Source quality
		high_sources = ["Referral", "紹介", "Website", "ウェブサイト"]
		if lead.source and lead.source in high_sources:
			score += 15
			reasons.append(f"高品質ソース: {lead.source}")

		# Recency
		from frappe.utils import date_diff, today
		age = date_diff(today(), lead.creation)
		if age <= 7:
			score += 25
			reasons.append("直近1週間のリード")
		elif age <= 30:
			score += 15
			reasons.append("直近1ヶ月のリード")

		# Engagement (has activities or communications)
		comm_count = frappe.db.count("Communication", {"reference_doctype": "Lead", "reference_name": lead.name})
		if comm_count >= 3:
			score += 25
			reasons.append(f"コミュニケーション{comm_count}件")
		elif comm_count >= 1:
			score += 15
			reasons.append(f"コミュニケーション{comm_count}件")

		# Owner assigned
		if lead.lead_owner:
			score += 10
			reasons.append("担当者割当済み")

		# Classify
		if score >= 70:
			priority = "Hot"
		elif score >= 40:
			priority = "Warm"
		else:
			priority = "Cold"

		qualified.append({
			"lead": lead.name,
			"lead_name": lead.lead_name,
			"company": lead.company_name,
			"score": score,
			"priority": priority,
			"reasons": reasons,
		})

	# Sort by score descending
	qualified.sort(key=lambda x: x["score"], reverse=True)

	return {
		"success": True,
		"count": len(qualified),
		"leads": qualified,
		"summary": {
			"hot": len([q for q in qualified if q["priority"] == "Hot"]),
			"warm": len([q for q in qualified if q["priority"] == "Warm"]),
			"cold": len([q for q in qualified if q["priority"] == "Cold"]),
		},
	}
