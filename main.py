"""
BrightSmile Dental — Sample Appointment API
===========================================

A small, self-contained API that a Voice AI agent can call as TOOLS during a
live phone call. Each endpoint is written to be "function-calling friendly":
clear summaries and descriptions, simple JSON in/out, and an auto-generated
OpenAPI spec at /openapi.json that the agent platform can import directly.

Sample business: a dental clinic. The agent can check availability, book,
look up, reschedule, and cancel appointments, and list services.

Storage is in-memory (a Python dict) — this is a demo, so it resets on restart.
No database needed.

Run locally:   uvicorn main:app --reload
Docs (try it): http://localhost:8000/docs
OpenAPI spec:  http://localhost:8000/openapi.json
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="BrightSmile Dental — Appointment API",
    version="1.0.0",
    description=(
        "Sample API for a dental clinic, designed to be called by a Voice AI "
        "agent as tools during a call. Book, look up, reschedule, and cancel "
        "appointments, check availability, and list services."
    ),
)

# Allow any origin so the agent platform / browser demos can call it freely.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------
SERVICES = {
    "cleaning": {"name": "Teeth Cleaning", "duration_min": 30, "price_usd": 80},
    "checkup": {"name": "Routine Check-up", "duration_min": 20, "price_usd": 50},
    "whitening": {"name": "Teeth Whitening", "duration_min": 60, "price_usd": 200},
    "filling": {"name": "Cavity Filling", "duration_min": 45, "price_usd": 150},
}

# Fixed set of daily slots the clinic offers.
DAILY_SLOTS = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]

# appointment_id -> appointment dict
APPOINTMENTS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class BookingRequest(BaseModel):
    patient_name: str = Field(..., examples=["Jayant Raj"])
    phone: str = Field(..., examples=["+919508509567"])
    service: str = Field(..., description="One of: cleaning, checkup, whitening, filling",
                         examples=["cleaning"])
    date: str = Field(..., description="Date in YYYY-MM-DD format", examples=["2026-09-01"])
    time: str = Field(..., description="Slot time in HH:MM (24h)", examples=["10:00"])


class RescheduleRequest(BaseModel):
    date: str = Field(..., description="New date YYYY-MM-DD", examples=["2026-09-02"])
    time: str = Field(..., description="New slot HH:MM", examples=["14:00"])


class Appointment(BaseModel):
    appointment_id: str
    patient_name: str
    phone: str
    service: str
    date: str
    time: str
    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _validate_service(service: str) -> None:
    if service not in SERVICES:
        raise HTTPException(status_code=400,
                            detail=f"Unknown service '{service}'. Valid: {list(SERVICES)}")


def _booked_times(on_date: str) -> set[str]:
    return {a["time"] for a in APPOINTMENTS.values()
            if a["date"] == on_date and a["status"] == "booked"}


# ---------------------------------------------------------------------------
# Endpoints (each = one tool the agent can call)
# ---------------------------------------------------------------------------
@app.get("/health", summary="Health check", tags=["system"])
def health():
    """Simple check that the API is running."""
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/services", summary="List services and prices", tags=["tools"])
def list_services():
    """Return the clinic's services with their duration and price.
    Use this when the caller asks what treatments are offered or how much they cost."""
    return {"services": SERVICES}


@app.get("/availability", summary="Check available appointment slots", tags=["tools"])
def check_availability(
    date: str = Query(..., description="Date to check, YYYY-MM-DD", examples=["2026-09-01"])
):
    """Return the free appointment slots for a given date.
    Use this when the caller asks what times are available on a day."""
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    booked = _booked_times(date)
    free = [s for s in DAILY_SLOTS if s not in booked]
    return {"date": date, "available_slots": free}


@app.post("/appointments", response_model=Appointment,
          summary="Book a new appointment", tags=["tools"])
def book_appointment(req: BookingRequest):
    """Book a new appointment for a patient.
    Use this once you have the patient's name, phone, chosen service, date and time.
    Returns the appointment with its appointment_id, which the caller should keep."""
    _validate_service(req.service)
    if req.time not in DAILY_SLOTS:
        raise HTTPException(status_code=400,
                            detail=f"Invalid time. Valid slots: {DAILY_SLOTS}")
    if req.time in _booked_times(req.date):
        raise HTTPException(status_code=409,
                            detail=f"{req.time} on {req.date} is already booked")
    appt_id = "APT-" + uuid.uuid4().hex[:6].upper()
    appt = {
        "appointment_id": appt_id, "patient_name": req.patient_name,
        "phone": req.phone, "service": req.service, "date": req.date,
        "time": req.time, "status": "booked",
    }
    APPOINTMENTS[appt_id] = appt
    return appt


@app.get("/appointments/{appointment_id}", response_model=Appointment,
         summary="Look up an appointment", tags=["tools"])
def get_appointment(appointment_id: str):
    """Look up an existing appointment by its ID.
    Use this when the caller wants to confirm or check the details of their booking."""
    appt = APPOINTMENTS.get(appointment_id.upper())
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@app.put("/appointments/{appointment_id}", response_model=Appointment,
         summary="Reschedule an appointment", tags=["tools"])
def reschedule_appointment(appointment_id: str, req: RescheduleRequest):
    """Change the date and/or time of an existing appointment.
    Use this when the caller wants to move their booking to a different slot."""
    appt = APPOINTMENTS.get(appointment_id.upper())
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if req.time not in DAILY_SLOTS:
        raise HTTPException(status_code=400, detail=f"Invalid time. Valid: {DAILY_SLOTS}")
    if req.time in _booked_times(req.date):
        raise HTTPException(status_code=409, detail="That slot is already booked")
    appt["date"], appt["time"] = req.date, req.time
    return appt


@app.delete("/appointments/{appointment_id}",
            summary="Cancel an appointment", tags=["tools"])
def cancel_appointment(appointment_id: str):
    """Cancel an existing appointment by its ID.
    Use this when the caller wants to cancel their booking."""
    appt = APPOINTMENTS.get(appointment_id.upper())
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appt["status"] = "cancelled"
    return {"appointment_id": appt["appointment_id"], "status": "cancelled"}
