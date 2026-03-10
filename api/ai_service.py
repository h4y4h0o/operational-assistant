import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"

VALID_CATEGORIES = {
    "baggage", "delay", "safety", "crew",
    "technical", "passenger", "catering", "other"
}

FALLBACK = {
    "normalized_category": "other",
    "ops_summary": "Unable to analyze incident automatically.",
    "recommended_action": "Manual review required.",
    "confidence_score": 0.10
}

SYSTEM_PROMPT = """You are an aviation operations analyst.
Analyze the incident and return ONLY a JSON object with exactly these fields:
{
  "normalized_category": "<baggage|delay|safety|crew|technical|passenger|catering|other>",
  "ops_summary": "<max 20 words, factual>",
  "recommended_action": "<max 15 words, concrete action>",
  "confidence_score": <float 0.00 to 1.00>
}
No explanation, no markdown, ONLY the JSON."""


def analyze_incident(incident: dict) -> dict:
    """
    Appelle Groq pour analyser un incident.
    Retourne toujours un dict valide (fallback si erreur).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {**FALLBACK, "ops_summary": "GROQ_API_KEY not configured."}

    user_message = (
        f"Analyze this aviation incident:\n"
        f"flight_id: {incident['flight_id']}\n"
        f"description: {incident['description']}\n"
        f"severity: {incident['severity']}/5"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ],
        "temperature": 0.1
    }

    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=15.0
        )
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]
        return validate_llm_response(raw_content)

    except httpx.TimeoutException:
        return {**FALLBACK, "ops_summary": "LLM service timeout."}
    except Exception:
        return FALLBACK


def validate_llm_response(raw: str) -> dict:
    """
    Parse et valide la réponse JSON du LLM.
    Retourne un fallback safe si la réponse est invalide.
    """
    # Nettoyer les balises markdown si présentes (```json ... ```)
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        return FALLBACK

    # Vérifier les champs obligatoires
    required = ["normalized_category", "ops_summary", "recommended_action", "confidence_score"]
    if not all(f in data for f in required):
        return FALLBACK

    # Valider la catégorie
    if data["normalized_category"] not in VALID_CATEGORIES:
        data["normalized_category"] = "other"

    # Valider le score de confiance
    score = data.get("confidence_score", 0)
    if not isinstance(score, (int, float)) or not (0 <= score <= 1):
        data["confidence_score"] = 0.10

    return {
        "normalized_category": data["normalized_category"],
        "ops_summary":         str(data["ops_summary"])[:200],
        "recommended_action":  str(data["recommended_action"])[:200],
        "confidence_score":    round(float(data["confidence_score"]), 2)
    }
