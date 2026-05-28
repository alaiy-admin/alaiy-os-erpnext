import frappe


def generate_alerts():
    """Run every 15 min. Check reorder points and late shipments."""
    _check_reorder_alerts()
    _check_late_shipment_alerts()


def _check_reorder_alerts():
    """Create Marketplace Alert for SKUs below reorder point."""
    policies = frappe.get_all("Reorder Policy", fields=["*"])
    for policy in policies:
        bin_qty = frappe.db.get_value(
            "Bin",
            {"item_code": policy.item_code, "warehouse": policy.warehouse},
            "actual_qty",
        ) or 0

        if bin_qty <= (policy.reorder_point or 0):
            existing = frappe.db.exists("Marketplace Alert", {
                "item_code": policy.item_code,
                "alert_type": "Reorder",
                "status": ["in", ["Open", "Snoozed"]],
            })
            if not existing:
                alert = frappe.new_doc("Marketplace Alert")
                alert.alert_type = "Reorder"
                alert.severity = "fire" if bin_qty <= (policy.safety_stock or 0) else "warn"
                alert.item_code = policy.item_code
                alert.marketplace = "amazon_in"
                alert.title = f"Low stock — {policy.item_code}"
                alert.description = (
                    f"{int(bin_qty)} units left at {policy.warehouse}. "
                    f"Reorder point: {policy.reorder_point}. "
                    f"Suggest ordering {policy.reorder_qty or 20} units."
                )
                alert.status = "Open"
                alert.flags.ignore_mandatory = True
                alert.insert(ignore_permissions=True)
    frappe.db.commit()


def _check_late_shipment_alerts():
    """Create alerts for Sales Orders due today that have not been dispatched."""
    today = frappe.utils.today()
    overdue_orders = frappe.db.sql("""
        SELECT name, customer, transaction_date
        FROM `tabSales Order`
        WHERE delivery_date <= %s
        AND status NOT IN ('Completed', 'Cancelled')
        AND delivery_status != 'Fully Delivered'
        AND docstatus = 1
    """, today, as_dict=True)

    for order in overdue_orders:
        existing = frappe.db.exists("Marketplace Alert", {
            "sales_order": order.name,
            "alert_type": "Late Shipment",
            "status": ["in", ["Open", "Snoozed"]],
        })
        if not existing:
            alert = frappe.new_doc("Marketplace Alert")
            alert.alert_type = "Late Shipment"
            alert.severity = "fire"
            alert.sales_order = order.name
            alert.title = f"Late shipment risk — {order.name}"
            alert.description = f"Order {order.name} for {order.customer} must ship today."
            alert.status = "Open"
            alert.flags.ignore_mandatory = True
            alert.insert(ignore_permissions=True)
    frappe.db.commit()
