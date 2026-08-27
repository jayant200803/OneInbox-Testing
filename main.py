"""
Order Status API
================

A small API to create, look up, update, and delete orders.
Protected with a Bearer token (Authorization: Bearer <token>).

Storage is a real database (Postgres in production via DATABASE_URL, or a local
SQLite file when DATABASE_URL is not set), so orders persist across restarts.

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
from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

app = FastAPI(
    title="Order Status API",
    version="1.0.0",
    description=(
        "Create, look up, update, and delete orders. "
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
# Database (persists across restarts)
# ---------------------------------------------------------------------------
def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        # Local / fallback: a SQLite file next to the app.
        return "sqlite:///./orders.db"
    # Render/Heroku give "postgres://..."; SQLAlchemy needs "postgresql://".
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _database_url()
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    customer_name: Mapped[str] = mapped_column(String, default="")
    item: Mapped[str] = mapped_column(String, default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total_amount: Mapped[str] = mapped_column(String, default="0")
    estimated_delivery: Mapped[str] = mapped_column(String, default="N/A")


SEED_ORDERS = [
    {"order_number": "1001", "status": "shipped", "customer_name": "Jayant Raj",
     "item": "Wireless Headphones", "quantity": 1, "total_amount": "7999",
     "estimated_delivery": "2026-09-02"},
    {"order_number": "1002", "status": "processing", "customer_name": "Aisha Khan",
     "item": "Bluetooth Speaker", "quantity": 1, "total_amount": "3499",
     "estimated_delivery": "2026-09-05"},
    {"order_number": "1003", "status": "delivered", "customer_name": "Rohit Mehta",
     "item": "Smart Watch", "quantity": 1, "total_amount": "12999",
     "estimated_delivery": "2026-08-25"},
    {"order_number": "1004", "status": "cancelled", "customer_name": "Sara Lee",
     "item": "Laptop Stand", "quantity": 1, "total_amount": "999",
     "estimated_delivery": "N/A"},
]


@app.on_event("startup")
def _init_db() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        if db.scalar(select(OrderRow).limit(1)) is None:
            db.add_all(OrderRow(**o) for o in SEED_ORDERS)
            db.commit()


def get_db():
    with Session(engine) as db:
        yield db


def _row_to_dict(row: OrderRow) -> dict:
    return {
        "order_number": row.order_number,
        "status": row.status,
        "customer_name": row.customer_name,
        "item": row.item,
        "quantity": row.quantity,
        "total_amount": row.total_amount,
        "estimated_delivery": row.estimated_delivery,
    }


# ---------------------------------------------------------------------------
# Response / request schemas
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
    count: int = 0


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


def _with_message(order: dict) -> dict:
    return {**order, "message": _spoken_message(order)}


# Request-body examples so Swagger UI shows an editable body box for these
# endpoints (needed because we read the raw request instead of a typed model).
_FULL_ORDER_EXAMPLE = {
    "customer_name": "Neha Sharma",
    "item": "Gaming Mouse",
    "quantity": 2,
    "total_amount": "15000",
    "status": "pending",
}
_PARTIAL_ORDER_EXAMPLE = {"status": "delivered", "quantity": 3}


def _body_schema(example: dict) -> dict:
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                    "example": example,
                }
            },
        }
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", summary="Health check", tags=["system"])
def health():
    """Simple check that the API is running. No auth required."""
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/orders", response_model=OrderList,
         summary="List all orders", tags=["orders"])
@app.get("/api/public/orders", response_model=OrderList,
         summary="List all orders", tags=["orders"])
def list_orders(db: Session = Depends(get_db), _: None = Depends(verify_token)):
    """Return ALL orders in one call, each with a ready-to-read message.
    Use this to see everything available and pick one — no need to know a
    specific order number first. Requires a valid Bearer token."""
    rows = db.scalars(select(OrderRow)).all()
    orders = [_with_message(_row_to_dict(r)) for r in rows]
    return {"orders": orders, "count": len(orders)}


@app.get("/orders/{order_number}", response_model=Order,
         summary="Get order status", tags=["orders"])
def get_order_status(
    order_number: str = Path(
        ..., description="The order number the caller provides, e.g. 1001",
        examples=["1001"],
    ),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Return the status (and details) of an order by its order number.
    Requires a valid Bearer token in the Authorization header."""
    row = db.get(OrderRow, order_number.strip())
    if not row:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Sorry, I couldn't find any order with the number {order_number}. "
                "Please double-check the order number."
            ),
        )
    return _with_message(_row_to_dict(row))


@app.post("/api/public/orders", response_model=Order, status_code=201,
          summary="Create a new order", tags=["orders"],
          openapi_extra=_body_schema(_FULL_ORDER_EXAMPLE))
async def create_order(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Create a new order. Use this when the user wants to place or create an order.
    Required fields: customer_name, item, quantity, total_amount.
    Optional: status (default 'pending').
    Requires a valid Bearer token. Returns the created order with its number and status."""
    data = await _read_body(request)
    try:
        new = NewOrder(**data)
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")

    if new.order_number:
        order_number = new.order_number.strip()
    else:
        existing = db.scalars(select(OrderRow.order_number)).all()
        next_num = max((int(n) for n in existing if n.isdigit()), default=1000) + 1
        order_number = str(next_num)

    if db.get(OrderRow, order_number):
        raise HTTPException(status_code=409, detail=f"Order {order_number} already exists.")

    row = OrderRow(
        order_number=order_number, status=new.status,
        customer_name=new.customer_name, item=new.item, quantity=new.quantity,
        total_amount=new.total_amount, estimated_delivery=new.estimated_delivery,
    )
    db.add(row)
    db.commit()
    return _with_message(_row_to_dict(row))


# Fields that may be updated on an order.
UPDATABLE_FIELDS = {
    "status", "customer_name", "item", "quantity",
    "total_amount", "estimated_delivery",
}


@app.patch("/api/public/orders/{order_number}", response_model=Order,
           summary="Update part of an order", tags=["orders"],
           openapi_extra=_body_schema(_PARTIAL_ORDER_EXAMPLE))
async def update_order(
    request: Request,
    order_number: str = Path(..., examples=["1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Update one or more fields of an existing order (status, item, quantity, etc.).
    Only the fields you send are changed. Requires a valid Bearer token."""
    row = db.get(OrderRow, order_number.strip())
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    data = await _read_body(request)
    for key, value in data.items():
        if key in UPDATABLE_FIELDS:
            if key == "quantity":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            setattr(row, key, value)
    db.commit()
    return _with_message(_row_to_dict(row))


@app.put("/api/public/orders/{order_number}", response_model=Order,
         summary="Replace an entire order", tags=["orders"],
         openapi_extra=_body_schema(_FULL_ORDER_EXAMPLE))
async def replace_order(
    request: Request,
    order_number: str = Path(..., examples=["1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Replace the whole order with the fields you send.
    Required fields: customer_name, item, quantity, total_amount.
    Requires a valid Bearer token."""
    row = db.get(OrderRow, order_number.strip())
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    data = await _read_body(request)
    try:
        new = NewOrder(**data)
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")
    row.status = new.status
    row.customer_name = new.customer_name
    row.item = new.item
    row.quantity = new.quantity
    row.total_amount = new.total_amount
    row.estimated_delivery = new.estimated_delivery
    db.commit()
    return _with_message(_row_to_dict(row))


@app.delete("/api/public/orders/{order_number}",
            summary="Delete an order", tags=["orders"])
def delete_order(
    order_number: str = Path(..., examples=["1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Remove an order by its order number. Requires a valid Bearer token."""
    row = db.get(OrderRow, order_number.strip())
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    db.delete(row)
    db.commit()
    return {
        "order_number": order_number.strip(),
        "message": f"Order {order_number.strip()} has been deleted.",
    }
