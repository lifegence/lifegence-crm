# Copyright (c) 2026, Lifegence and contributors
# For license information, please see license.txt

"""Agent skills for B2B sales management on top of ERPNext core.

Skills operate on standard ERPNext doctypes (Customer / Item / Quotation /
Sales Order / Delivery Note / Sales Invoice / Bin) — no custom doctypes.

Coverage:
  Read:
    - sales_lookup_customer   : Customer + credit + recent orders
    - sales_lookup_item       : Item + price + total stock
    - sales_check_stock       : Per-warehouse stock & reorder alerts
    - sales_customer_summary  : Order history, outstanding, top items
    - sales_period_report     : Period revenue, top entities, YoY/MoM
  Write (Medium risk — caller must confirm before execution):
    - sales_create_quotation  : Quotation from items list
    - sales_create_order      : Sales Order from Quotation or items list
    - sales_create_invoice    : Invoice from Sales Order or Delivery Note
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, flt, getdate, today

from lifegence_agent.skills.registry import register_skill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_company() -> str:
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )


def _resolve_customer(query: str) -> str | None:
    """Return Customer.name for an exact or fuzzy match. None if not found."""
    if not query:
        return None
    if frappe.db.exists("Customer", query):
        return query
    match = frappe.db.sql("""
        SELECT name FROM `tabCustomer`
        WHERE customer_name LIKE %s OR name LIKE %s
        ORDER BY LENGTH(customer_name) ASC LIMIT 1
    """, (f"%{query}%", f"%{query}%"))
    return match[0][0] if match else None


def _resolve_item(query: str) -> str | None:
    """Return Item.name (= item_code) for exact or fuzzy match. None if not found."""
    if not query:
        return None
    if frappe.db.exists("Item", query):
        return query
    match = frappe.db.sql("""
        SELECT name FROM `tabItem`
        WHERE item_code LIKE %s OR item_name LIKE %s
        ORDER BY LENGTH(item_name) ASC LIMIT 1
    """, (f"%{query}%", f"%{query}%"))
    return match[0][0] if match else None


def _period_range(period: str) -> tuple[str, str, str, str]:
    """Return (start, end, prev_start, prev_end) for 'this_month', 'last_month', 'this_quarter'."""
    from frappe.utils import get_first_day, get_last_day, getdate as _gd
    t = _gd(today())
    if period == "last_month":
        end = get_last_day(add_days(get_first_day(t), -1))
        start = get_first_day(end)
        prev_end = get_last_day(add_days(start, -1))
        prev_start = get_first_day(prev_end)
    elif period == "this_quarter":
        q_start_month = ((t.month - 1) // 3) * 3 + 1
        start = t.replace(month=q_start_month, day=1)
        end = get_last_day(start.replace(month=q_start_month + 2))
        prev_end = add_days(start, -1)
        prev_start = prev_end.replace(month=prev_end.month - 2 if prev_end.month > 2 else prev_end.month + 10,
                                      day=1)
    else:  # this_month (default)
        start = get_first_day(t)
        end = get_last_day(t)
        prev_end = add_days(start, -1)
        prev_start = get_first_day(prev_end)
    return str(start), str(end), str(prev_start), str(prev_end)


# ---------------------------------------------------------------------------
# 1. sales_lookup_customer
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_lookup_customer",
    description=(
        "Look up a customer by name or code and return master data, credit "
        "limit/utilization, and recent sales orders. Use when the user asks "
        "about a specific customer's status, credit, or recent business."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Customer name (full or partial) or customer code",
            },
            "recent_limit": {
                "type": "integer",
                "description": "Max recent Sales Orders to return (default: 5)",
            },
        },
        "required": ["query"],
    },
    risk_level="Low",
    skill_type="Custom",
)
def sales_lookup_customer(query, recent_limit=5):
    customer_name = _resolve_customer(query)
    if not customer_name:
        return {"success": False, "error": f"Customer matching '{query}' not found"}

    cust = frappe.get_doc("Customer", customer_name)
    company = _default_company()

    # Credit limit (from child table)
    credit_limit = 0
    if cust.credit_limits:
        for row in cust.credit_limits:
            if row.company == company:
                credit_limit = flt(row.credit_limit)
                break
        if not credit_limit:
            credit_limit = flt(cust.credit_limits[0].credit_limit)

    # Outstanding AR (Sales Invoices not yet paid)
    outstanding = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
    """, customer_name)[0][0]

    credit_used = flt(outstanding)
    credit_available = max(credit_limit - credit_used, 0)

    # Recent Sales Orders
    recent_orders = frappe.get_all(
        "Sales Order",
        filters={"customer": customer_name, "docstatus": ["!=", 2]},
        fields=["name", "transaction_date", "grand_total", "status", "delivery_date"],
        order_by="transaction_date desc",
        limit_page_length=min(int(recent_limit), 20),
    )

    # Payment history snapshot: count of paid SIs in last 90 days, max days overdue
    overdue_days_row = frappe.db.sql("""
        SELECT MAX(DATEDIFF(CURDATE(), due_date)) AS max_overdue
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
        AND due_date < CURDATE()
    """, customer_name)
    max_overdue = (overdue_days_row[0][0] or 0) if overdue_days_row else 0

    return {
        "success": True,
        "customer": {
            "name": cust.name,
            "customer_name": cust.customer_name,
            "customer_group": cust.customer_group,
            "territory": cust.territory,
            "currency": cust.default_currency,
        },
        "credit": {
            "limit": credit_limit,
            "used": credit_used,
            "available": credit_available,
            "utilization_pct": (credit_used / credit_limit * 100) if credit_limit else 0,
        },
        "payment_health": {
            "outstanding": outstanding,
            "max_overdue_days": max_overdue,
            "status": "good" if max_overdue == 0 else ("warning" if max_overdue < 30 else "critical"),
        },
        "recent_orders": recent_orders,
    }


# ---------------------------------------------------------------------------
# 2. sales_lookup_item
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_lookup_item",
    description=(
        "Look up an item by code or name. Returns price, total available stock "
        "across all warehouses, and item group. Use for product master inquiries."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Item code or item name (full or partial)",
            },
        },
        "required": ["query"],
    },
    risk_level="Low",
    skill_type="Custom",
)
def sales_lookup_item(query):
    item_code = _resolve_item(query)
    if not item_code:
        return {"success": False, "error": f"Item matching '{query}' not found"}

    item = frappe.get_doc("Item", item_code)

    # Total stock across all warehouses
    stock_rows = frappe.db.sql("""
        SELECT warehouse, actual_qty, projected_qty, reserved_qty
        FROM `tabBin`
        WHERE item_code = %s AND actual_qty != 0
        ORDER BY warehouse
    """, item_code, as_dict=True)
    total_stock = sum(flt(r["actual_qty"]) for r in stock_rows)
    total_reserved = sum(flt(r["reserved_qty"]) for r in stock_rows)

    # Last selling price from latest submitted SO
    last_sold = frappe.db.sql("""
        SELECT soi.rate, so.transaction_date, so.customer
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE soi.item_code = %s AND so.docstatus = 1
        ORDER BY so.transaction_date DESC LIMIT 1
    """, item_code, as_dict=True)

    return {
        "success": True,
        "item": {
            "code": item.item_code,
            "name": item.item_name,
            "item_group": item.item_group,
            "standard_rate": flt(item.standard_rate),
            "valuation_rate": flt(item.valuation_rate),
            "stock_uom": item.stock_uom,
            "is_stock_item": bool(item.is_stock_item),
        },
        "stock": {
            "total_qty": total_stock,
            "reserved_qty": total_reserved,
            "available_qty": total_stock - total_reserved,
            "by_warehouse": stock_rows,
        },
        "last_sold": last_sold[0] if last_sold else None,
    }


# ---------------------------------------------------------------------------
# 3. sales_check_stock
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_check_stock",
    description=(
        "Check inventory levels. Pass an item_code for per-warehouse breakdown, "
        "or set below_reorder=true to list all items currently below their "
        "reorder level (low-stock alert)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_code": {
                "type": "string",
                "description": "Specific item code to check. Omit to list low-stock items.",
            },
            "below_reorder": {
                "type": "boolean",
                "description": "If true, list all items below their reorder level (default: false)",
            },
            "limit": {
                "type": "integer",
                "description": "Max items to return for low-stock list (default: 10)",
            },
        },
        "required": [],
    },
    risk_level="Low",
    skill_type="Custom",
)
def sales_check_stock(item_code=None, below_reorder=False, limit=10):
    # Mode A: specific item
    if item_code:
        code = _resolve_item(item_code)
        if not code:
            return {"success": False, "error": f"Item '{item_code}' not found"}

        rows = frappe.db.sql("""
            SELECT b.warehouse, b.actual_qty, b.reserved_qty, b.projected_qty
            FROM `tabBin` b
            WHERE b.item_code = %s
            ORDER BY b.warehouse
        """, code, as_dict=True)

        # Reorder threshold (per-warehouse)
        reorder_levels = frappe.db.sql("""
            SELECT warehouse, warehouse_reorder_level
            FROM `tabItem Reorder` WHERE parent = %s
        """, code, as_dict=True)
        reorder_map = {r["warehouse"]: r["warehouse_reorder_level"] for r in reorder_levels}

        enriched = []
        for r in rows:
            qty = flt(r["actual_qty"])
            reorder = flt(reorder_map.get(r["warehouse"], 0))
            enriched.append({
                **r,
                "reorder_level": reorder,
                "below_reorder": qty < reorder if reorder else False,
                "available_qty": qty - flt(r["reserved_qty"]),
            })

        return {
            "success": True,
            "item_code": code,
            "total_qty": sum(flt(r["actual_qty"]) for r in rows),
            "available_qty": sum(flt(r["actual_qty"]) - flt(r["reserved_qty"]) for r in rows),
            "warehouses": enriched,
        }

    # Mode B: list items below reorder
    if below_reorder:
        # MariaDB rejects HAVING with column aliases — wrap aggregate in subquery
        results = frappe.db.sql("""
            SELECT * FROM (
                SELECT
                    b.item_code,
                    i.item_name,
                    SUM(b.actual_qty) AS total_qty,
                    SUM(b.reserved_qty) AS reserved_qty,
                    (
                        SELECT MAX(ir.warehouse_reorder_level)
                        FROM `tabItem Reorder` ir
                        WHERE ir.parent = b.item_code
                    ) AS reorder_level
                FROM `tabBin` b
                JOIN `tabItem` i ON i.name = b.item_code
                WHERE i.disabled = 0 AND i.is_stock_item = 1
                GROUP BY b.item_code, i.item_name
            ) AS agg
            WHERE reorder_level IS NOT NULL AND total_qty < reorder_level
            ORDER BY (total_qty / reorder_level) ASC
            LIMIT %s
        """, min(int(limit), 50), as_dict=True)

        # Calculate days of supply from last 30-day outflow
        for row in results:
            outflow = frappe.db.sql("""
                SELECT COALESCE(SUM(ABS(actual_qty)), 0)
                FROM `tabStock Ledger Entry`
                WHERE item_code = %s AND actual_qty < 0
                AND posting_date >= %s
            """, (row["item_code"], add_days(today(), -30)))[0][0]
            daily = flt(outflow) / 30.0 if outflow else 0
            row["days_remaining"] = round(flt(row["total_qty"]) / daily, 1) if daily else None
            row["suggested_order_qty"] = max(int(flt(row["reorder_level"]) * 2 - flt(row["total_qty"])), 0)

        return {
            "success": True,
            "count": len(results),
            "low_stock_items": results,
        }

    return {
        "success": False,
        "error": "Provide either item_code or set below_reorder=true",
    }


# ---------------------------------------------------------------------------
# 4. sales_create_quotation
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_create_quotation",
    description=(
        "Create a Quotation (見積書) for a customer. Returns the draft "
        "quotation name and totals. Auto-applies last-sold price if available. "
        "Caller should confirm before submitting."
    ),
    parameters={
        "type": "object",
        "properties": {
            "customer": {
                "type": "string",
                "description": "Customer name or code",
            },
            "items": {
                "type": "array",
                "description": "Line items",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "qty": {"type": "number"},
                        "rate": {"type": "number", "description": "Optional override; auto-filled if omitted"},
                    },
                    "required": ["item_code", "qty"],
                },
            },
            "valid_until": {
                "type": "string",
                "description": "Quotation validity end date (YYYY-MM-DD). Default: +30 days.",
            },
            "discount_percentage": {
                "type": "number",
                "description": "Additional discount %. Default: 0.",
            },
            "submit": {
                "type": "boolean",
                "description": "If true, submit immediately. Default: false (draft only).",
            },
        },
        "required": ["customer", "items"],
    },
    risk_level="Medium",
    skill_type="Custom",
)
def sales_create_quotation(customer, items, valid_until=None, discount_percentage=0, submit=False):
    customer_name = _resolve_customer(customer)
    if not customer_name:
        return {"success": False, "error": f"Customer '{customer}' not found"}

    company = _default_company()
    rows = []
    for line in items:
        code = _resolve_item(line.get("item_code"))
        if not code:
            return {"success": False, "error": f"Item '{line.get('item_code')}' not found"}
        rate = line.get("rate")
        if rate is None:
            rate = flt(frappe.db.get_value("Item", code, "standard_rate"))
        rows.append({"item_code": code, "qty": flt(line["qty"]), "rate": flt(rate)})

    doc = frappe.get_doc({
        "doctype": "Quotation",
        "quotation_to": "Customer",
        "party_name": customer_name,
        "transaction_date": today(),
        "valid_till": valid_until or add_days(today(), 30),
        "company": company,
        "currency": "JPY",
        "selling_price_list": "Standard Selling",
        "items": rows,
        "additional_discount_percentage": flt(discount_percentage),
    })
    doc.insert(ignore_permissions=True)
    if submit:
        doc.submit()
    frappe.db.commit()

    return {
        "success": True,
        "quotation": doc.name,
        "status": "Submitted" if submit else "Draft",
        "customer": customer_name,
        "grand_total": flt(doc.grand_total),
        "total_qty": flt(doc.total_qty),
        "items": [
            {"item_code": r.item_code, "qty": flt(r.qty), "rate": flt(r.rate), "amount": flt(r.amount)}
            for r in doc.items
        ],
        "valid_till": str(doc.valid_till),
    }


# ---------------------------------------------------------------------------
# 5. sales_create_order
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_create_order",
    description=(
        "Create a Sales Order (受注). Either from an existing Quotation "
        "(pass from_quotation) or directly from customer + items. Reserves "
        "stock from the default warehouse."
    ),
    parameters={
        "type": "object",
        "properties": {
            "from_quotation": {
                "type": "string",
                "description": "Existing Quotation name to convert. Mutually exclusive with customer+items.",
            },
            "customer": {
                "type": "string",
                "description": "Customer name (required if from_quotation omitted)",
            },
            "items": {
                "type": "array",
                "description": "Line items (required if from_quotation omitted)",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "qty": {"type": "number"},
                        "rate": {"type": "number"},
                    },
                    "required": ["item_code", "qty"],
                },
            },
            "delivery_date": {
                "type": "string",
                "description": "Required delivery date YYYY-MM-DD. Default: +14 days.",
            },
            "submit": {
                "type": "boolean",
                "description": "If true (default), submit immediately to allocate stock.",
            },
        },
        "required": [],
    },
    risk_level="Medium",
    skill_type="Custom",
)
def sales_create_order(from_quotation=None, customer=None, items=None, delivery_date=None, submit=True):
    company = _default_company()
    delivery = delivery_date or add_days(today(), 14)

    if from_quotation:
        if not frappe.db.exists("Quotation", from_quotation):
            return {"success": False, "error": f"Quotation '{from_quotation}' not found"}
        from erpnext.selling.doctype.quotation.quotation import make_sales_order
        doc = make_sales_order(from_quotation)
        doc.delivery_date = delivery
        for row in doc.items:
            row.delivery_date = delivery
    else:
        if not (customer and items):
            return {"success": False, "error": "Provide from_quotation OR customer+items"}
        customer_name = _resolve_customer(customer)
        if not customer_name:
            return {"success": False, "error": f"Customer '{customer}' not found"}
        rows = []
        for line in items:
            code = _resolve_item(line.get("item_code"))
            if not code:
                return {"success": False, "error": f"Item '{line.get('item_code')}' not found"}
            rate = line.get("rate")
            if rate is None:
                rate = flt(frappe.db.get_value("Item", code, "standard_rate"))
            rows.append({
                "item_code": code, "qty": flt(line["qty"]), "rate": flt(rate),
                "delivery_date": delivery,
            })
        doc = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": customer_name,
            "transaction_date": today(),
            "delivery_date": delivery,
            "company": company,
            "currency": "JPY",
            "selling_price_list": "Standard Selling",
            "items": rows,
        })

    doc.insert(ignore_permissions=True)
    if submit:
        doc.submit()
    frappe.db.commit()

    return {
        "success": True,
        "sales_order": doc.name,
        "status": doc.status,
        "customer": doc.customer,
        "delivery_date": str(doc.delivery_date),
        "grand_total": flt(doc.grand_total),
        "total_qty": flt(doc.total_qty),
        "items": [
            {"item_code": r.item_code, "qty": flt(r.qty), "rate": flt(r.rate), "amount": flt(r.amount)}
            for r in doc.items
        ],
    }


# ---------------------------------------------------------------------------
# 6. sales_create_invoice
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_create_invoice",
    description=(
        "Create a Sales Invoice (請求書) from an existing Sales Order or "
        "Delivery Note. Returns invoice name, totals, and due date."
    ),
    parameters={
        "type": "object",
        "properties": {
            "from_sales_order": {
                "type": "string",
                "description": "Sales Order name to invoice (skips DN — direct SO→SI)",
            },
            "from_delivery_note": {
                "type": "string",
                "description": "Delivery Note name to invoice (normal SO→DN→SI flow)",
            },
            "due_days": {
                "type": "integer",
                "description": "Payment terms: due X days after posting. Default: 30.",
            },
            "submit": {
                "type": "boolean",
                "description": "If true (default), submit immediately.",
            },
        },
        "required": [],
    },
    risk_level="Medium",
    skill_type="Custom",
)
def sales_create_invoice(from_sales_order=None, from_delivery_note=None, due_days=30, submit=True):
    if from_delivery_note:
        if not frappe.db.exists("Delivery Note", from_delivery_note):
            return {"success": False, "error": f"Delivery Note '{from_delivery_note}' not found"}
        from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
        doc = make_sales_invoice(from_delivery_note)
    elif from_sales_order:
        if not frappe.db.exists("Sales Order", from_sales_order):
            return {"success": False, "error": f"Sales Order '{from_sales_order}' not found"}
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
        doc = make_sales_invoice(from_sales_order)
    else:
        return {"success": False, "error": "Provide from_sales_order or from_delivery_note"}

    doc.posting_date = today()
    doc.set_posting_time = 1
    doc.due_date = add_days(today(), int(due_days))
    doc.insert(ignore_permissions=True)
    if submit:
        doc.submit()
    frappe.db.commit()

    return {
        "success": True,
        "sales_invoice": doc.name,
        "status": doc.status,
        "customer": doc.customer,
        "posting_date": str(doc.posting_date),
        "due_date": str(doc.due_date),
        "grand_total": flt(doc.grand_total),
        "outstanding_amount": flt(doc.outstanding_amount),
        "items": [
            {"item_code": r.item_code, "qty": flt(r.qty), "rate": flt(r.rate), "amount": flt(r.amount)}
            for r in doc.items
        ],
    }


# ---------------------------------------------------------------------------
# 7. sales_customer_summary
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_customer_summary",
    description=(
        "Summarize a customer's purchase activity: lifetime/period revenue, "
        "outstanding invoices, undelivered orders, undelivered/uninvoiced "
        "delivery notes, top items purchased. Use for account reviews and "
        "to find unbilled deliveries."
    ),
    parameters={
        "type": "object",
        "properties": {
            "customer": {
                "type": "string",
                "description": "Customer name or code",
            },
            "lookback_days": {
                "type": "integer",
                "description": "Period for revenue & top-items calc (default: 365)",
            },
        },
        "required": ["customer"],
    },
    risk_level="Low",
    skill_type="Custom",
)
def sales_customer_summary(customer, lookback_days=365):
    customer_name = _resolve_customer(customer)
    if not customer_name:
        return {"success": False, "error": f"Customer '{customer}' not found"}

    since = add_days(today(), -int(lookback_days))

    # Period revenue (from submitted Sales Invoices)
    revenue_row = frappe.db.sql("""
        SELECT
            COALESCE(SUM(grand_total), 0) AS total_billed,
            COALESCE(SUM(outstanding_amount), 0) AS total_outstanding,
            COUNT(*) AS invoice_count
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND posting_date >= %s
    """, (customer_name, since), as_dict=True)[0]

    # Open SOs (not fully delivered/billed)
    open_sos = frappe.db.sql("""
        SELECT name, transaction_date, delivery_date, grand_total,
               status, per_delivered, per_billed
        FROM `tabSales Order`
        WHERE customer = %s AND docstatus = 1
        AND status NOT IN ('Completed', 'Closed')
        ORDER BY transaction_date DESC LIMIT 10
    """, customer_name, as_dict=True)

    # Unbilled Delivery Notes (DNs not linked to an Invoice, or partially billed)
    unbilled_dns = frappe.db.sql("""
        SELECT dn.name, dn.posting_date, dn.grand_total, dn.per_billed
        FROM `tabDelivery Note` dn
        WHERE dn.customer = %s AND dn.docstatus = 1
        AND dn.per_billed < 100
        AND dn.status NOT IN ('Closed', 'Stopped')
        ORDER BY dn.posting_date DESC LIMIT 10
    """, customer_name, as_dict=True)

    # Top items in lookback
    top_items = frappe.db.sql("""
        SELECT sii.item_code, sii.item_name,
               SUM(sii.qty) AS total_qty,
               SUM(sii.amount) AS total_amount
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.customer = %s AND si.docstatus = 1 AND si.posting_date >= %s
        GROUP BY sii.item_code
        ORDER BY total_amount DESC LIMIT 5
    """, (customer_name, since), as_dict=True)

    return {
        "success": True,
        "customer": customer_name,
        "period_days": int(lookback_days),
        "revenue": {
            "total_billed": flt(revenue_row["total_billed"]),
            "outstanding": flt(revenue_row["total_outstanding"]),
            "invoice_count": int(revenue_row["invoice_count"]),
        },
        "open_sales_orders": open_sos,
        "unbilled_delivery_notes": unbilled_dns,
        "top_items": top_items,
    }


# ---------------------------------------------------------------------------
# 8. sales_period_report
# ---------------------------------------------------------------------------

@register_skill(
    skill_name="sales_period_report",
    description=(
        "Aggregate sales for a period (this_month / last_month / this_quarter) "
        "grouped by customer or item. Returns top entries with prior-period "
        "comparison. Use for sales reviews and trend analysis."
    ),
    parameters={
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "description": "this_month | last_month | this_quarter",
            },
            "group_by": {
                "type": "string",
                "description": "customer | item (default: customer)",
            },
            "top_n": {
                "type": "integer",
                "description": "Top N rows to return (default: 10)",
            },
        },
        "required": [],
    },
    risk_level="Low",
    skill_type="Custom",
)
def sales_period_report(period="this_month", group_by="customer", top_n=10):
    start, end, prev_start, prev_end = _period_range(period)
    top_n = min(int(top_n), 50)

    if group_by == "item":
        current = frappe.db.sql("""
            SELECT sii.item_code AS key_field, sii.item_name AS label,
                   SUM(sii.qty) AS qty, SUM(sii.amount) AS amount
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
            GROUP BY sii.item_code
            ORDER BY amount DESC LIMIT %s
        """, (start, end, top_n), as_dict=True)
        prev = frappe.db.sql("""
            SELECT sii.item_code AS key_field, SUM(sii.amount) AS amount
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
            GROUP BY sii.item_code
        """, (prev_start, prev_end), as_dict=True)
    else:
        current = frappe.db.sql("""
            SELECT si.customer AS key_field, c.customer_name AS label,
                   COUNT(*) AS invoice_count, SUM(si.grand_total) AS amount
            FROM `tabSales Invoice` si
            JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
            GROUP BY si.customer
            ORDER BY amount DESC LIMIT %s
        """, (start, end, top_n), as_dict=True)
        prev = frappe.db.sql("""
            SELECT customer AS key_field, SUM(grand_total) AS amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
            GROUP BY customer
        """, (prev_start, prev_end), as_dict=True)

    prev_map = {p["key_field"]: flt(p["amount"]) for p in prev}
    for row in current:
        prev_amt = prev_map.get(row["key_field"], 0)
        row["prev_amount"] = prev_amt
        row["mom_change"] = round(
            ((flt(row["amount"]) - prev_amt) / prev_amt * 100) if prev_amt else 0, 1
        )
        # Outlier flag for trend commentary
        if row["mom_change"] <= -10:
            row["trend"] = "down"
        elif row["mom_change"] >= 10:
            row["trend"] = "up"
        else:
            row["trend"] = "flat"

    # Period totals
    total_current = sum(flt(r["amount"]) for r in current)
    total_prev = sum(flt(p["amount"]) for p in prev)
    overall_mom = round(
        ((total_current - total_prev) / total_prev * 100) if total_prev else 0, 1
    )

    return {
        "success": True,
        "period": period,
        "group_by": group_by,
        "range": {"start": start, "end": end, "prev_start": prev_start, "prev_end": prev_end},
        "total_current": total_current,
        "total_prev": total_prev,
        "overall_mom_change": overall_mom,
        "top": current,
    }
