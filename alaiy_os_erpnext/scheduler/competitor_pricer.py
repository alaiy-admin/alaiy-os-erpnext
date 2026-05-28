import frappe


def update_competitor_prices():
    """Hourly: update competitor prices via Amazon SP API getCompetitivePricing."""
    try:
        from alaiy_os_erpnext.amazon.sp_api import get_sp_client
        sp = get_sp_client()

        competitors = frappe.get_all(
            "Competitor Listing",
            filters={"marketplace": "amazon_in"},
            fields=["name", "channel_sku_id", "item_code"],
        )

        asin_list = [c.channel_sku_id for c in competitors if c.channel_sku_id]
        if not asin_list:
            return

        pricing_data = sp.get_competitive_pricing(asin_list)

        for competitor in competitors:
            if competitor.channel_sku_id in pricing_data:
                price_info = pricing_data[competitor.channel_sku_id]
                frappe.db.set_value("Competitor Listing", competitor.name, {
                    "competitor_price_inr": price_info.get("lowest_price", 0),
                    "last_checked": frappe.utils.now_datetime(),
                })

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Competitor price update failed: {e}", "Competitor Pricer")
