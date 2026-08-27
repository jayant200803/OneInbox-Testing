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

import json
import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Path, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ValidationError

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
    quantity: int = 1
    total_amount: str = "0"
    estimated_delivery: str = "N/A"
    message: str


class OrderList(BaseModel):
    orders: list[Order]


class NewOrder(BaseModel):
    """Fields the caller provides to create a new order."""
    customer_name: str = Field(..., examples=["Jayant Raj"])
    item: str = Field(..., examples=["Wireless Headphones"])
    quantity: int = Field(..., examples=[1])
    total_amount: str = Field(..., examples=["15000"])
    status: str = Field("pending", examples=["pending"],
                        description="Order status. Defaults to 'pending'.")
    estimated_delivery: str = Field("N/A", examples=["2026-09-10"])
    order_number: Optional[str] = Field(
        None, description="Optional. If omitted, the next number is assigned.",
        examples=["1005"])


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


async def _read_body(request: Request) -> dict:
    """Read the JSON body, tolerating clients that send it as a quoted string
    (double-encoded) and total_amount as a number or a string."""
    raw = await request.body()
    try:
        data = json.loads(raw or b"{}")
        if isinstance(data, str):
            data = json.loads(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON body: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")
    if "total_amount" in data:
        data["total_amount"] = str(data["total_amount"])
    return data


@app.post("/api/public/orders", response_model=Order, status_code=201,
          summary="Create a new order", tags=["orders"])
async def create_order(request: Request, _: None = Depends(verify_token)):
    """Create a new order. Use this when the user wants to place or create an order.
    Required fields: customer_name, item, quantity, total_amount.
    Optional: status (default 'pending').
    Requires a valid Bearer token. Returns the created order with its number and status."""
    data = await _read_body(request)
    try:
        new = NewOrder(**data)
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")
    # Assign an order number if one wasn't provided.
    if new.order_number:
        order_number = new.order_number.strip()
    else:
        next_num = max((int(n) for n in ORDERS if n.isdigit()), default=1000) + 1
        order_number = str(next_num)

    if order_number in ORDERS:
        raise HTTPException(
            status_code=409,
            detail=f"Order {order_number} already exists.",
        )

    order = {
        "order_number": order_number,
        "status": new.status,
        "customer_name": new.customer_name,
        "item": new.item,
        "quantity": new.quantity,
        "total_amount": new.total_amount,
        "estimated_delivery": new.estimated_delivery,
    }
    ORDERS[order_number] = order
    return {**order, "message": _spoken_message(order)}


# Fields that may be updated on an order.
UPDATABLE_FIELDS = {
    "status", "customer_name", "item", "quantity",
    "total_amount", "estimated_delivery",
}


@app.patch("/api/public/orders/{order_number}", response_model=Order,
           summary="Update part of an order", tags=["orders"])
async def update_order(
    request: Request,
    order_number: str = Path(..., examples=["1001"]),
    _: None = Depends(verify_token),
):
    """Update one or more fields of an existing order (status, item, quantity, etc.).
    Only the fields you send are changed. Requires a valid Bearer token."""
    order = ORDERS.get(order_number.strip())
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    data = await _read_body(request)
    for key, value in data.items():
        if key in UPDATABLE_FIELDS:
            order[key] = value
    return {**order, "message": _spoken_message(order)}


@app.put("/api/public/orders/{order_number}", response_model=Order,
         summary="Replace an entire order", tags=["orders"])
async def replace_order(
    request: Request,
    order_number: str = Path(..., examples=["1001"]),
    _: None = Depends(verify_token),
):
    """Replace the whole order with the fields you send.
    Required fields: customer_name, item, quantity, total_amount.
    Requires a valid Bearer token."""
    if order_number.strip() not in ORDERS:
        raise HTTPException(status_code=404, detail="Order not found")
    data = await _read_body(request)
    try:
        new = NewOrder(**data)
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")
    order = {
        "order_number": order_number.strip(),
        "status": new.status,
        "customer_name": new.customer_name,
        "item": new.item,
        "quantity": new.quantity,
        "total_amount": new.total_amount,
        "estimated_delivery": new.estimated_delivery,
    }
    ORDERS[order_number.strip()] = order
    return {**order, "message": _spoken_message(order)}


@app.delete("/api/public/orders/{order_number}",
            summary="Delete an order", tags=["orders"])
def delete_order(
    order_number: str = Path(..., examples=["1001"]),
    _: None = Depends(verify_token),
):
    """Remove an order by its order number. Requires a valid Bearer token."""
    order = ORDERS.pop(order_number.strip(), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_number": order_number.strip(),
        "message": f"Order {order_number.strip()} has been deleted.",
    }
