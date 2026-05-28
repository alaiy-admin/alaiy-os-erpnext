"""
Amazon SP API wrapper for alaiy OS ERPNext.
Uses python-amazon-sp-api (pip install python-amazon-sp-api).
Credentials are read from the "Amazon SP API Settings" Single DocType.
"""
import frappe
import json
from datetime import datetime, timedelta


def get_sp_client():
    """Instantiate AlaiyAmazonSP from ERPNext settings."""
    settings = frappe.get_single("Amazon SP API Settings")
    return AlaiyAmazonSP(
        refresh_token=settings.refresh_token,
        lwa_client_id=settings.client_id,
        lwa_client_secret=settings.client_secret,
        aws_access_key=settings.aws_access_key,
        aws_secret_key=settings.aws_secret_key,
        role_arn=settings.iam_arn,
    )


class AlaiyAmazonSP:
    """
    Thin wrapper around python-amazon-sp-api that exposes only the operations
    alaiy OS needs. Each method returns plain Python dicts/lists suitable for
    JSON serialisation and storage in Frappe.
    """

    def __init__(self, refresh_token, lwa_client_id, lwa_client_secret,
                 aws_access_key, aws_secret_key, role_arn):
        self.credentials = {
            "refresh_token": refresh_token,
            "lwa_app_id": lwa_client_id,
            "lwa_client_secret": lwa_client_secret,
            "aws_access_key": aws_access_key,
            "aws_secret_key": aws_secret_key,
            "role_arn": role_arn,
        }

    def _orders_api(self):
        from sp_api.api import Orders
        from sp_api.base import Marketplaces
        return Orders(credentials=self.credentials, marketplace=Marketplaces.IN)

    def _catalog_api(self):
        from sp_api.api import CatalogItems
        from sp_api.base import Marketplaces
        return CatalogItems(credentials=self.credentials, marketplace=Marketplaces.IN)

    def _listings_api(self):
        from sp_api.api import ListingsItems
        from sp_api.base import Marketplaces
        return ListingsItems(credentials=self.credentials, marketplace=Marketplaces.IN)

    def _product_pricing_api(self):
        from sp_api.api import ProductPricing
        from sp_api.base import Marketplaces
        return ProductPricing(credentials=self.credentials, marketplace=Marketplaces.IN)

    def _feeds_api(self):
        from sp_api.api import Feeds
        from sp_api.base import Marketplaces
        return Feeds(credentials=self.credentials, marketplace=Marketplaces.IN)

    # ── Orders ────────────────────────────────────────────────────────────────

    def get_orders(self, days_ago=1, marketplace_id="A21TJRUUN4KGV"):
        """Return list of order dicts created in the last `days_ago` days."""
        created_after = (datetime.utcnow() - timedelta(days=days_ago)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        api = self._orders_api()
        response = api.get_orders(
            CreatedAfter=created_after,
            MarketplaceIds=[marketplace_id],
        )
        orders = response.payload.get("Orders", [])
        result = []
        for o in orders:
            result.append({
                "amazon_order_id": o.get("AmazonOrderId"),
                "purchase_date": o.get("PurchaseDate"),
                "status": o.get("OrderStatus"),
                "fulfillment_channel": o.get("FulfillmentChannel"),
                "buyer_email": o.get("BuyerInfo", {}).get("BuyerEmail", ""),
                "order_total": o.get("OrderTotal", {}).get("Amount", 0),
                "currency": o.get("OrderTotal", {}).get("CurrencyCode", "INR"),
                "number_of_items": o.get("NumberOfItemsShipped", 0) + o.get("NumberOfItemsUnshipped", 0),
                "ship_service_level": o.get("ShipServiceLevel", ""),
            })
        return result

    def get_order_items(self, amazon_order_id):
        """Return list of item dicts for a given Amazon order ID."""
        api = self._orders_api()
        response = api.get_order_items(orderId=amazon_order_id)
        items = response.payload.get("OrderItems", [])
        return [
            {
                "asin": i.get("ASIN"),
                "seller_sku": i.get("SellerSKU"),
                "title": i.get("Title"),
                "qty_ordered": i.get("QuantityOrdered", 0),
                "qty_shipped": i.get("QuantityShipped", 0),
                "item_price": i.get("ItemPrice", {}).get("Amount", 0),
                "currency": i.get("ItemPrice", {}).get("CurrencyCode", "INR"),
            }
            for i in items
        ]

    # ── Account Health ────────────────────────────────────────────────────────

    def get_account_health(self, marketplace_id="A21TJRUUN4KGV"):
        """
        Return account health metrics dict.
        Keys: odr, late_shipment_rate, cancel_rate, valid_tracking_rate, a_to_z_claims
        """
        try:
            from sp_api.api import Sellers
            api = Sellers(credentials=self.credentials)
            response = api.get_account_health()
            payload = response.payload or {}
            metrics_list = payload.get("accountHealthRating", {}).get("metrics", [])
            metrics = {}
            for m in metrics_list:
                name = m.get("name", "")
                value = m.get("value", 0)
                if "defect" in name.lower():
                    metrics["odr"] = float(value)
                elif "late" in name.lower():
                    metrics["late_shipment_rate"] = float(value)
                elif "cancel" in name.lower():
                    metrics["cancel_rate"] = float(value)
                elif "tracking" in name.lower():
                    metrics["valid_tracking_rate"] = float(value)
                elif "claim" in name.lower():
                    metrics["a_to_z_claims"] = int(value)
            return {"metrics": metrics, "raw": payload}
        except Exception as e:
            frappe.log_error(f"SP API account health error: {e}", "SP API")
            return {"metrics": {}, "error": str(e)}

    # ── Competitive Pricing ───────────────────────────────────────────────────

    def get_competitive_pricing(self, asin_list, marketplace_id="A21TJRUUN4KGV"):
        """Return dict of ASIN -> {lowest_price, buybox_price}."""
        api = self._product_pricing_api()
        result = {}
        for i in range(0, len(asin_list), 20):
            batch = asin_list[i:i + 20]
            try:
                response = api.get_competitive_pricing_for_asins(
                    MarketplaceId=marketplace_id, Asins=batch
                )
                for item in response.payload:
                    asin = item.get("ASIN")
                    pricing = item.get("Product", {}).get("CompetitivePricing", {})
                    prices = pricing.get("CompetitivePrices", [])
                    lowest = None
                    buybox = None
                    for p in prices:
                        amount = p.get("Price", {}).get("ListingPrice", {}).get("Amount", 0)
                        if p.get("condition") == "New":
                            if lowest is None or amount < lowest:
                                lowest = amount
                        if p.get("belongsToRequester"):
                            buybox = amount
                    result[asin] = {
                        "lowest_price": lowest or 0,
                        "buybox_price": buybox or 0,
                    }
            except Exception as e:
                frappe.log_error(f"Competitive pricing error for batch {batch}: {e}", "SP API")
        return result

    # ── Listings / Repricing ──────────────────────────────────────────────────

    def reprice_listing(self, sku, price, marketplace_id="A21TJRUUN4KGV"):
        """Patch a listings item price via patchListingsItem."""
        api = self._listings_api()
        seller_id = frappe.db.get_single_value("Amazon SP API Settings", "seller_id") or ""
        patches = [
            {
                "op": "replace",
                "path": "/attributes/purchasable_offer",
                "value": [
                    {
                        "marketplace_id": marketplace_id,
                        "currency": "INR",
                        "our_price": [{"schedule": [{"value_with_tax": price}]}],
                    }
                ],
            }
        ]
        try:
            response = api.patch_listings_item(
                sellerId=seller_id,
                sku=sku,
                marketplaceIds=[marketplace_id],
                body={"productType": "PRODUCT", "patches": patches},
            )
            return {"status": response.payload.get("status"), "sku": sku, "price": price}
        except Exception as e:
            frappe.log_error(f"Reprice error for SKU {sku}: {e}", "SP API")
            return {"error": str(e), "sku": sku}

    def get_listings_item(self, sku, marketplace_id="A21TJRUUN4KGV"):
        """Get full listing details for a SKU."""
        api = self._listings_api()
        seller_id = frappe.db.get_single_value("Amazon SP API Settings", "seller_id") or ""
        try:
            response = api.get_listings_item(
                sellerId=seller_id,
                sku=sku,
                marketplaceIds=[marketplace_id],
                includedData=["summaries", "attributes", "issues", "offers"],
            )
            return response.payload
        except Exception as e:
            frappe.log_error(f"Get listing error for SKU {sku}: {e}", "SP API")
            return {"error": str(e)}

    def create_or_update_listing(self, sku, product_data, marketplace_id="A21TJRUUN4KGV"):
        """Create or update a listing via putListingsItem."""
        api = self._listings_api()
        seller_id = frappe.db.get_single_value("Amazon SP API Settings", "seller_id") or ""
        try:
            response = api.put_listings_item(
                sellerId=seller_id,
                sku=sku,
                marketplaceIds=[marketplace_id],
                body=product_data,
            )
            return response.payload
        except Exception as e:
            frappe.log_error(f"Create/update listing error for SKU {sku}: {e}", "SP API")
            return {"error": str(e)}

    # ── Inventory ─────────────────────────────────────────────────────────────

    def update_inventory_quantity(self, sku, qty, marketplace_id="A21TJRUUN4KGV"):
        """Update FBA inventory quantity via Feeds API (inventory feed)."""
        api = self._feeds_api()
        feed_content = "sku\tquantity\n" + f"{sku}\t{int(qty)}\n"
        try:
            doc_response = api.create_feed_document(contentType="text/tab-separated-values;charset=UTF-8")
            doc = doc_response.payload
            feed_doc_id = doc["feedDocumentId"]
            upload_url = doc["url"]

            import requests
            requests.put(
                upload_url,
                data=feed_content.encode("utf-8"),
                headers={"Content-Type": "text/tab-separated-values;charset=UTF-8"},
            )

            feed_response = api.create_feed(
                body={
                    "feedType": "POST_INVENTORY_AVAILABILITY_DATA",
                    "marketplaceIds": [marketplace_id],
                    "inputFeedDocumentId": feed_doc_id,
                }
            )
            return {"feed_id": feed_response.payload.get("feedId"), "sku": sku, "qty": qty}
        except Exception as e:
            frappe.log_error(f"Inventory update error for SKU {sku}: {e}", "SP API")
            return {"error": str(e)}

    # ── Shipment Confirmation ─────────────────────────────────────────────────

    def confirm_shipment(self, amazon_order_id, carrier, tracking_number, ship_date=None):
        """Confirm shipment for an MFN order."""
        if ship_date is None:
            ship_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        api = self._orders_api()
        try:
            payload = {
                "packageDetail": {
                    "packageReferenceId": "1",
                    "carrierCode": carrier,
                    "trackingNumber": tracking_number,
                    "shipDate": ship_date,
                    "orderItems": [],
                }
            }
            response = api.confirm_shipment(orderId=amazon_order_id, payload=payload)
            return {"status": "confirmed", "amazon_order_id": amazon_order_id, "awb": tracking_number}
        except Exception as e:
            frappe.log_error(f"Confirm shipment error for {amazon_order_id}: {e}", "SP API")
            return {"error": str(e)}
