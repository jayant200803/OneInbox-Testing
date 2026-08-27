# Order Status API

Base URL (deployed): **`https://oneinbox-testing.onrender.com`**
Import spec directly from: **`https://oneinbox-testing.onrender.com/openapi.json`**
Interactive docs: **`https://oneinbox-testing.onrender.com/docs`**

Look up an order's status by its order number. All order endpoints require a
**Bearer token** in the `Authorization` header.

---

## Authentication

Every request to an `/orders` endpoint must include this header:

```
Authorization: Bearer test-token-123
```

- Default token: **`test-token-123`**
- Missing or wrong token → HTTP `401 Unauthorized`.
- (The token can be changed on the server via the `API_TOKEN` environment variable.)

---

## Endpoints

### 1. Get order status
- **Call:** `GET /orders/{order_number}`
- **Auth:** required (Bearer token)
- **Example:** `GET /orders/1001`
- **Returns:**
  ```json
  {
    "order_number": "1001",
    "status": "shipped",
    "customer_name": "Jayant Raj",
    "item": "Wireless Headphones",
    "estimated_delivery": "2026-09-02"
  }
  ```
- Unknown order → HTTP `404`.

### 2. List all orders
- **Call:** `GET /orders`
- **Auth:** required (Bearer token)
- **Returns:** `{ "orders": [ ... ] }`

### 3. Health check
- **Call:** `GET /health`
- **Auth:** not required
- **Returns:** `{ "status": "ok", "time": "..." }`

---

## Quick test (curl)

```bash
curl -H "Authorization: Bearer test-token-123" \
  https://oneinbox-testing.onrender.com/orders/1001
```

---

## Sample order numbers (demo data)

| Order number | Status |
|---|---|
| `1001` | shipped |
| `1002` | processing |
| `1003` | delivered |
| `1004` | cancelled |

Storage is in-memory (demo) — it resets if the server restarts.
