# Tools for the Voice Agent — BrightSmile Dental API

Hi Saaniya — this is the sample API for the voice agent to call during a call.
Base URL (once deployed): **`<PASTE_DEPLOYED_URL_HERE>`**
Import spec directly from: **`<BASE_URL>/openapi.json`**

Below is each tool with the exact info the agent needs (name, when to use it,
method, path, parameters, and an example). All requests/responses are JSON.

---

### 1. list_services
- **When to use:** caller asks what treatments are offered or how much they cost.
- **Call:** `GET /services`
- **Params:** none
- **Returns:** services with duration and price.

### 2. check_availability
- **When to use:** caller asks what times are open on a given day.
- **Call:** `GET /availability?date=YYYY-MM-DD`
- **Params:** `date` (string, YYYY-MM-DD, required)
- **Example:** `GET /availability?date=2026-09-01`
- **Returns:** `{ "date": "...", "available_slots": ["09:00","11:00", ...] }`

### 3. book_appointment
- **When to use:** once you have the patient's name, phone, service, date and time.
- **Call:** `POST /appointments`
- **Body (JSON):**
  ```json
  {
    "patient_name": "Jayant Raj",
    "phone": "+919508509567",
    "service": "cleaning",
    "date": "2026-09-01",
    "time": "10:00"
  }
  ```
- **service** must be one of: `cleaning`, `checkup`, `whitening`, `filling`
- **Returns:** the appointment including `appointment_id` (tell the caller to keep it).

### 4. get_appointment
- **When to use:** caller wants to confirm/check an existing booking.
- **Call:** `GET /appointments/{appointment_id}`
- **Example:** `GET /appointments/APT-C65551`

### 5. reschedule_appointment
- **When to use:** caller wants to move their booking to a different slot.
- **Call:** `PUT /appointments/{appointment_id}`
- **Body (JSON):** `{ "date": "2026-09-02", "time": "14:00" }`

### 6. cancel_appointment
- **When to use:** caller wants to cancel their booking.
- **Call:** `DELETE /appointments/{appointment_id}`

---

### Notes
- Valid time slots: `09:00, 10:00, 11:00, 14:00, 15:00, 16:00`.
- Booking a taken slot returns HTTP 409; unknown appointment returns 404.
- Storage is in-memory (demo) — it resets if the server restarts.
- CORS is open, so browser/demo clients can call it freely.

Any questions on the API, ping me. — Jayant
