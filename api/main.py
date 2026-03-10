import re
from datetime import date as date_type
from fastapi import FastAPI, Query, HTTPException, Depends, status
from fastapi.responses import JSONResponse

from auth import verify_token
from db import (
    get_flights_by_date,
    get_incidents_by_date,
    get_incidents_by_flight,
    flight_exists,
    save_ai_insight,
)
from ai_service import analyze_incident

app = FastAPI(
    title="Ops Assistant API",
    description="API opérationnelle pour la surveillance des vols et incidents",
    version="1.0.0"
)


# ------------------------------------------------------------------
# Health check — utilisé par Docker et Kubernetes
# ------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------
# GET /ops/summary?date=YYYY-MM-DD
# Résumé opérationnel d'une journée
# ------------------------------------------------------------------
@app.get("/ops/summary")
def ops_summary(date: str = Query(..., description="Date au format YYYY-MM-DD")):

    # Validation du format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_DATE", "message": "date must be in YYYY-MM-DD format"}
        )

    # Validation calendaire
    try:
        date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_DATE", "message": f"{date} is not a valid calendar date"}
        )

    # Récupération des données
    try:
        flights   = get_flights_by_date(date)
        incidents = get_incidents_by_date(date)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "DB_ERROR", "message": "Database unavailable"}
        )

    if not flights:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NO_DATA", "message": f"No flights found for {date}"}
        )

    # Vols en retard (> 30 min)
    delayed = [
        {
            "flight_id":     f["flight_id"],
            "route":         f["route"],
            "delay_minutes": round(float(f["delay_minutes"]), 1) if f["delay_minutes"] else None,
            "status":        f["status"]
        }
        for f in flights
        if f["delay_minutes"] and float(f["delay_minutes"]) > 30
    ]

    return {
        "date":             date,
        "total_flights":    len(flights),
        "total_incidents":  len(incidents),
        "delayed_flights":  delayed,
        "incidents_summary": [
            {
                "incident_id":          i["incident_id"],
                "flight_id":            i["flight_id"],
                "severity":             i["severity"],
                "normalized_category":  i.get("normalized_category"),
                "ops_summary":          i.get("ops_summary"),
            }
            for i in incidents
        ]
    }


# ------------------------------------------------------------------
# POST /ai/analyze?flight_id=LC123
# Déclenche l'analyse IA pour tous les incidents d'un vol
# ------------------------------------------------------------------
@app.post("/ai/analyze")
def ai_analyze(
    flight_id: str = Query(..., min_length=2, max_length=20, description="ID du vol"),
    token: str = Depends(verify_token)   # Endpoint protégé par Bearer token
):

    # Validation du format du flight_id
    if not re.match(r"^[A-Z0-9]{2,20}$", flight_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_FLIGHT_ID", "message": "flight_id must be uppercase alphanumeric"}
        )

    # Vérification que le vol existe
    try:
        if not flight_exists(flight_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "FLIGHT_NOT_FOUND", "message": f"No flight with id {flight_id}"}
            )
        incidents = get_incidents_by_flight(flight_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "DB_ERROR", "message": "Database unavailable"}
        )

    if not incidents:
        return {"flight_id": flight_id, "analyzed_incidents": []}

    # Analyse IA pour chaque incident
    results = []
    for incident in incidents:
        insight = analyze_incident(incident)
        save_ai_insight(incident["incident_id"], insight)
        results.append({
            "incident_id":          incident["incident_id"],
            "normalized_category":  insight["normalized_category"],
            "ops_summary":          insight["ops_summary"],
            "recommended_action":   insight["recommended_action"],
            "confidence_score":     insight["confidence_score"],
        })

    return {"flight_id": flight_id, "analyzed_incidents": results}
