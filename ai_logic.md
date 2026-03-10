# Logique IA — Assistant Opérationnel Vols & Incidents

## Vue d'ensemble

Pour chaque incident, le système produit une analyse structurée via deux couches :
1. **Couche 1 — Règles métier** : détection rapide par mots-clés
2. **Couche 2 — LLM (fallback)** : analyse profonde si les règles ne suffisent pas

---

## D1. Prompt Système LLM

### Contexte d'utilisation
Le prompt est envoyé à l'API d'un LLM (ex: Claude, GPT-4) via le node n8n
"HTTP Request". Il reçoit la description d'un incident et doit retourner
un JSON strict.

### Prompt Système

```
You are an aviation operations analyst for a commercial airline.
Your role is to analyze incident reports and produce structured operational data.

## INSTRUCTIONS

Given an incident description, you MUST return a JSON object with exactly
these 4 fields. No explanation, no markdown, no extra text — ONLY the JSON.

## OUTPUT FORMAT (strict)

{
  "normalized_category": "<one of: baggage | delay | safety | crew | technical | passenger | catering | other>",
  "ops_summary": "<max 20 words, neutral tone, factual>",
  "recommended_action": "<concrete action for ground ops team, max 15 words>",
  "confidence_score": <float between 0.00 and 1.00>
}

## CATEGORY DEFINITIONS

- baggage     → lost, delayed, damaged luggage or cargo
- delay       → departure or arrival delay, gate issues
- safety      → security threat, medical emergency, evacuation
- crew        → crew shortage, scheduling conflict, behavior
- technical   → mechanical failure, aircraft system issue
- passenger   → complaint, misconduct, boarding issue
- catering    → food, water, provisioning problem
- other       → does not fit any category above

## CONFIDENCE SCORE RULES

- 0.90 – 1.00 : description is clear and unambiguous
- 0.70 – 0.89 : description is mostly clear, minor uncertainty
- 0.50 – 0.69 : description is vague, category inferred
- 0.00 – 0.49 : description is too unclear to categorize reliably

## CONSTRAINTS

- Never include PII (names, passport numbers, seat numbers)
- If the description is empty or nonsensical, use category "other"
  and confidence_score 0.10
- ops_summary must be in the same language as the incident description
- Do not hallucinate details not present in the description
```

### Exemple d'appel complet

**Input (envoyé au LLM) :**
```
Analyze this aviation incident:

flight_id: LC123
description: "Late baggage delivery, passenger unhappy"
severity: 3
```

**Output attendu :**
```json
{
  "normalized_category": "baggage",
  "ops_summary": "Delayed baggage delivery caused passenger dissatisfaction on flight LC123.",
  "recommended_action": "Notify ground handling team and offer passenger compensation voucher.",
  "confidence_score": 0.92
}
```

---

## D2. Choix : Option B — Règles métier + fallback LLM

### Principe

Avant d'appeler le LLM (coûteux, lent), on applique des règles simples
basées sur des mots-clés. Si une règle matche avec suffisamment de
confiance, on économise l'appel API.

```
incident.description
        │
        ▼
┌───────────────────┐
│  Règles métier    │  ← rapide, gratuit, déterministe
│  (mots-clés)      │
└───────────────────┘
        │
   match >= 0.80 ?
        │
   OUI ──────────────────────────────► résultat direct
        │
   NON (vague, ambigu, inconnu)
        │
        ▼
┌───────────────────┐
│   Appel LLM       │  ← lent, payant, mais plus intelligent
│   (Claude/GPT-4)  │
└───────────────────┘
        │
        ▼
   Validation du JSON retourné
        │
   JSON valide ? ──── NON ──► fallback : category="other", score=0.10
        │
       OUI
        │
        ▼
   Stockage dans ai_insights
```

### Règles métier (implémentation Python/pseudo-code)

```python
RULES = {
    "baggage": [
        "baggage", "luggage", "bag", "cargo", "suitcase",
        "lost bag", "missing luggage", "delayed baggage"
    ],
    "delay": [
        "delay", "late", "postponed", "behind schedule",
        "gate change", "waiting", "retard"
    ],
    "safety": [
        "safety", "security", "threat", "emergency",
        "evacuation", "medical", "injury", "fire"
    ],
    "crew": [
        "crew", "pilot", "cabin crew", "staff shortage",
        "flight attendant", "captain"
    ],
    "technical": [
        "mechanical", "technical", "engine", "system failure",
        "malfunction", "maintenance", "avionics"
    ],
    "passenger": [
        "passenger", "complaint", "unhappy", "disruptive",
        "boarding", "misconduct", "refused"
    ],
    "catering": [
        "food", "catering", "meal", "water", "drink",
        "provisioning", "snack"
    ]
}

def classify_with_rules(description: str) -> dict | None:
    """
    Retourne un résultat si un mot-clé matche clairement.
    Retourne None si aucune règle ne s'applique (→ fallback LLM).
    """
    description_lower = description.lower()
    scores = {}

    for category, keywords in RULES.items():
        matches = sum(1 for kw in keywords if kw in description_lower)
        if matches > 0:
            scores[category] = matches

    if not scores:
        return None  # Aucune règle ne matche → LLM obligatoire

    best_category = max(scores, key=scores.get)
    match_count = scores[best_category]

    # Confiance basée sur le nombre de mots-clés trouvés
    confidence = min(0.60 + (match_count * 0.10), 0.85)

    # Si plusieurs catégories matchent → confiance réduite, mieux vaut le LLM
    if len(scores) > 1:
        confidence -= 0.15

    if confidence < 0.65:
        return None  # Trop ambigu → LLM obligatoire

    return {
        "normalized_category": best_category,
        "ops_summary": f"Incident detected: {description[:80]}",
        "recommended_action": "Review incident and follow standard ops procedure.",
        "confidence_score": round(confidence, 2)
    }
```

### Validation du JSON retourné par le LLM

```python
VALID_CATEGORIES = {
    "baggage", "delay", "safety", "crew",
    "technical", "passenger", "catering", "other"
}

def validate_llm_response(raw_response: str) -> dict:
    """
    Parse et valide la réponse JSON du LLM.
    Retourne un fallback safe en cas d'erreur.
    """
    FALLBACK = {
        "normalized_category": "other",
        "ops_summary": "Unable to analyze incident automatically.",
        "recommended_action": "Manual review required.",
        "confidence_score": 0.10
    }

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        # Le LLM a renvoyé du texte au lieu de JSON pur
        return FALLBACK

    # Vérification des champs obligatoires
    required_fields = [
        "normalized_category", "ops_summary",
        "recommended_action", "confidence_score"
    ]
    if not all(field in data for field in required_fields):
        return FALLBACK

    # Vérification de la catégorie
    if data["normalized_category"] not in VALID_CATEGORIES:
        data["normalized_category"] = "other"

    # Vérification du score de confiance
    score = data.get("confidence_score", 0)
    if not isinstance(score, (int, float)) or not (0 <= score <= 1):
        data["confidence_score"] = 0.10

    return data
```

---

## Question critique : Qu'est-ce qui peut casser le prompt ?

### Exemple d'incident problématique

```
"!!URGENT!! Pax 14F: ALLERGIC REACTION - EpiPen used - DIVERT NOW
 contact: john.doe@email.com tel: +1-555-0123 - CREW PANICKING"
```

### Pourquoi c'est dangereux

| Problème | Risque |
|---|---|
| PII (email, téléphone, nom) | Le LLM pourrait les répéter dans le résumé |
| Majuscules et ponctuation excessive | Peut déstabiliser le prompt et changer le comportement |
| Plusieurs catégories mélangées (safety + crew + passenger) | Le LLM hésite, confiance basse |
| Instruction cachée ("DIVERT NOW") | Injection de prompt possible |

### Protections mises en place

**1. Sanitisation avant envoi au LLM :**
```python
import re

def sanitize_description(text: str) -> str:
    # Supprimer les emails
    text = re.sub(r'[\w.-]+@[\w.-]+\.\w+', '[EMAIL]', text)
    # Supprimer les numéros de téléphone
    text = re.sub(r'\+?[\d\s\-().]{7,15}', '[PHONE]', text)
    # Supprimer les numéros de siège (ex: "14F")
    text = re.sub(r'\b\d{1,3}[A-F]\b', '[SEAT]', text)
    # Limiter la longueur
    return text[:500]
```

**2. Le prompt impose un format de sortie strict** — même si l'input est
   chaotique, le LLM est contraint à retourner uniquement les 4 champs.

**3. La validation JSON côté code** vérifie que la réponse est conforme
   indépendamment du contenu de l'incident.

**4. Confiance basse → revue manuelle** : si `confidence_score < 0.60`,
   l'incident est flaggué pour revue humaine et l'alerte Slack mentionne
   explicitement l'incertitude.

---

## Pourquoi l'Option B (règles + fallback LLM) est plus pertinente ici

| Critère | Règles métier | Deep Learning |
|---|---|---|
| Coût | Gratuit | Élevé (GPU, données) |
| Vitesse | < 1ms | 100ms–2s |
| Déterminisme | 100% prévisible | Variable |
| Données requises | 0 | Milliers d'exemples labellisés |
| Maintenance | Facile (modifier un fichier) | Nécessite re-entraînement |
| Interprétabilité | Totale | Boîte noire |

**Conclusion :** À ce stade (prototype, données mock, équipe junior), un
modèle deep learning serait une sur-ingénierie injustifiée. Les règles
métier couvrent 70–80% des cas courants. Le LLM gère les cas ambigus
sans nécessiter de dataset ni d'infrastructure ML.
