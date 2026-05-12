"""One-shot helper: set a Gemini API key everywhere agents look for it
and mark the existing LiteLLM Site Key inactive (force direct-Gemini route).

Usage:
    bench --site dev.localhost execute \\
        lifegence_crm.scripts._apply_gemini_key.run \\
        --kwargs '{"api_key": "AIza..."}'
"""
import frappe


def run(api_key: str):
    if not api_key:
        print("✗ api_key required")
        return
    # 1. Set the Gemini API key on the sales-demo-agent (encrypted field)
    agent_name = frappe.db.get_value(
        "Chat Agent", {"agent_name": "sales-demo-agent"}, "name"
    )
    if not agent_name:
        print("✗ sales-demo-agent not found")
        return
    doc = frappe.get_doc("Chat Agent", agent_name)
    doc.gemini_api_key = api_key
    doc.save(ignore_permissions=True)
    print(f"✓ gemini_api_key set on {agent_name}")

    # 2. Also set on the assistant agent so OpenClaw can fall back consistently
    a_name = frappe.db.get_value("Chat Agent", {"agent_name": "assistant"}, "name")
    if a_name:
        a = frappe.get_doc("Chat Agent", a_name)
        a.gemini_api_key = api_key
        a.save(ignore_permissions=True)
        print(f"✓ gemini_api_key set on {a_name} (assistant)")

    # 3. Clear / mark inactive the revoked LiteLLM Site Key so it doesn't
    #    poison routing (we want direct-Gemini, no proxy).
    n = frappe.db.sql(
        "UPDATE `tabLiteLLM Site Key` SET is_active = 0 WHERE site = %s",
        (frappe.local.site,)
    )
    frappe.db.commit()
    print(f"✓ LiteLLM Site Key marked inactive for site={frappe.local.site}")

    # 3b. Also set on the central Chat Settings + Company OS AI Settings —
    #     these are the canonical sources used by web_search, relay, gemini_live.
    try:
        cs = frappe.get_single("Chat Settings")
        cs.gemini_api_key = api_key
        cs.save(ignore_permissions=True)
        print("✓ gemini_api_key set on Chat Settings")
    except Exception as e:
        print(f"  Chat Settings update skipped: {e}")
    try:
        cos = frappe.get_single("Company OS AI Settings")
        cos.gemini_api_key = api_key
        cos.save(ignore_permissions=True)
        print("✓ gemini_api_key set on Company OS AI Settings")
    except Exception as e:
        print(f"  Company OS AI Settings update skipped: {e}")
    frappe.db.commit()

    # 4. Verify
    out = frappe.db.sql(
        """SELECT name, agent_name, llm_provider, LENGTH(gemini_api_key) AS key_len
           FROM `tabChat Agent` WHERE agent_name IN ('sales-demo-agent','assistant')""",
        as_dict=True,
    )
    for row in out:
        print(f"  {row}")
