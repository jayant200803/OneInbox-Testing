# BrightSmile Dental — Sample Appointment API

A small FastAPI service that a **Voice AI agent** can call as **tools** during a
live call. Sample business: a dental clinic. The agent can check availability,
book, look up, reschedule, and cancel appointments, and list services.

Built by Jayant Raj as the API for the voice-agent tools demo.

---

## What this is for

The voice agent needs real functions to *do* things on a call ("book me a
cleaning Thursday at 10"). Each endpoint here is one such tool. The agent
platform imports the OpenAPI spec (`/openapi.json`) and calls these endpoints
during the conversation.

Storage is in-memory (resets on restart) — this is a demo, no database needed.

---

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

- Interactive docs (try each endpoint): http://localhost:8000/docs
- OpenAPI spec (for the agent platform): http://localhost:8000/openapi.json

---

## Deploy (so the AI can reach it over the internet)

The agent calls this over the internet, so it can't be localhost. Easiest free
options:

**Render (recommended)** — this repo already has `render.yaml`:
1. Push this folder to a GitHub repo.
2. Go to render.com → New → Web Service → connect the repo.
3. It auto-detects `render.yaml`. Click deploy.
4. You get a public URL like `https://brightsmile-dental-api.onrender.com`.

**Railway / Fly.io** — similar; a `Procfile` is included.

**Quick temporary URL (for testing only)** — run locally then:
```bash
npx ngrok http 8000       # gives a temporary public https URL
```

---

## Endpoints (each = one agent tool)

| Method | Path | What it does |
|---|---|---|
| GET | `/services` | List services and prices |
| GET | `/availability?date=YYYY-MM-DD` | Free slots on a date |
| POST | `/appointments` | Book a new appointment |
| GET | `/appointments/{id}` | Look up an appointment |
| PUT | `/appointments/{id}` | Reschedule |
| DELETE | `/appointments/{id}` | Cancel |
| GET | `/health` | Health check |

See `TOOLS_FOR_SAANIYA.md` for the function-calling descriptions to give the
agent.

---

## What to hand over

Send Saaniya:
1. The deployed base URL (e.g. `https://...onrender.com`)
2. The link `<base-url>/openapi.json`
3. `TOOLS_FOR_SAANIYA.md` (the tool descriptions)
