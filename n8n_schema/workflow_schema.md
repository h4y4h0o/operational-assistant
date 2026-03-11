# Schéma du Workflow n8n

## Screenshot du workflow réel

![Workflow n8n](../screenshots/n8n_workflow.png)

---

## Diagramme des nodes

```
┌──────────────────┐
│  1. Manual       │  ← Déclencheur manuel
│     Trigger      │     (remplaçable par Cron "0 6 * * *" pour 6h du matin)
└────────┬─────────┘
         │
         ├─────────────────────────────────────────────┐
         │                                             │
         ▼                                             ▼
┌─────────────────────────┐               ┌─────────────────────────┐
│  2. HTTP Request        │               │  3. HTTP Request        │
│     flights.json        │               │     incidents.json      │
│                         │               │                         │
│  GET localhost:8080/    │               │  GET localhost:8080/    │
│  data/flights.json      │               │  data/incidents.json    │
└──────────┬──────────────┘               └──────────┬──────────────┘
           │                                         │
           ▼                                         ▼
┌─────────────────────────┐               ┌─────────────────────────┐
│  4. Upsert Flights      │               │  5. Upsert Incidents    │
│     → Postgres          │               │     → Postgres          │
│                         │               │                         │
│  ON CONFLICT (flight_id)│               │  ON CONFLICT            │
│  DO UPDATE              │               │  (incident_id)          │
│                         │               │  DO NOTHING             │
└──────────┬──────────────┘               └──────────┬──────────────┘
           │                                         │
           └──────────────────┬──────────────────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │  6. Merge            │  ← Attend la fin des 2 branches
                   │     (Append mode)    │     avant de continuer
                   └──────────┬───────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │  7. POST             │  ← Appel FastAPI
                   │     /ai/analyze      │     Auth: Bearer dev-token-123
                   │                      │     → Groq LLM analyse incidents
                   │  flight_id: LC123    │     → Stocke dans ai_insights
                   └──────────┬───────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │  8. GET              │  ← Résumé complet du jour
                   │     /ops/summary     │     inclut insights IA
                   │     ?date=2026-01-10 │
                   └──────────┬───────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │  9. Code             │  ← Construit le message Slack
                   │     Build message    │     depuis les réponses API
                   └──────────┬───────────┘
                              │
                   ┌──────────┴───────────┐
              succès                   échec
                   │                       │
                   ▼                       ▼
        ┌──────────────────┐   ┌──────────────────────┐
        │  10. Slack       │   │  10b. Slack Error    │
        │  "Send a message"│   │  "IA indispo,        │
        │  #ops-alerts     │   │   revue manuelle"    │
        │  Bot Token Auth  │   │                      │
        └──────────────────┘   └──────────────────────┘
```

---

## Tableau des nodes

| # | Node | Type n8n | Action |
|---|------|----------|--------|
| 1 | Manual Trigger | `manualTrigger` | Lance le pipeline à la demande |
| 2 | HTTP Request (flights) | `httpRequest` GET | Charge flights.json via serveur Python local |
| 3 | HTTP Request (incidents) | `httpRequest` GET | Charge incidents.json via serveur Python local |
| 4 | Upsert Flights | `postgres` Execute Query | INSERT ON CONFLICT DO UPDATE |
| 5 | Upsert Incidents | `postgres` Execute Query | INSERT ON CONFLICT DO NOTHING |
| 6 | Merge | `merge` Append | Attend la fin des 2 branches parallèles |
| 7 | Call AI Analyze | `httpRequest` POST | POST /ai/analyze → Groq LLM → ai_insights |
| 8 | Get Summary | `httpRequest` GET | GET /ops/summary?date=2026-01-10 |
| 9 | Build Slack Message | `code` | Construit le message dynamique depuis les réponses API |
| 10 | Send a message | `slack` v2.4 | Envoie via Bot Token sur #ops-alerts |

---

## Justification du nombre de nodes

Le cahier des charges suggère 4-6 nodes. Notre workflow en compte 10 pour
des raisons architecturales justifiées (voir README.md). En résumé :

- **Nodes 2-6** : parallélisation du chargement → temps divisé par 2
- **Nodes 7-8** : séquentiels obligatoires (AI écrit, Summary lit)
- **Node 9** : séparation claire de la logique de présentation
- **Node 10** : Slack natif, plus sécurisé qu'un Incoming Webhook

---

## Réponses aux questions du cahier des charges

### Comment garantissez-vous l'idempotence ?

**Définition :** Exécuter le workflow 5 fois = même résultat qu'une seule fois.

On utilise `ON CONFLICT` dans les requêtes SQL :
- Vols : `ON CONFLICT (flight_id) DO UPDATE` → met à jour le statut si le vol existe déjà
- Incidents : `ON CONFLICT (incident_id) DO NOTHING` → ignore les doublons (un incident ne change pas)
- ai_insights : contrainte `UNIQUE` sur `incident_id` → une seule analyse par incident

### Que se passe-t-il si Slack est indisponible ?

Le node Slack a `onError: continueErrorOutput` :

1. n8n continue l'exécution sans planter
2. L'erreur est loggée dans l'historique d'exécution n8n
3. L'administrateur peut **re-jouer l'exécution** depuis l'UI n8n
4. En production : ajouter un node "Wait 60s → Retry x3" avant Slack

### Où stockez-vous les secrets n8n ?

| Secret | Stockage |
|--------|----------|
| Bot Token Slack (`xoxb-...`) | Credential n8n "Slack Access Token" (chiffré AES-256) |
| Password Postgres | Credential n8n "Postgres" (chiffré AES-256) |
| Bearer Token API | Header `Authorization` en valeur fixe (à migrer en credential) |
| Clé Groq (`gsk_...`) | Variable d'environnement Docker (`GROQ_API_KEY`) |

**Règle absolue :** Aucun secret n'apparaît en clair dans le JSON du workflow exporté.
Les credentials sont référencés par leur ID chiffré, jamais par leur valeur.

### Pourquoi les branches flights et incidents sont-elles parallèles ?

Ces deux opérations sont **totalement indépendantes** — il n'existe aucune
relation entre le chargement des vols et le chargement des incidents à ce
stade. Les exécuter en parallèle réduit le temps d'exécution de ~2s à ~1s.

Le node **Merge (Append)** garantit que les deux branches sont terminées
avant de passer à l'analyse IA — évitant ainsi les erreurs de clé étrangère
(un incident référence un flight_id qui doit exister en base).

### Pourquoi POST /ai/analyze et GET /ops/summary sont-ils séquentiels ?

`POST /ai/analyze` écrit les résultats dans la table `ai_insights`.
`GET /ops/summary` lit depuis `ai_insights` via un LEFT JOIN.

Les paralléliser retournerait `null` pour `normalized_category` et
`ops_summary` dans le résumé — les données n'étant pas encore écrites.
