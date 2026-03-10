# Assistant Opérationnel Vols & Incidents

Pipeline automatisé de surveillance des vols, analyse IA des incidents, et alertes Slack.

## Architecture

```
flights.json   ──┐
                 ├──► n8n workflow ──► Postgres ──► API IA ──► Slack #ops-alerts
incidents.json ──┘
```

**Stack technique :** n8n · PostgreSQL · FastAPI (Python) · LLM (Claude/GPT-4) · Docker · Azure

---

## Structure du repo

```
.
├── schema.sql              # Schéma Postgres (3 tables + index)
├── queries.sql             # Requêtes SQL + justification des index
├── n8n_workflow.json       # Workflow n8n exporté (6 nodes)
├── n8n_schema/
│   └── workflow_schema.md  # Schéma visuel du workflow + réponses aux questions
├── api.md                  # Description des 2 endpoints API + sécurité
├── ai_logic.md             # Prompt LLM + logique règles métier + validation
├── azure_deployment.md     # Architecture Azure + Kubernetes + secrets
├── Dockerfile              # Image Docker de l'API (commentée)
├── api/
│   └── requirements.txt    # Dépendances Python
├── CHATGPT_LOG.md          # Journal d'utilisation de l'IA
└── README.md               # Ce fichier
```

---

## Démarrage rapide (local)

### Prérequis
- Docker Desktop installé
- Un compte n8n Cloud (ou n8n en local)

### 1. Lancer Postgres + l'API avec Docker

```bash
# Copier les variables d'environnement
cp .env.example .env
# Remplir les valeurs dans .env (ne jamais commiter ce fichier)

# Lancer les services
docker compose up -d
```

### 2. Initialiser la base de données

```bash
# Appliquer le schéma SQL
docker exec -i ops-postgres psql -U opsadmin -d opsdb < schema.sql
```

### 3. Importer le workflow n8n

1. Ouvrir n8n Cloud → Menu → Import Workflow
2. Sélectionner `n8n_workflow.json`
3. Configurer les credentials (Postgres, Slack, API token) dans n8n
4. Activer et exécuter

---

## Données mock

```json
// flights.json
{
  "flight_id": "LC123",
  "route": "ORY-EWR",
  "sched_dep_utc": "2026-01-10T10:00:00Z",
  "actual_dep_utc": "2026-01-10T10:42:00Z",
  "status": "departed"
}

// incidents.json
{
  "incident_id": "INC45",
  "flight_id": "LC123",
  "description": "Late baggage delivery, passenger unhappy",
  "severity": 3,
  "created_at_utc": "2026-01-10T11:10:00Z"
}
```

---

## API

| Endpoint | Description |
|---|---|
| `GET /ops/summary?date=YYYY-MM-DD` | Résumé opérationnel du jour |
| `POST /ai/analyze?flight_id=LC123` | Analyse IA des incidents d'un vol |
| `GET /health` | Health check (utilisé par Docker et AKS) |

Authentification : `Authorization: Bearer <token>`

Voir `api.md` pour les formats de réponse complets.

---

## Choix techniques clés

### Pourquoi les règles métier plutôt qu'un modèle ML ?

Pour un prototype sans dataset labellisé, les règles par mots-clés couvrent 70-80%
des cas courants instantanément, gratuitement, et de façon transparente.
Le LLM prend le relais pour les cas ambigus. Voir `ai_logic.md`.

### Pourquoi l'idempotence dans n8n ?

`ON CONFLICT DO NOTHING / DO UPDATE` garantit qu'on peut relancer le workflow
autant de fois qu'on veut sans créer de doublons en base.

### Pourquoi python:3.11-slim et non alpine ?

Alpine cause des problèmes de compilation avec `psycopg2` et `asyncpg` (musl vs glibc).
`slim` est le meilleur compromis taille/compatibilité.

---

## Sécurité

- Aucun secret dans le repo (tokens, mots de passe, clés API)
- Credentials stockés dans le gestionnaire n8n (chiffré AES-256)
- En production : Azure Key Vault + Managed Identity
- API protégée par Bearer Token + rate limiting (10 req/min)
- Conteneur Docker exécuté en utilisateur non-root

---

## Déploiement Azure (conceptuel)

| Composant | Service Azure |
|---|---|
| Postgres | Azure Database for PostgreSQL Flexible Server |
| API + n8n | Azure Kubernetes Service (AKS) |
| Images Docker | Azure Container Registry (ACR) |
| Secrets | Azure Key Vault |

Voir `azure_deployment.md` pour l'architecture complète et la stratégie de redéploiement.
