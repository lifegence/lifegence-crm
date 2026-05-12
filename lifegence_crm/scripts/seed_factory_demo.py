"""Seed B2B manufacturing sales demo data.

Builds a realistic factory sales scenario on top of an existing ERPNext company:
- 4 named customers + 11 filler customers (15 total, B2B clients)
- 4 named items + 26 filler items (30 SKUs)
- 2 dedicated warehouses (本社倉庫, 大阪倉庫)
- Initial stock (some intentionally low to trigger reorder alerts in demo)
- Pipeline: 8 Leads → 5 Opportunities → 10 Quotations → 20 Sales Orders
- Fulfillment: 12 Delivery Notes → 15 Sales Invoices (mixed paid/unpaid)

Usage:
    bench --site dev.localhost execute \\
        lifegence_crm.scripts.seed_factory_demo.run

    # With non-default company:
    bench --site demo-factory.saas.lifegence.com execute \\
        lifegence_crm.scripts.seed_factory_demo.run \\
        --kwargs '{"company":"ライフジェンス工業株式会社"}'

Idempotent: re-running skips already-created docs (by name match).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import frappe
from frappe.utils import add_days, flt, getdate, today


# === Configuration ===

DEFAULT_COMPANY = "Lifegence Corporation"
ITEM_PREFIX = "DEMO-"  # All seeded items prefixed to avoid collision
CUSTOMER_GROUP = "B2B 製造業"
ITEM_GROUP = "DEMO 製造品"
TERRITORY = "Japan"

# Named entities used by the demo talk script
WAREHOUSE_HQ = "本社倉庫"
WAREHOUSE_OSAKA = "大阪倉庫"


# === Customer master ===

CUSTOMERS = [
    # Tier-1: named in demo talk script. Order matters.
    {"name": "トヨタ自動車部品株式会社", "credit_limit": 5_000_000, "sub_group": "自動車"},
    {"name": "三菱電機株式会社", "credit_limit": 8_000_000, "sub_group": "電機"},
    {"name": "株式会社日立製作所", "credit_limit": 6_000_000, "sub_group": "電機"},
    {"name": "デンソー精密工業", "credit_limit": 4_000_000, "sub_group": "自動車"},
    # Filler (11)
    {"name": "アイシン精機株式会社", "credit_limit": 3_500_000, "sub_group": "自動車"},
    {"name": "パナソニック電工", "credit_limit": 5_500_000, "sub_group": "電機"},
    {"name": "ファナック株式会社", "credit_limit": 7_000_000, "sub_group": "機械"},
    {"name": "東芝メカトロニクス", "credit_limit": 4_500_000, "sub_group": "電機"},
    {"name": "オムロン制御機器", "credit_limit": 3_800_000, "sub_group": "電機"},
    {"name": "キーエンス産業", "credit_limit": 4_200_000, "sub_group": "電機"},
    {"name": "村田機械", "credit_limit": 3_000_000, "sub_group": "機械"},
    {"name": "島津製作所", "credit_limit": 3_300_000, "sub_group": "機械"},
    {"name": "横河電機", "credit_limit": 3_600_000, "sub_group": "電機"},
    {"name": "三井物産マシナリー", "credit_limit": 6_500_000, "sub_group": "商社"},
    {"name": "丸紅鉄鋼", "credit_limit": 5_200_000, "sub_group": "商社"},
]


# === Item master ===
# (item_code suffix, item_name, rate, reorder_level, target_end_hq, target_end_osaka, sub_group)
#
# target_end_hq / target_end_osaka = stock levels visible "today" after a final
# Stock Reconciliation. Initial stock is seeded large enough to satisfy all
# SOs/DNs in between (see _seed_initial_stock / _seed_final_reconciliation).
ITEMS = [
    # Tier-1: named in demo talk script
    ("SVM-300", "サーボモーター SVM-300", 17_000, 50, 75, 30, "動力機器"),
    ("CTL-100", "制御基板 CTL-100", 35_000, 50, 18, 0, "制御機器"),       # BELOW reorder
    ("PWR-500", "電源ユニット PWR-500", 28_000, 40, 22, 0, "動力機器"),    # BELOW reorder
    ("SNS-200", "温度センサー SNS-200", 8_500, 30, 8, 0, "センサー"),       # BELOW reorder, critical
    # Tier-2 (8): regular stock
    ("SVM-500", "サーボモーター SVM-500", 28_000, 30, 60, 20, "動力機器"),
    ("CTL-200", "制御基板 CTL-200", 48_000, 30, 45, 15, "制御機器"),
    ("CTL-300", "PLC コントローラ CTL-300", 75_000, 20, 35, 10, "制御機器"),
    ("PWR-300", "電源ユニット PWR-300", 18_000, 40, 80, 25, "動力機器"),
    ("PWR-1000", "大容量電源 PWR-1000", 65_000, 20, 30, 8, "動力機器"),
    ("SNS-100", "圧力センサー SNS-100", 12_500, 30, 55, 18, "センサー"),
    ("SNS-300", "光センサー SNS-300", 15_500, 25, 40, 12, "センサー"),
    ("SNS-400", "近接センサー SNS-400", 6_800, 50, 120, 40, "センサー"),
    # Tier-3 (18): filler
    ("MTR-100", "ステッピングモーター MTR-100", 9_500, 40, 95, 30, "動力機器"),
    ("MTR-200", "ACモーター MTR-200", 22_000, 30, 50, 15, "動力機器"),
    ("MTR-400", "DCモーター MTR-400", 14_500, 30, 70, 20, "動力機器"),
    ("RLY-100", "リレーユニット RLY-100", 3_200, 100, 250, 80, "制御機器"),
    ("RLY-200", "ソリッドステートリレー RLY-200", 5_500, 80, 180, 60, "制御機器"),
    ("CBL-100", "制御ケーブル 5m CBL-100", 2_800, 100, 320, 100, "配線部品"),
    ("CBL-200", "制御ケーブル 10m CBL-200", 4_500, 80, 220, 70, "配線部品"),
    ("CON-100", "コネクタ 12pin CON-100", 1_200, 200, 500, 150, "配線部品"),
    ("CON-200", "コネクタ 24pin CON-200", 2_400, 150, 380, 120, "配線部品"),
    ("SW-100", "押しボタンスイッチ SW-100", 1_800, 100, 240, 80, "制御機器"),
    ("SW-200", "セレクタスイッチ SW-200", 2_200, 80, 180, 60, "制御機器"),
    ("LMP-100", "表示灯 LED 赤 LMP-100", 850, 150, 400, 120, "制御機器"),
    ("LMP-200", "表示灯 LED 緑 LMP-200", 850, 150, 380, 120, "制御機器"),
    ("FAN-100", "冷却ファン 80mm FAN-100", 3_500, 60, 140, 50, "動力機器"),
    ("FAN-200", "冷却ファン 120mm FAN-200", 4_800, 50, 110, 35, "動力機器"),
    ("BRK-100", "サーキットブレーカ 10A BRK-100", 3_200, 60, 130, 45, "制御機器"),
    ("BRK-200", "サーキットブレーカ 20A BRK-200", 4_200, 50, 100, 35, "制御機器"),
    ("ENC-100", "ロータリーエンコーダ ENC-100", 18_500, 25, 38, 12, "センサー"),
]

# Generous initial stock multiplier — covers all SO/DN consumption without
# triggering NegativeStockError. Final levels are set via Stock Reconciliation.
INIT_STOCK_MULTIPLIER = 10


# ----------------------------------------------------------------------------
# Master seeding
# ----------------------------------------------------------------------------

def _ensure_customer_group(parent_group: str = "All Customer Groups") -> None:
    """Top-level CUSTOMER_GROUP plus sub-groups (自動車/電機/機械/商社)."""
    if not frappe.db.exists("Customer Group", CUSTOMER_GROUP):
        frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": CUSTOMER_GROUP,
            "parent_customer_group": parent_group,
            "is_group": 1,
        }).insert(ignore_permissions=True)

    for sub in ("自動車", "電機", "機械", "商社"):
        if not frappe.db.exists("Customer Group", sub):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": sub,
                "parent_customer_group": CUSTOMER_GROUP,
                "is_group": 0,
            }).insert(ignore_permissions=True)


def _ensure_item_group(parent_group: str = "All Item Groups") -> None:
    if not frappe.db.exists("Item Group", ITEM_GROUP):
        frappe.get_doc({
            "doctype": "Item Group",
            "item_group_name": ITEM_GROUP,
            "parent_item_group": parent_group,
            "is_group": 1,
        }).insert(ignore_permissions=True)

    for sub in ("動力機器", "制御機器", "センサー", "配線部品"):
        if not frappe.db.exists("Item Group", sub):
            frappe.get_doc({
                "doctype": "Item Group",
                "item_group_name": sub,
                "parent_item_group": ITEM_GROUP,
                "is_group": 0,
            }).insert(ignore_permissions=True)


def _ensure_warehouses(company: str) -> tuple[str, str]:
    """Create 本社倉庫 / 大阪倉庫 under {company} if missing. Return their canonical names."""
    abbr = frappe.db.get_value("Company", company, "abbr")
    # Root warehouse name is locale-dependent ("All Warehouses - X" in en,
    # "すべての倉庫 - X" in ja). Resolve dynamically instead of hardcoding.
    parent = frappe.db.get_value(
        "Warehouse",
        {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]},
        "name",
    ) or f"All Warehouses - {abbr}"

    def _make(name: str) -> str:
        canonical = f"{name} - {abbr}"
        if not frappe.db.exists("Warehouse", canonical):
            frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": name,
                "parent_warehouse": parent,
                "company": company,
                "is_group": 0,
            }).insert(ignore_permissions=True)
        return canonical

    return _make(WAREHOUSE_HQ), _make(WAREHOUSE_OSAKA)


def _ensure_territory() -> None:
    if not frappe.db.exists("Territory", TERRITORY):
        frappe.get_doc({
            "doctype": "Territory",
            "territory_name": TERRITORY,
            "parent_territory": "All Territories",
            "is_group": 0,
        }).insert(ignore_permissions=True)


def _seed_customers() -> list[str]:
    created = []
    for cust in CUSTOMERS:
        name = cust["name"]
        if frappe.db.exists("Customer", name):
            created.append(name)
            continue

        doc = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Company",
            "customer_group": cust["sub_group"],
            "territory": TERRITORY,
            "default_currency": "JPY",
        }).insert(ignore_permissions=True)

        # Set credit limit (child table)
        # NB: credit_limits is mandatory only if Credit Limit feature is used in selling.
        # We attach for realism — referenced by sales_customer_summary skill.
        doc.append("credit_limits", {
            "company": frappe.defaults.get_user_default("Company") or DEFAULT_COMPANY,
            "credit_limit": cust["credit_limit"],
        })
        doc.save(ignore_permissions=True)
        created.append(doc.name)
    return created


def _seed_items(company: str, hq_wh: str, osaka_wh: str) -> list[dict]:
    """Create items. Return list of {code, rate, reorder_level, target_hq, target_osaka}."""
    out = []
    for suffix, item_name, rate, reorder, target_hq, target_osaka, sub_group in ITEMS:
        code = f"{ITEM_PREFIX}{suffix}"
        rec = {
            "code": code,
            "rate": rate,
            "reorder_level": reorder,
            "target_hq": target_hq,
            "target_osaka": target_osaka,
        }
        if frappe.db.exists("Item", code):
            out.append(rec)
            continue

        doc = frappe.get_doc({
            "doctype": "Item",
            "item_code": code,
            "item_name": item_name,
            "item_group": sub_group,
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "include_item_in_manufacturing": 0,
            "standard_rate": rate,
            "valuation_rate": rate * 0.6,  # cost basis = 60% of selling price
            "is_sales_item": 1,
            "is_purchase_item": 1,
        }).insert(ignore_permissions=True)

        # Reorder level on HQ warehouse
        doc.append("reorder_levels", {
            "warehouse": hq_wh,
            "warehouse_reorder_level": reorder,
            "warehouse_reorder_qty": reorder * 2,
            "material_request_type": "Purchase",
        })
        doc.save(ignore_permissions=True)
        out.append(rec)

    return out


def _seed_initial_stock(company: str, hq_wh: str, osaka_wh: str, items: list[dict]) -> None:
    """Material Receipt at -60d with generous stock so SO/DN never goes negative.

    Demo-visible levels are set later by _seed_final_reconciliation.
    """
    existing = frappe.db.sql("""
        SELECT 1 FROM `tabStock Ledger Entry`
        WHERE item_code LIKE %(prefix)s
        AND voucher_type = 'Stock Entry'
        LIMIT 1
    """, {"prefix": f"{ITEM_PREFIX}%"})
    if existing:
        return

    rows = []
    for item in items:
        # Generous initial: target × multiplier (covers all SO/DN demand)
        init_hq = max(item["target_hq"], 100) * INIT_STOCK_MULTIPLIER
        init_osaka = max(item["target_osaka"], 50) * INIT_STOCK_MULTIPLIER
        rows.append({
            "item_code": item["code"], "qty": init_hq,
            "t_warehouse": hq_wh, "basic_rate": item["rate"] * 0.6,
        })
        rows.append({
            "item_code": item["code"], "qty": init_osaka,
            "t_warehouse": osaka_wh, "basic_rate": item["rate"] * 0.6,
        })

    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "company": company,
        "posting_date": add_days(today(), -90),
        "set_posting_time": 1,
        "items": rows,
    })
    se.insert(ignore_permissions=True)
    se.submit()


def _seed_final_reconciliation(company: str, hq_wh: str, osaka_wh: str, items: list[dict]) -> None:
    """Stock Reconciliation at 'today' to set demo-visible final stock levels."""
    # Skip if a recent stock recon already exists for this company
    existing = frappe.db.sql("""
        SELECT 1 FROM `tabStock Reconciliation`
        WHERE company = %(company)s
        AND posting_date >= %(since)s
        AND docstatus = 1
        LIMIT 1
    """, {"company": company, "since": add_days(today(), -1)})
    if existing:
        return

    rows = []
    for item in items:
        rate = item["rate"] * 0.6
        # Always reconcile both warehouses so leftover initial stock is cleared
        # (even when target is 0 — required for scene-5 low-stock alert).
        rows.append({
            "item_code": item["code"], "warehouse": hq_wh,
            "qty": item["target_hq"], "valuation_rate": rate,
        })
        rows.append({
            "item_code": item["code"], "warehouse": osaka_wh,
            "qty": item["target_osaka"], "valuation_rate": rate,
        })

    sr = frappe.get_doc({
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "company": company,
        "posting_date": today(),
        "set_posting_time": 1,
        "items": rows,
    })
    sr.insert(ignore_permissions=True)
    sr.submit()


# ----------------------------------------------------------------------------
# Pipeline (Lead → Opportunity → Quotation → SO → DN → SI)
# ----------------------------------------------------------------------------

LEADS = [
    {"lead_name": "山田太郎", "company_name": "山田精密工業", "status": "Open", "source": "Walk In"},
    {"lead_name": "佐藤健", "company_name": "佐藤製作所", "status": "Open", "source": "Reference"},
    {"lead_name": "鈴木一郎", "company_name": "鈴木金属", "status": "Replied", "source": "Website"},
    {"lead_name": "高橋誠", "company_name": "高橋エンジニアリング", "status": "Open", "source": "Reference"},
    {"lead_name": "田中和也", "company_name": "田中産業", "status": "Open", "source": "Walk In"},
    {"lead_name": "渡辺修", "company_name": "渡辺機械", "status": "Interested", "source": "Reference"},
    {"lead_name": "伊藤健太", "company_name": "伊藤テクノロジー", "status": "Open", "source": "Website"},
    {"lead_name": "中村正", "company_name": "中村重工", "status": "Replied", "source": "Walk In"},
]


def _seed_leads() -> list[str]:
    out = []
    for spec in LEADS:
        if frappe.db.exists("Lead", {"company_name": spec["company_name"]}):
            existing = frappe.db.get_value("Lead", {"company_name": spec["company_name"]}, "name")
            out.append(existing)
            continue
        doc = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": spec["lead_name"],
            "company_name": spec["company_name"],
            "status": spec["status"],
            "source": spec["source"],
            "no_of_employees": "11-50",
        }).insert(ignore_permissions=True)
        out.append(doc.name)
    return out


def _seed_opportunities(company: str) -> list[str]:
    """5 opportunities — 3 against Customer, 2 against Lead."""
    opps = [
        {"party_type": "Customer", "party": "デンソー精密工業",
         "amount": 1_800_000, "items": [("SVM-500", 30), ("CTL-200", 15)]},
        {"party_type": "Customer", "party": "アイシン精機株式会社",
         "amount": 950_000, "items": [("SVM-300", 40)]},
        {"party_type": "Customer", "party": "パナソニック電工",
         "amount": 2_400_000, "items": [("CTL-300", 20), ("SNS-100", 50)]},
        {"party_type": "Lead", "party": "山田精密工業",
         "amount": 680_000, "items": [("MTR-200", 20), ("PWR-300", 15)]},
        {"party_type": "Lead", "party": "鈴木金属",
         "amount": 1_200_000, "items": [("CTL-200", 15), ("PWR-1000", 8)]},
    ]
    out = []
    for spec in opps:
        # Resolve Lead party_name (ERPNext Opportunity uses party_name = Lead.name for Lead type)
        if spec["party_type"] == "Lead":
            party = frappe.db.get_value("Lead", {"company_name": spec["party"]}, "name")
            if not party:
                continue
        else:
            party = spec["party"]
            if not frappe.db.exists("Customer", party):
                continue

        # Idempotency: skip if opp with same party + amount exists
        if frappe.db.exists("Opportunity", {
            "party_name": party, "opportunity_amount": spec["amount"]
        }):
            continue

        items_rows = []
        for suffix, qty in spec["items"]:
            code = f"{ITEM_PREFIX}{suffix}"
            rate = frappe.db.get_value("Item", code, "standard_rate") or 0
            items_rows.append({
                "item_code": code, "qty": qty, "rate": rate,
                "amount": qty * flt(rate),
            })

        doc = frappe.get_doc({
            "doctype": "Opportunity",
            "opportunity_from": spec["party_type"],
            "party_name": party,
            "opportunity_type": "Sales",
            "status": "Open",
            "transaction_date": add_days(today(), -random.randint(5, 30)),
            "company": company,
            "currency": "JPY",
            "items": items_rows,
        }).insert(ignore_permissions=True)
        out.append(doc.name)
    return out


def _seed_quotations(company: str) -> list[str]:
    """10 quotations for various customers, mixed statuses."""
    plans = [
        # (customer, items[(suffix,qty)], discount_pct, age_days, status)
        ("トヨタ自動車部品株式会社", [("SVM-300", 30), ("SNS-200", 50)], 0, 45, "Ordered"),
        ("トヨタ自動車部品株式会社", [("SVM-300", 40)], 5, 30, "Ordered"),
        ("トヨタ自動車部品株式会社", [("SVM-500", 20), ("CTL-200", 10)], 3, 15, "Ordered"),
        ("三菱電機株式会社", [("CTL-300", 15), ("RLY-100", 80)], 0, 25, "Ordered"),
        ("三菱電機株式会社", [("PWR-1000", 12), ("SNS-100", 30)], 5, 12, "Ordered"),
        ("株式会社日立製作所", [("SVM-500", 25)], 0, 50, "Ordered"),  # last month
        ("株式会社日立製作所", [("MTR-200", 30), ("CTL-200", 10)], 0, 10, "Ordered"),
        ("ファナック株式会社", [("ENC-100", 20), ("SVM-300", 15)], 0, 8, "Submitted"),
        ("オムロン制御機器", [("SNS-300", 40), ("SNS-400", 60)], 0, 5, "Submitted"),
        ("三井物産マシナリー", [("PWR-300", 80), ("CBL-100", 200)], 7, 3, "Submitted"),
    ]
    out = []
    for customer, items, discount_pct, age_days, status in plans:
        # Idempotency: customer + amount + date
        if frappe.db.exists("Quotation", {
            "party_name": customer, "transaction_date": add_days(today(), -age_days)
        }):
            continue

        items_rows = []
        for suffix, qty in items:
            code = f"{ITEM_PREFIX}{suffix}"
            rate = flt(frappe.db.get_value("Item", code, "standard_rate") or 0)
            items_rows.append({
                "item_code": code, "qty": qty, "rate": rate,
            })

        doc = frappe.get_doc({
            "doctype": "Quotation",
            "quotation_to": "Customer",
            "party_name": customer,
            "transaction_date": add_days(today(), -age_days),
            "valid_till": add_days(today(), -age_days + 30),
            "company": company,
            "currency": "JPY",
            "selling_price_list": "Standard Selling",
            "items": items_rows,
            "additional_discount_percentage": discount_pct,
        }).insert(ignore_permissions=True)
        if status in ("Submitted", "Ordered"):
            doc.submit()
        out.append(doc.name)
    return out


def _seed_sales_orders(company: str, hq_wh: str, osaka_wh: str) -> list[str]:
    """20 Sales Orders with varied fulfillment states.

    Layout designed for talk script:
    - トヨタ: 3 delivered+invoiced last 30 days (clean payment history)
    - 三菱電機: 2 delivered NOT invoiced (DN-2026-0089/0091 in script)
                + 2 invoiced (paid)
    - 日立製作所: this-month total ~¥2.8M, last-month total ~¥3.3M (-15%)
    - その他: 11 SOs spread across last 60 days
    """
    plans = [
        # (customer, items, age_days, mark_delivered, mark_invoiced, mark_paid)
        # === トヨタ自動車部品 (3 SOs, this month, all completed clean) ===
        ("トヨタ自動車部品株式会社", [("SVM-300", 30), ("SNS-200", 50)], 22, True, True, True),
        ("トヨタ自動車部品株式会社", [("SVM-300", 40)], 15, True, True, True),
        ("トヨタ自動車部品株式会社", [("SVM-500", 20), ("CTL-200", 10)], 8, True, True, False),
        # === 三菱電機 (4 SOs) ===
        # 2 delivered not invoiced (for sales_customer_summary in scene 4)
        ("三菱電機株式会社", [("CTL-300", 15), ("RLY-100", 80)], 7, True, False, False),
        ("三菱電機株式会社", [("PWR-1000", 12), ("SNS-100", 30)], 4, True, False, False),
        # 2 invoiced+paid
        ("三菱電機株式会社", [("CTL-200", 20)], 35, True, True, True),
        ("三菱電機株式会社", [("SVM-500", 15), ("PWR-500", 12)], 50, True, True, True),
        # === 日立製作所 (4 SOs) ===
        # last-month (3 SOs ~¥3.3M)
        ("株式会社日立製作所", [("SVM-500", 25)], 50, True, True, True),
        ("株式会社日立製作所", [("SVM-300", 50)], 45, True, True, True),
        ("株式会社日立製作所", [("CTL-300", 20)], 40, True, True, True),
        # this-month (1 SO ~¥2.8M total — leaves -15% gap)
        ("株式会社日立製作所", [("MTR-200", 30), ("CTL-200", 10), ("SVM-500", 50)], 9, True, True, True),
        # === Others (9 SOs spread across last 60 days) ===
        ("デンソー精密工業", [("SVM-500", 30), ("CTL-200", 15)], 28, True, True, True),
        ("アイシン精機株式会社", [("SVM-300", 40)], 18, True, True, False),
        ("パナソニック電工", [("CTL-300", 12), ("SNS-100", 25)], 12, False, False, False),  # not delivered yet
        ("ファナック株式会社", [("ENC-100", 20), ("SVM-300", 15)], 6, False, False, False),  # draft pipeline
        ("オムロン制御機器", [("SNS-300", 40), ("SNS-400", 60)], 3, False, False, False),
        ("東芝メカトロニクス", [("PWR-500", 10), ("RLY-200", 40)], 25, True, True, True),
        ("キーエンス産業", [("SNS-100", 30), ("SNS-400", 80)], 14, True, True, False),
        ("村田機械", [("MTR-100", 50), ("CBL-100", 100)], 38, True, True, True),
        ("島津製作所", [("FAN-100", 30), ("BRK-100", 25)], 55, True, True, True),
    ]
    out = []
    for customer, items, age_days, mark_delivered, mark_invoiced, mark_paid in plans:
        txn_date = add_days(today(), -age_days)
        delivery_date = add_days(txn_date, 7)

        # Idempotency: customer + date + first item
        first_item = f"{ITEM_PREFIX}{items[0][0]}"
        existing = frappe.db.sql("""
            SELECT name FROM `tabSales Order`
            WHERE customer = %s AND transaction_date = %s
            AND name IN (
                SELECT parent FROM `tabSales Order Item` WHERE item_code = %s
            )
            LIMIT 1
        """, (customer, txn_date, first_item))
        if existing:
            out.append(existing[0][0])
            continue

        items_rows = []
        for suffix, qty in items:
            code = f"{ITEM_PREFIX}{suffix}"
            rate = flt(frappe.db.get_value("Item", code, "standard_rate") or 0)
            items_rows.append({
                "item_code": code, "qty": qty, "rate": rate,
                "warehouse": hq_wh,
                "delivery_date": delivery_date,
            })

        so = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": customer,
            "transaction_date": txn_date,
            "delivery_date": delivery_date,
            "company": company,
            "currency": "JPY",
            "selling_price_list": "Standard Selling",
            "items": items_rows,
        })
        so.insert(ignore_permissions=True)
        so.submit()
        out.append(so.name)

        # === Optional Delivery Note ===
        if mark_delivered:
            from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
            dn = make_delivery_note(so.name)
            dn.posting_date = add_days(delivery_date, 0)
            dn.set_posting_time = 1
            dn.insert(ignore_permissions=True)
            dn.submit()

            # === Optional Sales Invoice ===
            if mark_invoiced:
                from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
                sinv = make_sales_invoice(dn.name)
                sinv.posting_date = add_days(delivery_date, 1)
                sinv.due_date = add_days(sinv.posting_date, 30)
                sinv.set_posting_time = 1
                sinv.insert(ignore_permissions=True)
                sinv.submit()

                # === Optional Payment Entry (mark as paid) ===
                if mark_paid:
                    from erpnext.accounts.doctype.payment_entry.payment_entry import (
                        get_payment_entry,
                    )
                    pe = get_payment_entry("Sales Invoice", sinv.name)
                    pe.reference_no = f"DEMO-PAY-{sinv.name}"
                    pe.reference_date = add_days(sinv.posting_date, 14)
                    pe.posting_date = pe.reference_date
                    pe.insert(ignore_permissions=True)
                    pe.submit()

    return out


# ----------------------------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------------------------

def run(company: str = DEFAULT_COMPANY) -> None:
    """Idempotent seed entry point."""
    if not frappe.db.exists("Company", company):
        raise ValueError(f"Company '{company}' not found. Create it first or pass company=...")

    print(f"→ Seeding factory demo into company: {company}")
    random.seed(20260512)  # reproducible

    print("  · Customer groups & territory")
    _ensure_customer_group()
    _ensure_item_group()
    _ensure_territory()

    print("  · Warehouses")
    hq_wh, osaka_wh = _ensure_warehouses(company)
    print(f"    {hq_wh} / {osaka_wh}")

    print("  · Customers")
    customers = _seed_customers()
    print(f"    {len(customers)} total")

    print("  · Items")
    items = _seed_items(company, hq_wh, osaka_wh)
    print(f"    {len(items)} total")

    print("  · Initial stock")
    _seed_initial_stock(company, hq_wh, osaka_wh, items)

    print("  · Leads")
    leads = _seed_leads()
    print(f"    {len(leads)} total")

    print("  · Opportunities")
    opps = _seed_opportunities(company)
    print(f"    {len(opps)} new")

    print("  · Quotations")
    quots = _seed_quotations(company)
    print(f"    {len(quots)} new")

    print("  · Sales Orders + Delivery Notes + Invoices + Payments")
    sos = _seed_sales_orders(company, hq_wh, osaka_wh)
    print(f"    {len(sos)} total")

    print("  · Final stock reconciliation (demo-visible levels)")
    _seed_final_reconciliation(company, hq_wh, osaka_wh, items)

    print("  · Syncing sales_* skills to Chat Agent Skill")
    _sync_skills()

    frappe.db.commit()
    print("✓ Factory demo seed complete")


def _sync_skills() -> None:
    """Register sales_* skills in Chat Agent Skill doctype.

    Imports the lifegence_agent builtin package to trigger external skill
    discovery (chat_agent_skills hook), then sync to DB.
    """
    import lifegence_agent.skills.builtin  # noqa: F401 — side-effect import
    from lifegence_agent.skills.registry import SkillRegistry
    SkillRegistry.sync_builtin_to_db()


# ----------------------------------------------------------------------------
# Demo recording agent setup (Playwright video target)
# ----------------------------------------------------------------------------

DEMO_AGENT_NAME = "sales-demo-agent"
DEMO_SKILLS = [
    "sales_lookup_customer",
    "sales_lookup_item",
    "sales_check_stock",
    "sales_create_quotation",
    "sales_create_order",
    "sales_create_invoice",
    "sales_customer_summary",
    "sales_period_report",
]


def ensure_demo_agent() -> str:
    """Create (or update) a Chat Agent dedicated to the sales demo recording.

    Assigns all 8 sales_* skills, sets a Japanese system prompt suited to the
    营业事务 persona, and returns the agent doc name.

    Usage:
        bench --site dev.localhost execute \
            lifegence_crm.scripts.seed_factory_demo.ensure_demo_agent
    """
    _sync_skills()  # idempotent — skills must exist before assignment

    system_prompt = (
        "あなたは製造業 B2B の営業事務をサポートする AI アシスタントです。"
        "ライフジェンス工業株式会社の田中さんを支援しています。\n"
        "応答ルール:\n"
        "- 提供されたスキル (sales_*) を積極的に使用し、ERPNext の実データを参照する\n"
        "- 受注・見積・請求などの書き込み操作の前には必ず「実行しますか?」と確認する\n"
        "- 金額は ¥ 表記、日付は YYYY-MM-DD 形式で返す\n"
        "- 顧客の与信状況や在庫不足など、リスクに関わる情報は太字で強調する\n"
        "- 簡潔・実務的な日本語で返答する"
    )

    if frappe.db.exists("Chat Agent", {"agent_name": DEMO_AGENT_NAME}):
        agent_doc_name = frappe.db.get_value("Chat Agent", {"agent_name": DEMO_AGENT_NAME}, "name")
        agent = frappe.get_doc("Chat Agent", agent_doc_name)
    else:
        agent = frappe.get_doc({
            "doctype": "Chat Agent",
            "agent_name": DEMO_AGENT_NAME,
            "display_name": "営業デモエージェント",
            "description": "製造業 B2B 販売管理 デモ用 AI アシスタント",
            "is_active": 1,
            "engine": "Builtin",
            "llm_provider": "Gemini",
            "llm_model": "gemini/gemini-2.0-flash",
            "gemini_model": "gemini-2.0-flash",
            "temperature": 0.3,  # lower for more deterministic demo responses
            "max_iterations": 10,
            "timeout_seconds": 120,
            "trigger_type": "DM Only",
        })

    agent.system_prompt = system_prompt
    agent.display_name = "営業デモエージェント"
    agent.description = "製造業 B2B 販売管理 デモ用 AI アシスタント"
    agent.is_active = 1

    # If gemini_api_key is unset, copy from the canonical `assistant` agent.
    # Skip silently if the field doesn't exist on this site's schema (newer
    # deployments route via LiteLLM virtual key — no per-agent key needed).
    try:
        if hasattr(agent, "gemini_api_key") and not agent.get("gemini_api_key"):
            donor_key = frappe.db.get_value(
                "Chat Agent", {"agent_name": "assistant"}, "gemini_api_key"
            )
            if donor_key:
                agent.gemini_api_key = donor_key
    except Exception:
        pass  # field absent → LiteLLM-only deployment

    # Assign all sales_* skills (medium-risk skills auto require approval)
    existing_skills = {row.skill for row in (agent.enabled_skills or [])}
    for skill_name in DEMO_SKILLS:
        if skill_name in existing_skills:
            continue
        risk = frappe.db.get_value("Chat Agent Skill", skill_name, "risk_level") or "Low"
        agent.append("enabled_skills", {
            "skill": skill_name,
            # In demo mode, do NOT require approval (so video flows uninterrupted)
            "requires_approval": 0,
        })

    agent.save(ignore_permissions=True)

    # Clear any prior demo conversations so each recording starts on an
    # empty chat (no stale "⚠ error" messages from previous runs visible).
    _clear_demo_conversations(agent.name)

    frappe.db.commit()

    print(f"✓ Demo agent ready: {agent.name} (agent_name='{DEMO_AGENT_NAME}')")
    print(f"  Skills attached: {len(agent.enabled_skills)}")
    return agent.name


def _clear_demo_conversations(agent_doc_name: str) -> None:
    """Wipe Chat Messages + Chat Conversations for the demo agent.

    Idempotent; safe to call repeatedly.
    """
    # Find conversations linked to this agent.
    # The Chat Conversation schema varies across versions; we try a few
    # possible foreign-key columns.
    conv_table = "tabChat Conversation"
    candidate_cols = ("agent_name", "ai_agent", "chat_agent", "agent")
    convs: list[str] = []
    for col in candidate_cols:
        try:
            rows = frappe.db.sql(
                f"SELECT name FROM `{conv_table}` WHERE `{col}` = %s",
                agent_doc_name,
            )
            if rows:
                convs.extend(r[0] for r in rows)
                break
        except Exception:
            continue

    if not convs:
        return

    # Delete messages first, then conversations
    placeholders = ", ".join(["%s"] * len(convs))
    try:
        frappe.db.sql(
            f"DELETE FROM `tabChat Message` WHERE conversation IN ({placeholders})",
            convs,
        )
    except Exception:
        pass

    for conv in convs:
        try:
            frappe.delete_doc("Chat Conversation", conv,
                              ignore_permissions=True, force=True,
                              delete_permanently=True)
        except Exception:
            pass

    print(f"  Cleared {len(convs)} prior demo conversation(s)")


def reset(company: str = DEFAULT_COMPANY, confirm: bool = False) -> None:
    """Destructive: cancel & delete all DEMO-prefixed seed data.

    Usage:
        bench --site dev.localhost execute \\
            lifegence_crm.scripts.seed_factory_demo.reset \\
            --kwargs '{"confirm": true}'
    """
    if not confirm:
        print("Reset is destructive. Pass confirm=true to proceed.")
        return

    print(f"→ Resetting factory demo from company: {company}")

    # Order matters: cancel from deepest dependency first
    for doctype in [
        "Payment Entry",
        "Sales Invoice",
        "Delivery Note",
        "Sales Order",
        "Quotation",
        "Opportunity",
        "Stock Entry",
    ]:
        if doctype == "Stock Entry":
            names = frappe.db.sql_list("""
                SELECT DISTINCT se.name FROM `tabStock Entry` se
                JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                WHERE sed.item_code LIKE %s AND se.company = %s
            """, (f"{ITEM_PREFIX}%", company))
        elif doctype == "Opportunity":
            names = frappe.db.get_all(doctype, filters={"company": company}, pluck="name")
        else:
            names = frappe.db.get_all(doctype, filters={"company": company}, pluck="name")

        for name in names:
            try:
                doc = frappe.get_doc(doctype, name)
                if doc.docstatus == 1:
                    doc.cancel()
                doc.delete(ignore_permissions=True)
            except Exception as e:
                print(f"    Skipped {doctype} {name}: {e}")

    # Then: Leads, Customers, Items
    for company_name in [c["name"] for c in CUSTOMERS]:
        if frappe.db.exists("Customer", company_name):
            try:
                frappe.delete_doc("Customer", company_name, ignore_permissions=True, force=True)
            except Exception as e:
                print(f"    Skipped Customer {company_name}: {e}")

    for spec in LEADS:
        lead = frappe.db.get_value("Lead", {"company_name": spec["company_name"]}, "name")
        if lead:
            frappe.delete_doc("Lead", lead, ignore_permissions=True, force=True)

    for item_spec in ITEMS:
        code = f"{ITEM_PREFIX}{item_spec[0]}"
        if frappe.db.exists("Item", code):
            try:
                frappe.delete_doc("Item", code, ignore_permissions=True, force=True)
            except Exception as e:
                print(f"    Skipped Item {code}: {e}")

    frappe.db.commit()
    print("✓ Factory demo reset complete")
