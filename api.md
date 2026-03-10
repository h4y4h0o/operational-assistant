# API — Assistant Opérationnel

## Vue d'ensemble

API REST minimale construite avec **FastAPI** (Python).
Elle expose 2 endpoints consommés par le workflow n8n.

```
n8n workflow
    │
    ├── GET /ops/summary?date=...   → résumé du jour
    └── POST /ai/analyze?flight_id= → déclenche l'analyse IA
```

---

## Endpoint 1 — GET /ops/summary

### Description
Retourne un résumé opérationnel pour une date donnée :
vols du jour, incidents associés, insights IA disponibles.

### URL
```
GET /ops/summary?date=2026-01-10
```

### Validation des entrées
- `date` est obligatoire
- Format attendu : `YYYY-MM-DD`
- Refusé si date invalide ou absente

### Réponse succès (200)
```json
{
  "date": "2026-01-10",
  "total_flights": 12,
  "total_incidents": 3,
  "delayed_flights": [
    {
      "flight_id": "LC123",
      "route": "ORY-EWR",
      "delay_minutes": 42,
      "status": "departed"
    }
  ],
  "incidents_summary": [
    {
      "incident_id": "INC45",
      "flight_id": "LC123",
      "severity": 3,
      "normalized_category": "baggage",
      "ops_summary": "Delayed baggage delivery caused passenger dissatisfaction."
    }
  ]
}
```

### Réponses d'erreur
```json
// 400 — paramètre manquant ou invalide
{ "error": "INVALID_DATE", "message": "date must be in YYYY-MM-DD format" }

// 404 — aucune donnée pour cette date
{ "error": "NO_DATA", "message": "No flights found for 2026-01-10" }

// 500 — erreur base de données
{ "error": "DB_ERROR", "message": "Database unavailable" }
```

### Implémentation FastAPI
```python
from fastapi import FastAPI, Query, HTTPException
from datetime import date
import re

app = FastAPI()

@app.get("/ops/summary")
async def ops_summary(date: str = Query(..., description="Date YYYY-MM-DD")):

    # Validation du format de date
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_DATE", "message": "date must be in YYYY-MM-DD format"}
        )

    try:
        target_date = date.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_DATE", "message": f"{date} is not a valid calendar date"}
        )

    # Requête Postgres
    flights = await db.fetch_flights_by_date(target_date)

    if not flights:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_DATA", "message": f"No flights found for {date}"}
        )

    return build_summary_response(flights, target_date)
```

---

## Endpoint 2 — POST /ai/analyze

### Description
Déclenche l'analyse IA pour tous les incidents d'un vol donné.
Appelle le LLM, stocke les résultats dans `ai_insights`, retourne le JSON.

### URL
```
POST /ai/analyze?flight_id=LC123
```

### Validation des entrées
- `flight_id` est obligatoire
- Format : lettres majuscules + chiffres, 3–10 caractères
- Le vol doit exister en base

### Réponse succès (200)
```json
{
  "flight_id": "LC123",
  "analyzed_incidents": [
    {
      "incident_id": "INC45",
      "normalized_category": "baggage",
      "ops_summary": "Delayed baggage delivery caused passenger dissatisfaction.",
      "recommended_action": "Notify ground handling and offer compensation voucher.",
      "confidence_score": 0.92,
      "analyzed_at_utc": "2026-01-10T11:15:00Z"
    }
  ]
}
```

### Réponses d'erreur
```json
// 400 — flight_id manquant ou invalide
{ "error": "INVALID_FLIGHT_ID", "message": "flight_id must be 3-10 alphanumeric uppercase characters" }

// 401 — non autorisé (voir sécurité)
{ "error": "UNAUTHORIZED", "message": "Valid Bearer token required" }

// 404 — vol introuvable
{ "error": "FLIGHT_NOT_FOUND", "message": "No flight with id LC123" }

// 502 — LLM indisponible
{ "error": "AI_UNAVAILABLE", "message": "LLM service timeout, try again later" }
```

### Implémentation FastAPI
```python
@app.post("/ai/analyze")
async def ai_analyze(
    flight_id: str = Query(..., min_length=3, max_length=10),
    token: str = Depends(verify_token)   # sécurité (voir ci-dessous)
):
    # Validation format
    if not re.match(r"^[A-Z0-9]{3,10}$", flight_id):
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FLIGHT_ID", "message": "..."}
        )

    # Vérification existence du vol
    flight = await db.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail={"error": "FLIGHT_NOT_FOUND"})

    # Récupération des incidents
    incidents = await db.get_incidents_by_flight(flight_id)

    # Analyse IA pour chaque incident
    results = []
    for incident in incidents:
        insight = await analyze_incident(incident)      # règles + LLM
        await db.upsert_ai_insight(incident.id, insight)
        results.append(insight)

    return {"flight_id": flight_id, "analyzed_incidents": results}
```

---

## Sécurité — Comment empêcher un accès non autorisé

### Réponse à la question du cas pratique

La protection repose sur **3 couches** :

### Couche 1 — Bearer Token (obligatoire)
```python
from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Vérifie que le token est valide avant d'exécuter l'endpoint."""
    valid_tokens = os.getenv("API_VALID_TOKENS", "").split(",")

    if credentials.credentials not in valid_tokens:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "Valid Bearer token required"}
        )
```

Le token est passé dans le header `Authorization: Bearer <token>`.
Dans n8n, il est stocké dans les **credentials chiffrés** (jamais en clair).

### Couche 2 — Rate limiting (abus)
```python
# Limiter à 10 analyses par minute par token
# Utiliser slowapi ou un middleware Redis
@app.post("/ai/analyze")
@limiter.limit("10/minute")
async def ai_analyze(...):
    ...
```
Sans cela, un attaquant pourrait générer des milliers d'appels LLM
et faire exploser la facture API.

### Couche 3 — Réseau (en production Azure)
- L'API n'est accessible qu'en interne (VNet Azure)
- n8n et l'API sont dans le même réseau privé
- L'endpoint `/ai/analyze` n'est **jamais** exposé sur Internet directement

---

## Structure des fichiers
```
api/
├── main.py          ← routes FastAPI
├── db.py            ← requêtes Postgres (asyncpg)
├── ai_service.py    ← logique règles + LLM
├── auth.py          ← vérification token
└── requirements.txt
```
