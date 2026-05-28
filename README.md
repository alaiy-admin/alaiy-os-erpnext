# alaiy-os-erpnext

**alaiy OS** custom Frappe/ERPNext v15 app — ecommerce operations dashboard backend.

Provides Amazon SP API + Shopify GraphQL connectors, 4 custom DocTypes, a scheduler-driven alert/feed engine, and whitelisted REST endpoints consumed by the `alaiy-os-selfserve-prototype.html` frontend.

---

## What this app does

| Capability | Detail |
|---|---|
| **Marketplace Alert feed** | Severity-ranked (fire / warn / info) ops alerts surfaced to the frontend |
| **Amazon SP API** | Read orders, account health, competitive pricing; write repricing, inventory, shipment confirmation |
| **Shopify GraphQL** | Read orders; write fulfilment, repricing, inventory, returns, products |
| **Shopify webhooks** | Inbound `orders/create`, `fulfillments/create`, cancellations, refunds to ERPNext documents |
| **Scheduler jobs** | Alert generation (15 min), competitor repricing (hourly), Amazon health poll (daily), Shopify sync (every 5 min) |
| **REST API** | `frappe.whitelist()` methods consumed by the HTML frontend over `http://localhost:8000` |

---

## Prerequisites

- ERPNext v15 (Frappe v15) bench
- Python 3.11+
- `ecommerce_integrations` app installed (for `Ecommerce Item` DocType)
- Amazon Seller Central SP API application (OAuth + IAM role)
- Shopify Partner app with `Admin API` scopes

---

## Local development setup

```bash
# 1. Get into the bench directory
cd ~/frappe-bench

# 2. Download the app
bench get-app https://github.com/alaiy-admin/alaiy-os-erpnext

# 3. Install on your site
bench --site your-site.localhost install-app alaiy_os_erpnext

# 4. Run migrations (creates the 4 DocTypes)
bench --site your-site.localhost migrate

# 5. Start in dev mode
bench start
```

---

## Configuration

### Amazon SP API

1. In ERPNext, open **Amazon SP API Settings** (Single DocType).
2. Fill in:
   - `client_id` / `client_secret` — LWA credentials from Seller Central
   - `refresh_token` — from OAuth flow
   - `aws_access_key` / `aws_secret_key` — IAM user with SP API role assumption
   - `iam_arn` — ARN of the IAM role
   - `seller_id` — your Amazon Seller ID
3. Save.

### Shopify

1. Open **Shopify Settings** (Frappe single DocType).
2. Fill in:
   - `shopify_url` — your `.myshopify.com` domain
   - `password` — Private App access token (or Custom App API token)
   - `shared_secret` — for webhook HMAC validation
3. Register the webhook endpoint in Shopify Partner dashboard:
   - URL: `https://your-erpnext-site/api/alaiy_os/shopify_webhook`
   - Topics: `orders/create`, `orders/paid`, `orders/cancelled`, `fulfillments/create`, `fulfillments/update`, `refunds/create`

---

## Architecture

### Custom DocTypes

| DocType | Purpose |
|---|---|
| `Marketplace Alert` | Central feed of ops issues (stock, health, shipment, buybox) |
| `Account Health Snapshot` | Daily snapshot of Amazon seller account health metrics |
| `Reorder Policy` | Per-SKU/warehouse reorder points and supplier config |
| `Competitor Listing` | Tracked competitor prices per ASIN/marketplace |

### Connectors

```
alaiy_os_erpnext/
├── amazon/sp_api.py     AlaiyAmazonSP — wraps python-amazon-sp-api
└── shopify/graphql.py   ShopifyGraphQL — raw GQL over requests, cost-throttle backoff
```

### Scheduler jobs

| Frequency | Job | What it does |
|---|---|---|
| Every 5 min | `shopify_order_sync` | Poll Shopify for new orders to Sales Orders |
| Every 15 min | `alert_generator` | Check reorder points + overdue shipments to Marketplace Alerts |
| Hourly | `competitor_pricer` | Refresh Amazon competitive pricing on tracked ASINs |
| Daily | `health_poller` | Pull Amazon account health to Account Health Snapshot |

### API endpoints (whitelisted)

All callable from the frontend via:
```
GET /api/method/alaiy_os_erpnext.api.<method_name>
```

| Method | Description |
|---|---|
| `get_feed_items` | Open/snoozed alerts for the feed panel |
| `get_kpi_summary` | Header strip KPIs (orders, revenue, stock, health) |
| `get_inventory_with_velocity` | Inventory table with 14-day velocity and status |
| `snooze_alert` | Snooze an alert for N hours |
| `approve_reorder` | Create draft Purchase Order |
| `mark_dispatched` | Submit Delivery Note with AWB |
| `amazon_reprice` | Patch Amazon listing price |
| `amazon_get_account_health` | Live Amazon health check |
| `shopify_fulfill_order` | GraphQL fulfillmentCreate |
| `shopify_reprice` | Update Shopify variant price |
| `shopify_update_inventory` | Set Shopify inventory quantity |
| `get_account_health_latest` | Latest snapshot per marketplace |

---

## Frontend connection

The `alaiy-os-selfserve-prototype.html` file makes authenticated fetch() calls:

```javascript
// Example: fetch the alert feed
const response = await fetch(
  "http://localhost:8000/api/method/alaiy_os_erpnext.api.get_feed_items",
  {
    credentials: "include",   // sends Frappe session cookie
    headers: { "X-Frappe-CSRF-Token": getCsrfToken() }
  }
);
const data = await response.json();
```

Log in to ERPNext at `http://localhost:8000` first so the session cookie is set, then open the HTML file in the same browser.

---

## License

MIT
