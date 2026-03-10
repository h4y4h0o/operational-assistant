import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Retourne une connexion Postgres depuis les variables d'environnement."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "opsdb"),
        user=os.getenv("POSTGRES_USER", "opsadmin"),
        password=os.getenv("POSTGRES_PASSWORD", "opspassword123"),
    )


def get_flights_by_date(date_str: str) -> list[dict]:
    """Retourne tous les vols d'une date donnée."""
    query = """
        SELECT flight_id, route, sched_dep_utc, actual_dep_utc, status,
               CASE
                 WHEN actual_dep_utc IS NOT NULL
                 THEN EXTRACT(EPOCH FROM (actual_dep_utc - sched_dep_utc)) / 60
                 ELSE NULL
               END AS delay_minutes
        FROM flights
        WHERE DATE(sched_dep_utc) = %s
        ORDER BY sched_dep_utc
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (date_str,))
            return [dict(row) for row in cur.fetchall()]


def get_incidents_by_flight(flight_id: str) -> list[dict]:
    """Retourne tous les incidents d'un vol."""
    query = """
        SELECT i.incident_id, i.flight_id, i.description, i.severity,
               i.created_at_utc, ai.normalized_category, ai.ops_summary,
               ai.recommended_action, ai.confidence_score
        FROM incidents i
        LEFT JOIN ai_insights ai ON ai.incident_id = i.incident_id
        WHERE i.flight_id = %s
        ORDER BY i.severity DESC
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (flight_id,))
            return [dict(row) for row in cur.fetchall()]


def get_incidents_by_date(date_str: str) -> list[dict]:
    """Retourne tous les incidents pour les vols d'une date donnée."""
    query = """
        SELECT i.incident_id, i.flight_id, i.description, i.severity,
               i.created_at_utc, ai.normalized_category, ai.ops_summary,
               ai.recommended_action, ai.confidence_score
        FROM incidents i
        JOIN flights f ON f.flight_id = i.flight_id
        LEFT JOIN ai_insights ai ON ai.incident_id = i.incident_id
        WHERE DATE(f.sched_dep_utc) = %s
        ORDER BY i.severity DESC
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (date_str,))
            return [dict(row) for row in cur.fetchall()]


def flight_exists(flight_id: str) -> bool:
    """Vérifie si un vol existe en base."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM flights WHERE flight_id = %s", (flight_id,))
            return cur.fetchone() is not None


def save_ai_insight(incident_id: str, insight: dict):
    """Insère ou met à jour une analyse IA en base."""
    query = """
        INSERT INTO ai_insights
            (incident_id, normalized_category, ops_summary, recommended_action, confidence_score)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (incident_id) DO UPDATE SET
            normalized_category = EXCLUDED.normalized_category,
            ops_summary         = EXCLUDED.ops_summary,
            recommended_action  = EXCLUDED.recommended_action,
            confidence_score    = EXCLUDED.confidence_score,
            analyzed_at_utc     = NOW()
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (
                incident_id,
                insight["normalized_category"],
                insight["ops_summary"],
                insight["recommended_action"],
                insight["confidence_score"],
            ))
        conn.commit()
