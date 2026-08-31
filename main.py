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
from fastapi.responses import HTMLResponse
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


# Load the standalone dashboard page (served read-only at /dashboard).
try:
    with open(os.path.join(os.path.dirname(__file__), "dashboard.html"),
              encoding="utf-8") as _f:
        _DASHBOARD_HTML = _f.read()
except OSError:
    _DASHBOARD_HTML = "<h1>Dashboard file not found.</h1>"


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    """A live, auto-refreshing dashboard of all orders. Read-only: it just polls
    the existing /api/public/orders endpoint, so it never changes any data."""
    return _DASHBOARD_HTML


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
        if key not in UPDATABLE_FIELDS:
            continue
        # Ignore blank / unreplaced-placeholder values so a partial update never
        # wipes existing data (e.g. agent sends empty {{item}} while changing status).
        if value is None:
            continue
        if isinstance(value, str):
            v = value.strip()
            if v == "" or (v.startswith("{{") and v.endswith("}}")):
                continue
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


# ===========================================================================
# FRESH API: Support Tickets  (added alongside orders — nothing above changes)
# ===========================================================================
# Richer parameters / validation for testing:
#   category : enum (billing | technical | general | complaint)
#   priority : enum (low | medium | high | urgent)
#   status   : enum (open | in_progress | resolved | closed)
#   email    : must contain "@"
#   subject  : 3..120 chars
TICKET_CATEGORIES = {"billing", "technical", "general", "complaint"}
TICKET_PRIORITIES = {"low", "medium", "high", "urgent"}
TICKET_STATUSES = {"open", "in_progress", "resolved", "closed"}


class TicketRow(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_name: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, default="general")
    priority: Mapped[str] = mapped_column(String, default="medium")
    subject: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="open")


SEED_TICKETS = [
    {"ticket_id": "TKT-1001", "customer_name": "Jayant Raj", "email": "jayant@example.com",
     "category": "technical", "priority": "high", "subject": "App keeps crashing",
     "description": "The app crashes on login.", "status": "open"},
    {"ticket_id": "TKT-1002", "customer_name": "Aisha Khan", "email": "aisha@example.com",
     "category": "billing", "priority": "urgent", "subject": "Double charged",
     "description": "I was charged twice this month.", "status": "in_progress"},
    {"ticket_id": "TKT-1003", "customer_name": "Rohit Mehta", "email": "rohit@example.com",
     "category": "general", "priority": "low", "subject": "How to change email",
     "description": "Need help updating my email address.", "status": "resolved"},
]


@app.on_event("startup")
def _init_tickets() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        if db.scalar(select(TicketRow).limit(1)) is None:
            db.add_all(TicketRow(**t) for t in SEED_TICKETS)
            db.commit()


def _ticket_to_dict(row: TicketRow) -> dict:
    return {
        "ticket_id": row.ticket_id,
        "customer_name": row.customer_name,
        "email": row.email,
        "category": row.category,
        "priority": row.priority,
        "subject": row.subject,
        "description": row.description,
        "status": row.status,
    }


class Ticket(BaseModel):
    ticket_id: str
    customer_name: str
    email: str
    category: str
    priority: str
    subject: str
    description: str = ""
    status: str
    message: str


class TicketList(BaseModel):
    tickets: list[Ticket]
    count: int = 0


class NewTicket(BaseModel):
    customer_name: str = Field("Caller", examples=["Jayant Raj"])
    email: str = Field("not-provided@example.com", examples=["jayant@example.com"])
    category: str = Field("general", examples=["technical"],
                          description="One of: billing, technical, general, complaint")
    priority: str = Field("medium", examples=["high"],
                          description="One of: low, medium, high, urgent")
    subject: str = Field(..., min_length=1, max_length=200,
                         examples=["App keeps crashing"])
    description: str = Field("", examples=["The app crashes on login."])
    status: str = Field("open", examples=["open"],
                        description="One of: open, in_progress, resolved, closed")
    ticket_id: Optional[str] = Field(
        None, description="Optional. If omitted, the next id is assigned.",
        examples=["TKT-1004"])


def _validate_ticket_enums(data: dict) -> None:
    """Be forgiving: map anything the agent says to a valid value instead of
    rejecting, so natural speech ('non-technical', empty priority, no email)
    never fails the call. Only truly needs a subject."""
    if "category" in data and str(data["category"]).lower() not in TICKET_CATEGORIES:
        c = str(data["category"]).lower()
        if c.startswith("non") or "general" in c or "question" in c:
            data["category"] = "general"
        elif "bill" in c or "charge" in c or "refund" in c or "payment" in c:
            data["category"] = "billing"
        elif "tech" in c or "bug" in c or "error" in c or "login" in c:
            data["category"] = "technical"
        elif "complain" in c or "rude" in c:
            data["category"] = "complaint"
        else:
            data["category"] = "general"
    if "priority" in data and str(data["priority"]).lower() not in TICKET_PRIORITIES:
        data["priority"] = "medium"
    if "status" in data and str(data["status"]).lower() not in TICKET_STATUSES:
        data["status"] = "open"
    if "email" in data and "@" not in str(data.get("email", "")):
        # Missing / spoken-wrong email -> store a placeholder instead of failing.
        data["email"] = "not-provided@example.com"


def _norm_ticket_id(tid: str) -> str:
    """Normalise spoken/typed ticket ids so 'tkt 1001', 'TKT1001', '1001'
    all resolve to 'TKT-1001'."""
    t = str(tid).strip().upper().replace(" ", "").replace("_", "-")
    if t.isdigit():
        return "TKT-" + t
    if t.startswith("TKT") and not t.startswith("TKT-"):
        t = "TKT-" + t[3:]
    return t


def _ticket_message(t: dict) -> str:
    return (f"Ticket {t['ticket_id']} ({t['priority']} priority, {t['category']}) "
            f"for {t['customer_name']} is currently {t['status']}: {t['subject']}.")


def _ticket_with_message(t: dict) -> dict:
    return {**t, "message": _ticket_message(t)}


_TICKET_FULL_EXAMPLE = {
    "customer_name": "Neha Sharma", "email": "neha@example.com",
    "category": "billing", "priority": "high",
    "subject": "Refund not received", "description": "Refund pending 10 days.",
    "status": "open",
}
_TICKET_PARTIAL_EXAMPLE = {"status": "resolved", "priority": "low"}


@app.get("/tickets/{ticket_id}", response_model=Ticket,
         summary="Get a support ticket", tags=["tickets"])
def get_ticket(
    ticket_id: str = Path(..., examples=["TKT-1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Return a single ticket by its ID. Requires a valid Bearer token."""
    row = db.get(TicketRow, _norm_ticket_id(ticket_id))
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_with_message(_ticket_to_dict(row))


@app.get("/api/public/tickets", response_model=TicketList,
         summary="List all support tickets", tags=["tickets"])
def list_tickets(db: Session = Depends(get_db), _: None = Depends(verify_token)):
    """Return ALL tickets. Requires a valid Bearer token."""
    rows = db.scalars(select(TicketRow)).all()
    tickets = [_ticket_with_message(_ticket_to_dict(r)) for r in rows]
    return {"tickets": tickets, "count": len(tickets)}


@app.post("/api/public/tickets", response_model=Ticket, status_code=201,
          summary="Create a support ticket", tags=["tickets"],
          openapi_extra=_body_schema(_TICKET_FULL_EXAMPLE))
async def create_ticket(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Create a support ticket. Required: customer_name, email, category, subject.
    Optional: priority (default medium), description, status (default open)."""
    data = await _read_body(request)
    _validate_ticket_enums(data)
    try:
        new = NewTicket(**data)
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")

    if new.ticket_id:
        ticket_id = new.ticket_id.strip()
    else:
        existing = db.scalars(select(TicketRow.ticket_id)).all()
        nums = [int(t.split("-")[-1]) for t in existing if t.split("-")[-1].isdigit()]
        ticket_id = "TKT-" + str((max(nums) if nums else 1000) + 1)

    if db.get(TicketRow, ticket_id):
        raise HTTPException(status_code=409, detail=f"Ticket {ticket_id} already exists.")

    row = TicketRow(
        ticket_id=ticket_id, customer_name=new.customer_name, email=new.email,
        category=new.category, priority=new.priority, subject=new.subject,
        description=new.description, status=new.status,
    )
    db.add(row)
    db.commit()
    return _ticket_with_message(_ticket_to_dict(row))


TICKET_UPDATABLE = {"customer_name", "email", "category", "priority",
                    "subject", "description", "status"}


@app.patch("/api/public/tickets/{ticket_id}", response_model=Ticket,
           summary="Update part of a ticket", tags=["tickets"],
           openapi_extra=_body_schema(_TICKET_PARTIAL_EXAMPLE))
async def update_ticket(
    request: Request,
    ticket_id: str = Path(..., examples=["TKT-1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Update one or more fields of a ticket. Only the fields you send change."""
    row = db.get(TicketRow, _norm_ticket_id(ticket_id))
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    data = await _read_body(request)
    _validate_ticket_enums(data)
    for key, value in data.items():
        if key in TICKET_UPDATABLE:
            setattr(row, key, value)
    db.commit()
    return _ticket_with_message(_ticket_to_dict(row))


@app.put("/api/public/tickets/{ticket_id}", response_model=Ticket,
         summary="Replace a ticket", tags=["tickets"],
         openapi_extra=_body_schema(_TICKET_FULL_EXAMPLE))
async def replace_ticket(
    request: Request,
    ticket_id: str = Path(..., examples=["TKT-1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Replace the whole ticket with the fields you send."""
    row = db.get(TicketRow, _norm_ticket_id(ticket_id))
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    data = await _read_body(request)
    _validate_ticket_enums(data)
    try:
        new = NewTicket(**data)
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")
    row.customer_name = new.customer_name
    row.email = new.email
    row.category = new.category
    row.priority = new.priority
    row.subject = new.subject
    row.description = new.description
    row.status = new.status
    db.commit()
    return _ticket_with_message(_ticket_to_dict(row))


@app.delete("/api/public/tickets/{ticket_id}",
            summary="Delete a ticket", tags=["tickets"])
def delete_ticket(
    ticket_id: str = Path(..., examples=["TKT-1001"]),
    db: Session = Depends(get_db),
    _: None = Depends(verify_token),
):
    """Delete a ticket by its ID. Requires a valid Bearer token."""
    row = db.get(TicketRow, _norm_ticket_id(ticket_id))
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    db.delete(row)
    db.commit()
    return {"ticket_id": ticket_id.strip(),
            "message": f"Ticket {ticket_id.strip()} has been deleted."}
