# Schéma du Workflow n8n

## Diagramme des nodes

```
┌─────────────────┐
│  1. Manual      │  ← Déclencheur manuel (ou Cron "0 6 * * *" pour 6h du matin)
│     Trigger     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  2. Load JSON               │  ← HTTP GET vers endpoint mock
│     (flights + incidents)   │     Retourne: { flights:[...], incidents:[...] }
└──────┬──────────────────────┘
       │
       ├─────────────────────────────────────┐
       │                                     │
       ▼                                     ▼
┌──────────────────┐               ┌──────────────────────┐
│  3. Upsert       │               │  4. Upsert           │
│     Flights      │               │     Incidents        │
│     → Postgres   │               │     → Postgres       │
│                  │               │                      │
│  ON CONFLICT     │               │  ON CONFLICT         │
│  flight_id       │               │  incident_id         │
│  DO UPDATE       │               │  DO NOTHING          │
└──────────────────┘               └──────────┬───────────┘
                                              │
                                              ▼
                                   ┌──────────────────────┐
                                   │  5. POST             │
                                   │     /ai/analyze      │
                                   │     API              │
                                   │                      │
                                   │  Auth: Bearer Token  │
                                   │  Body: incident data │
                                   └──────────┬───────────┘
                                              │
                                   ┌──────────┴───────────┐
                              succès                   échec
                                   │                       │
                                   ▼                       ▼
                         ┌──────────────────┐   ┌─────────────────────┐
                         │  6. Slack Alert  │   │  6b. Slack Error    │
                         │                  │   │      "IA indispo,   │
                         │  #ops-alerts     │   │       revue manuelle│
                         │  Résumé complet  │   │       requise"      │
                         └──────────────────┘   └─────────────────────┘
```

## Pseudo-nodes (format liste)

| # | Node | Type n8n | Action |
|---|------|----------|--------|
| 1 | Manual Trigger | `manualTrigger` | Lance le pipeline à la demande |
| 2 | Load JSON | `httpRequest` (GET) | Charge les données vols/incidents |
| 3 | Upsert Flights | `postgres` | INSERT ON CONFLICT DO UPDATE |
| 4 | Upsert Incidents | `postgres` | INSERT ON CONFLICT DO NOTHING |
| 5 | Call AI API | `httpRequest` (POST) | POST /ai/analyze avec Bearer token |
| 6 | Send Slack | `slack` | Message formaté sur #ops-alerts |

## Réponses aux questions

### Comment garantissez-vous l'idempotence ?

**Définition simple :** Exécuter le workflow 5 fois = même résultat qu'une fois.

On utilise `ON CONFLICT` dans les requêtes SQL :
- Vols : `ON CONFLICT (flight_id) DO UPDATE` → met à jour le statut si le vol existe déjà
- Incidents : `ON CONFLICT (incident_id) DO NOTHING` → ignore les doublons (un incident ne change pas)
- ai_insights : la table a `UNIQUE` sur `incident_id` → une seule analyse par incident

### Que se passe-t-il si Slack est indisponible ?

**Configuration :** Le node Slack a `onError: continueErrorOutput`

1. n8n continue l'exécution sans planter
2. L'erreur est loggée dans l'historique d'exécution n8n
3. Un node de fallback envoie une alerte par email (ou log dans Postgres)
4. L'administrateur peut **re-jouer l'exécution** depuis l'UI n8n
5. En production : ajouter un node "Wait 60s → Retry x3" avant Slack

### Où stockez-vous les secrets n8n ?

| Secret | Stockage |
|--------|----------|
| Token Slack | Credential n8n "Slack OAuth" (chiffré AES-256) |
| Password Postgres | Credential n8n "Postgres" (chiffré) |
| Bearer Token API | Credential n8n "Header Auth" (chiffré) |
| Clé LLM (OpenAI/Claude) | Variable d'environnement `N8N_ENCRYPTION_KEY` |

**Règle absolue :** Aucun secret n'apparaît en clair dans le JSON du workflow exporté.
Les credentials sont référencés par leur ID, pas leur valeur.
