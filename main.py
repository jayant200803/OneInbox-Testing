"""
Order Status API
================

A small, self-contained API to look up an order's status by its order number.
Protected with a Bearer token (Authorization: Bearer <token>).

Run locally:   uvicorn main:app --reload
Docs (try it): http://localhost:8000/docs
OpenAPI spec:  http://localhost:8000/openapi.json

Auth:
  Send header ->  Authorization: Bearer <API_TOKEN>
  The token is read from the API_TOKEN environment variable.
  If unset, it defaults to "test-token-123" for easy testing.
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

app = FastAPI(
    title="Order Status API",
    version="1.0.0",
    description=(
        "Look up an order's status by its order number. "
        "All order endpoints require a Bearer token in the Authorization header."
    ),
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---------------------------------------------------------------------------
# Auth (Bearer token)
# ---------------------------------------------------------------------------
API_TOKEN = os.environ.get("API_TOKEN", "test-token-123")
bearer_scheme = HTTPBearer(auto_error=False)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    """Validate the Bearer token sent in the Authorization header."""
    if credentials is None or credentials.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# In-memory "database" of orders (demo — resets on restart)
# ---------------------------------------------------------------------------
ORDERS: dict[str, dict] = {
    "1001": {
        "order_number": "1001",
        "status": "shipped",
        "customer_name": "Jayant Raj",
        "item": "Wireless Headphones",
        "estimated_delivery": "2026-09-02",
    },
    "1002": {
        "order_number": "1002",
        "status": "processing",
        "customer_name": "Aisha Khan",
        "item": "Bluetooth Speaker",
        "estimated_delivery": "2026-09-05",
    },
    "1003": {
        "order_number": "1003",
        "status": "delivered",
        "customer_name": "Rohit Mehta",
        "item": "Smart Watch",
        "estimated_delivery": "2026-08-25",
    },
    "1004": {
        "order_number": "1004",
        "status": "cancelled",
        "customer_name": "Sara Lee",
        "item": "Laptop Stand",
        "estimated_delivery": "N/A",
    },
}


# ---------------------------------------------------------------------------
# Response schema (so the agent platform reliably sees every field)
# ---------------------------------------------------------------------------
class Order(BaseModel):
    order_number: str
    status: str
    customer_name: str
    item: str
    estimated_delivery: str
    message: str


class OrderList(BaseModel):
    orders: list[Order]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", summary="Health check", tags=["system"])
def health():
    """Simple check that the API is running. No auth required."""
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/orders/{order_number}", response_model=Order,
         summary="Get order status", tags=["orders"])
def get_order_status(
    order_number: str = Path(
        ...,
        description="The order number the caller provides, e.g. 1001",
        examples=["1001"],
    ),
    _: None = Depends(verify_token),
):
    """Return the status (and details) of an order by its order number.
    Requires a valid Bearer token in the Authorization header."""
    order = ORDERS.get(order_number.strip())
    if not order:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Sorry, I couldn't find any order with the number {order_number}. "
                "Please double-check the order number."
            ),
        )
    return {**order, "message": _spoken_message(order)}


def _spoken_message(order: dict) -> str:
    """Build a natural, ready-to-read-aloud sentence for the voice agent."""
    num = order["order_number"]
    status = order["status"]
    item = order["item"]
    eta = order["estimated_delivery"]
    if status == "shipped":
        return (
            f"Your order {num} for the {item} has shipped "
            f"and is expected to arrive by {eta}."
        )
    if status == "processing":
        return (
            f"Your order {num} for the {item} is currently being processed "
            f"and is expected to arrive by {eta}."
        )
    if status == "delivered":
        return f"Your order {num} for the {item} was delivered on {eta}."
    if status == "cancelled":
        return f"Your order {num} for the {item} has been cancelled."
    return f"Your order {num} for the {item} is currently {status}."


@app.get("/orders", response_model=OrderList,
         summary="List all orders", tags=["orders"])
def list_orders(_: None = Depends(verify_token)):
    """Return ALL orders in one call, each with a ready-to-read message.
    The voice agent fetches this once and reads back whichever order the
    caller asks about. Requires a valid Bearer token."""
    return {
        "orders": [
            {**order, "message": _spoken_message(order)}
            for order in ORDERS.values()
        ]
    }
