# Order Status API

A small FastAPI service to look up an order's status by its order number,
protected with a **Bearer token**.

---

## Authentication

All `/orders` endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer test-token-123
```

The token is read from the `API_TOKEN` environment variable (default
`test-token-123` if unset). Missing/wrong token returns HTTP 401.

---

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

- Interactive docs: http://localhost:8000/docs
- OpenAPI spec: http://localhost:8000/openapi.json

---

## Endpoints

| Method | Path | Auth | What it does |
|---|---|---|---|
| GET | `/orders/{order_number}` | Bearer | Get an order's status |
| GET | `/orders` | Bearer | List all orders |
| GET | `/health` | none | Health check |

Sample order numbers: `1001`, `1002`, `1003`, `1004`.

---

## Quick test

```bash
curl -H "Authorization: Bearer test-token-123" \
  http://localhost:8000/orders/1001
```

---

## Deploy (Render)

This repo includes `render.yaml`, `Procfile`, and `.python-version`.

1. Push to GitHub.
2. render.com → New → Web Service → connect the repo.
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

To change the token in production, set an `API_TOKEN` environment variable in
the Render dashboard.

Storage is in-memory (demo) — it resets on restart.
