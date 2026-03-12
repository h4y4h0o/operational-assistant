# Flight & Incident Operations Assistant

> Version française : [README.fr.md](README.fr.md)

Automated pipeline for flight monitoring, AI-powered incident analysis, and Slack alerts.

## Real Architecture (implemented and tested)

```
data/flights.json   ──► HTTP Request (n8n) ──► Upsert Flights   ──► Postgres
data/incidents.json ──► HTTP Request (n8n) ──► Upsert Incidents  ──► Postgres
                                                                        │
                                                                        ▼
                                                          POST /ai/analyze (FastAPI)
                                                                        │
                                                                        ▼
                                                           Groq LLM (llama-3.3-70b)
                                                                        │
                                                                        ▼
                                                           Store ai_insights (Postgres)
                                                                        │
                                                                        ▼
                                                           GET /ops/summary (FastAPI)
                                                                        │
                                                                        ▼
                                                           Slack #ops-alerts
```

**Tech stack:** n8n · PostgreSQL · FastAPI (Python) · Groq LLM · Docker · Azure

---

## Repository Structure

```
.
├── schema.sql              # Postgres schema (3 tables + indexes)
├── queries.sql             # SQL queries + index justification
├── n8n_workflow.json       # Exported n8n workflow
├── n8n_schema/
│   └── workflow_schema.md  # Visual workflow diagram + Q&A
├── screenshots/
│   ├── n8n_workflow.png    # Screenshot of the full n8n workflow
│   └── slack_alert.png     # Screenshot of the Slack alert received
├── api/
│   ├── main.py             # FastAPI routes (GET /ops/summary, POST /ai/analyze)
│   ├── db.py               # Postgres connection + queries
│   ├── ai_service.py       # Groq LLM call + JSON validation
│   ├── auth.py             # Bearer token verification
│   └── requirements.txt    # Python dependencies
├── data/
│   ├── flights.json        # Mock flight data
│   └── incidents.json      # Mock incident data
├── api.md                  # API endpoint description + security
├── ai_logic.md             # LLM prompt + business rules + validation
├── azure_deployment.md     # Azure architecture + Kubernetes + secrets
├── Dockerfile              # API Docker image (annotated)
├── docker-compose.yml      # Orchestrates Postgres + API + n8n locally
├── .env.example            # Environment variables template
├── CHATGPT_LOG.md          # AI usage log
└── README.md               # French version
```

---

## Quick Start (local)

### Prerequisites
- Docker Desktop installed
- A Groq API key (free at console.groq.com)

### 1. Configure environment variables

```bash
cp .env.example .env
# Open .env and fill in the values:
# GROQ_API_KEY=gsk_...
# API_TOKENS=your-secret-token
```

### 2. Start all services

```bash
docker compose up -d --build
```

This automatically starts:
- **ops-postgres** on port `5432` (SQL schema applied on startup)
- **ops-api** on port `8000`
- **ops-n8n** on port `5678`

Verify everything is running:
```bash
docker compose ps
```

### 3. Start the mock file server

In a separate terminal (keep it open):
```bash
python3 -m http.server 8080
```

This exposes `data/flights.json` and `data/incidents.json` to n8n via:
```
http://host.docker.internal:8080/data/flights.json
http://host.docker.internal:8080/data/incidents.json
```

### 4. Import the n8n workflow

1. Open `http://localhost:5678` (login: `admin` / `admin123`)
2. Menu `...` → **Import from file** → select `n8n_workflow.json`
3. Configure the **Postgres** credential in n8n:
   - Host: `postgres`
   - Database: `opsdb`
   - User: `opsadmin`
   - Password: `opspassword123`
4. Configure the **Slack** credential in n8n:
   - Type: `Access Token`
   - Token: `xoxb-...` (Bot User OAuth Token from api.slack.com/apps)
   - Required scopes: `chat:write`, `chat:write.public`
5. Click **"Test workflow"**

### 5. Slack alert received

![Slack Alert](screenshots/slack_alert.png)

---

## Testing the API directly

```bash
# Health check
curl http://localhost:8000/health

# Daily operational summary
curl "http://localhost:8000/ops/summary?date=2026-01-10"

# Trigger AI analysis for a flight (replace <token> with the value of API_TOKENS in .env)
curl -X POST "http://localhost:8000/ai/analyze?flight_id=LC123" \
     -H "Authorization: Bearer <token>"
```

### Sample response — GET /ops/summary

```json
{
  "date": "2026-01-10",
  "total_flights": 3,
  "total_incidents": 3,
  "delayed_flights": [
    {
      "flight_id": "LC123",
      "route": "ORY-EWR",
      "delay_minutes": 42.0,
      "status": "departed"
    }
  ],
  "incidents_summary": [
    {
      "incident_id": "INC46",
      "flight_id": "LC123",
      "severity": 5,
      "normalized_category": "technical",
      "ops_summary": "Engine issue before departure"
    }
  ]
}
```

### Sample response — POST /ai/analyze

```json
{
  "flight_id": "LC123",
  "analyzed_incidents": [
    {
      "incident_id": "INC46",
      "normalized_category": "technical",
      "ops_summary": "Engine issue before departure",
      "recommended_action": "Inspect engine 2 immediately",
      "confidence_score": 0.95
    },
    {
      "incident_id": "INC45",
      "normalized_category": "baggage",
      "ops_summary": "Late baggage delivery",
      "recommended_action": "Improve baggage handling",
      "confidence_score": 0.80
    }
  ]
}
```

---

## n8n Workflow — actual nodes

![n8n Workflow](screenshots/n8n_workflow.png)

| # | Node | Type | Role |
|---|---|---|---|
| 1 | Manual Trigger | `manualTrigger` | Triggers the pipeline |
| 2 | HTTP Request (flights) | `httpRequest` GET | Loads flights.json from local server |
| 3 | Upsert Flights | `postgres` Execute Query | INSERT ON CONFLICT DO UPDATE |
| 4 | HTTP Request (incidents) | `httpRequest` GET | Loads incidents.json from local server |
| 5 | Upsert Incidents | `postgres` Execute Query | INSERT ON CONFLICT DO NOTHING |
| 6 | Call AI Analyze | `httpRequest` POST | POST /ai/analyze with Bearer token |
| 7 | Get Summary | `httpRequest` GET | GET /ops/summary |
| 8 | Build Slack Message | `code` | Builds dynamic message from API responses |
| 9 | Send a message | `slack` | Sends via Bot Token (Access Token) to #ops-alerts |

---

## Key Technical Decisions

### LLM: Groq (llama-3.3-70b) over OpenAI

Groq provides ultra-fast inference (~500 tokens/s) and a free API tier.
The `llama-3.3-70b-versatile` model is powerful enough to classify incidents
into structured JSON reliably.

### Business rules + LLM fallback

For a prototype without a labelled dataset, keyword-based rules cover 70-80%
of common cases instantly and for free. The LLM handles ambiguous cases.
See `ai_logic.md`.

### Idempotence in n8n

`ON CONFLICT DO NOTHING / DO UPDATE` ensures the workflow can be re-run any
number of times without creating duplicate records in the database.

### SQL range queries instead of DATE()

Date-filtering queries use a range on `sched_dep_utc` instead of
`DATE(sched_dep_utc) = x`. The `DATE()` function call prevents Postgres from
using the btree index (requires evaluating every row — full table scan).
The range allows Postgres to use `idx_flights_sched_dep_utc` directly:

```sql
-- ❌ Full table scan — index not used
WHERE DATE(sched_dep_utc) = '2026-01-10'

-- ✅ Index range scan — idx_flights_sched_dep_utc used
WHERE sched_dep_utc >= '2026-01-10'::date
  AND sched_dep_utc <  '2026-01-10'::date + INTERVAL '1 day'
```

### API token security

The Bearer token is never hardcoded in the source code. It is loaded from the
`API_TOKENS` environment variable at API startup. If the variable is missing,
the API refuses to start with an explicit error.

### python:3.11-slim over alpine

Alpine causes compilation issues with `psycopg2` (musl vs glibc).
`slim` is the best size/compatibility trade-off.

### Loading JSON files via HTTP

The n8n "Read/Write from Disk" node returns raw binary (metadata only). The
chosen solution: a Python `http.server` exposing the files, consumed by an
HTTP Request node that automatically parses the JSON.

### 9 nodes instead of the suggested 4-6

The spec suggests 4-6 nodes as a simplicity guideline. Our workflow uses 9
for justified architectural reasons:

**1. Single responsibility principle**

Each node does exactly one thing:
- One node loads, one stores, one analyzes, one builds the message
- If a node fails, you immediately know which one and why
- A monolithic "do-everything" node would be harder to debug and maintain

**2. Sequential flights → incidents**

Loading is sequential: flights are inserted before incidents. This guarantees
referential integrity — an incident references a `flight_id` that must already
exist in the database before insertion.

**3. Mandatory sequential AI → Summary**

`POST /ai/analyze` writes to `ai_insights`, `GET /ops/summary` reads from
`ai_insights`. These two calls cannot be merged without breaking the business
logic — they remain two distinct nodes.

**Conclusion**: node count is not a quality indicator. A well-structured
9-node workflow is preferable to an opaque 5-node workflow that does too much.

### Native Slack node over Incoming Webhook

The native n8n Slack node (`slack` v2.4) with a Bot Token (`xoxb-...`) is
preferred over an HTTP Request to an Incoming Webhook for two reasons:
- **Security**: the token is stored in n8n's AES-256 encrypted credentials,
  never exposed in the exported workflow JSON
- **Features**: full Slack API access (dynamic channels, threads, reactions)
  vs plain text only with webhooks

---

## Security

- No secrets in the repo (`.env` in `.gitignore`)
- `API_TOKENS` loaded from environment — API refuses to start if missing
- `GROQ_API_KEY` injected via Docker environment variable
- Slack Bot Token stored in n8n AES-256 encrypted credentials
- API container runs as non-root user
- In production: Azure Key Vault + Managed Identity

---

## Azure Deployment (conceptual)

| Component | Azure Service |
|---|---|
| Postgres | Azure Database for PostgreSQL Flexible Server |
| API + n8n | Azure Kubernetes Service (AKS) |
| Docker images | Azure Container Registry (ACR) |
| Secrets | Azure Key Vault |

See `azure_deployment.md` for the full architecture and redeployment strategy.
