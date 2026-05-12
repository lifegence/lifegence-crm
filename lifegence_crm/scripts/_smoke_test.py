"""Smoke test helpers for sales skills."""
import json


def setup_demo_agent():
    """Create/refresh the sales-demo-agent used by Playwright recording."""
    try:
        from lifegence_crm.scripts.seed_factory_demo import ensure_demo_agent
        name = ensure_demo_agent()
        print(f"Agent ready: {name}")
    except Exception as e:
        import traceback
        print(f"FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()


def test_agent_response():
    """Send a single message to sales-demo-agent and print the response."""
    import frappe

    agent_name = frappe.db.get_value("Chat Agent", {"agent_name": "sales-demo-agent"}, "name")
    print(f"Agent: {agent_name}")

    try:
        # Invoke via the canonical agent API (uses _create_runner factory)
        from lifegence_agent.api.agent import invoke_agent
        # Need an existing conversation; pick the first DM with this agent or create one
        conv = frappe.db.get_value(
            "Chat Conversation",
            {"agent": agent_name},
            "name",
        )
        if not conv:
            cdoc = frappe.get_doc({
                "doctype": "Chat Conversation",
                "conversation_type": "AI Direct",
                "agent": agent_name,
                "title": "smoke-test",
            }).insert(ignore_permissions=True)
            conv = cdoc.name
            frappe.db.commit()
        print(f"Conversation: {conv}")
        result = invoke_agent(
            agent_name=agent_name,
            message="トヨタ自動車部品さんの与信状況を教えて",
            conversation=conv,
        )
        print(f"RESULT: {json.dumps(result, ensure_ascii=False, default=str)[:600]}")
    except Exception as e:
        import traceback
        print(f"FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()


def sync_skills():
    """Sync all decorator-registered skills to Chat Agent Skill doctype."""
    # Trigger external skill discovery (hooks.chat_agent_skills).
    # Force-import the sales module explicitly: on long-running workers the
    # hook may have been resolved before sales_skills.py existed, leaving
    # the @register_skill decorator unfired.
    import lifegence_agent.skills.builtin  # noqa: F401  — side-effect import
    import lifegence_crm.sales_crm.skills.sales_skills  # noqa: F401
    from lifegence_agent.skills.registry import SkillRegistry
    before = len(SkillRegistry._builtin_skills)
    SkillRegistry.sync_builtin_to_db()
    sales_count = sum(1 for k in SkillRegistry._builtin_skills if k.startswith("sales_"))
    print(f"✓ Skills synced ({before} registered, {sales_count} sales_*)")


def list_sales_skills():
    """List registered sales_* skills."""
    import frappe
    skills = frappe.get_all(
        "Chat Agent Skill",
        filters={"skill_name": ["like", "sales_%"]},
        fields=["skill_name", "skill_type", "risk_level", "is_active"],
    )
    print(json.dumps(skills, ensure_ascii=False, indent=2))
