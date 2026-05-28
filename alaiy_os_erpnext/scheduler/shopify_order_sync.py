import frappe


def sync_shopify_orders():
    """Every 5 min: poll Shopify for new orders and create Sales Orders in ERPNext."""
    try:
        from alaiy_os_erpnext.shopify.graphql import ShopifyGraphQL
        shopify = ShopifyGraphQL()

        last_sync = (
            frappe.db.get_single_value("Shopify Settings", "last_sync_datetime")
            or frappe.utils.add_days(frappe.utils.now_datetime(), -1)
        )

        orders = shopify.get_orders(since=last_sync)

        created = 0
        for order in orders:
            shopify_id = order.get("id", "")
            if not frappe.db.exists("Sales Order", {"custom_shopify_order_id": shopify_id}):
                _create_sales_order_from_shopify(order)
                created += 1

        frappe.db.set_single_value(
            "Shopify Settings", "last_sync_datetime", frappe.utils.now_datetime()
        )
        frappe.db.commit()

        if created:
            frappe.logger().info(f"Shopify sync: created {created} Sales Orders")

    except Exception as e:
        frappe.log_error(f"Shopify order sync failed: {e}", "Shopify Order Sync")


def _create_sales_order_from_shopify(order):
    """Create an ERPNext Sales Order from a Shopify GraphQL order dict."""
    customer_name = order.get("customer", {}).get("displayName", "Shopify Customer")

    customer = frappe.db.get_value("Customer", {"customer_name": customer_name})
    if not customer:
        c = frappe.new_doc("Customer")
        c.customer_name = customer_name
        c.customer_group = "Shopify"
        c.territory = "All Territories"
        c.flags.ignore_mandatory = True
        c.insert(ignore_permissions=True)
        customer = c.name

    so = frappe.new_doc("Sales Order")
    so.customer = customer
    so.transaction_date = frappe.utils.today()
    so.delivery_date = frappe.utils.add_days(frappe.utils.today(), 3)
    so.custom_shopify_order_id = order.get("id", "")
    so.custom_channel = "shopify"

    for line in order.get("lineItems", {}).get("nodes", []):
        item_code = line.get("sku") or line.get("title", "UNKNOWN")

        if not frappe.db.exists("Item", item_code):
            item = frappe.new_doc("Item")
            item.item_code = item_code
            item.item_name = line.get("title", item_code)
            item.item_group = "Shopify Items"
            item.is_stock_item = 1
            item.stock_uom = "Nos"
            item.flags.ignore_mandatory = True
            item.insert(ignore_permissions=True)

        so.append("items", {
            "item_code": item_code,
            "qty": float(line.get("quantity", 1)),
            "rate": float(
                line.get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount", 0)
            ),
            "delivery_date": so.delivery_date,
        })

    if so.items:
        so.flags.ignore_mandatory = True
        so.insert(ignore_permissions=True)
        so.submit()
