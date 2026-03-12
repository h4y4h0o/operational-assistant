# CHATGPT_LOG.md — Journal d'utilisation de l'IA

> Outils utilisés : Claude (Anthropic) et CHATGPT
> Ce journal documente quelques-uns des prompts réellement utilisés, ce qui a bien fonctionné,
> ce qui a été corrigé, et les décisions où je n'ai PAS suivi l'IA.

-----------
## Prompt 1

**Prompt envoyé :**

```
Dans mon workflow n8n, est-ce une bonne idee de parralleliser le chargement de données et leur stockage dans postgres pour flights et incendies?
```

**Réponse de l'IA :**
```
Ces deux opérations sont **totalement indépendantes** — il n'existe aucune
relation entre le chargement des vols et le chargement des incidents à ce
stade. Les exécuter en parallèle réduit le temps d'exécution de ~2s à ~1s.

Le node **Merge (Append)** garantit que les deux branches sont terminées
avant de passer à l'analyse IA — évitant ainsi les erreurs de clé étrangère
(un incident référence un flight_id qui doit exister en base).
```

**Pourquoi je n'ai pas suivi l'IA:**
- En raison du "foreign key constraint" (flight_id), ce parallélisme est incorecte, et il faut d'abord rajouter les flights ensuite les incendits.

-----------
## Prompt 2

**Prompt envoyé :**

```
Is it good approach to index on datetime column:

CREATE TABLE flights (
    flight_id       VARCHAR(20)  PRIMARY KEY,          -- ex: "LC123" — identifiant unique du vol
    route           VARCHAR(20)  NOT NULL,              -- ex: "ORY-EWR" — aéroport départ - arrivée
    sched_dep_utc   TIMESTAMPTZ  NOT NULL,              -- heure de départ prévue (UTC)
    actual_dep_utc  TIMESTAMPTZ,                        -- heure de départ réelle (NULL si pas encore parti)
    status          VARCHAR(30)  NOT NULL               -- ex: "departed", "delayed", "cancelled"
);

CREATE INDEX idx_flights_route ON flights(route);
CREATE INDEX idx_flights_sched_dep ON flights(sched_dep_utc);
```

**Ce que l'IA a bien fait :**

- Description de quand l'indexing d'un datetime est bénéfique,
- Et qu'il est important d'éviter les DATE() sur la colonne. (Cela a permis de corriger une query dans lequel l'IA avait préalablement caster avec DATE()).


-----------
## Prompt 3
**Prompt envoyé :**
```
Dans n8n, quelle est la meilleure façon d'envoyer un message/alert Slack?
```

**Réponse de l'IA :**
```
La façon la plus simple est d'utiliser un Incoming Webhook Slack — pas besoin
  de configurer OAuth.

  ---
  Étape 1 — Créer un Incoming Webhook Slack

  1. Va sur https://api.slack.com/apps
  2. Clique "Create New App" → "From scratch"
  3. Nom : Ops Assistant → sélectionne ton workspace → Create App
  4. Dans le menu gauche → "Incoming Webhooks"
  5. Active le toggle "Activate Incoming Webhooks"
  6. Clique "Add New Webhook to Workspace"
  7. Sélectionne un channel (ex: #general ou crée #ops-alerts)
  8. Clique Allow
  9. Copie l'URL qui ressemble à :
  https://hooks.slack.com/services/T.../B.../...

  ---
  Étape 2 — Configurer dans n8n

  Supprime l'ancien node Slack et ajoute un node HTTP Request :

  ┌───────────┬───────────────────────┐
  │   Champ   │        Valeur         │
  ├───────────┼───────────────────────┤
  │ Method    │ POST                  │
  ├───────────┼───────────────────────┤
  │ URL       │ ton_webhook_url_slack │
  ├───────────┼───────────────────────┤
  │ Body Type │ JSON                  │
  └───────────┴───────────────────────┘

  JSON Body :
  {
    "text": "*[OPS ALERT]* Rapport du 2026-01-10\n*Vols analysés :* 
  3\n*Incidents :* 3\n*Vols en retard :* LC123 (+42 min)\n*Analyse IA disponible
   sur :* http://localhost:8000/ops/summary?date=2026-01-10"
  }

  ---
  Teste avec "Test step" — tu dois recevoir le message dans ton channel Slack !
  ```

**Pourquoi je n'ai pas suivi l:IA:**
J'ai trouvé qu'utiliser le node "Slack (send message)" de n8n était plus simple. Surtout que dans l'approche proposé par l'IA, des informations secrètes sont lisible dans le webhook_url_slack, entrées directement dans les paramètres du node, ce qui n'est pas secure.


-----------
## Prompt 4
**Prompt envoyé :**
```
Que se passe-t-il si la volumétrie est multipliée par 100 ?
```

**Ce que l'IA a bien fait :**
```
Si la volumétrie est multipliée par 100 :
   - Les index deviennent indispensables (sans eux, les requêtes passent
     de quelques ms à plusieurs secondes)
   - Il faudrait envisager le partitionnement de la table flights par mois
     (PARTITION BY RANGE sur sched_dep_utc)
   - Pour ai_insights, une stratégie d'archivage des vieilles analyses
     serait nécessaire pour garder des performances correctes
```

**Ce que l'IA n'a pas bien fait :**
```
 - Un index partiel sur les vols en retard serait pertinent :
     CREATE INDEX idx_delayed ON flights(actual_dep_utc)
     WHERE actual_dep_utc - sched_dep_utc > INTERVAL '30 minutes';
```
Ceci n'est pas correcte car on utilise l'index a d'autre endroit (API Get by date).


-----------
## Prompt 5
**Prompt envoyé :**
```
Dans n8n, que se passe-t-il si Slack est indisponible ?
```

**Ce que l'IA a bien fait :**
```
Le node Slack a `onError: continueErrorOutput` :
1. n8n continue l'exécution sans planter
2. L'erreur est loggée dans l'historique d'exécution n8n
3. L'administrateur peut **re-jouer l'exécution** depuis l'UI n8n
4. En production : ajouter un node "Wait 60s → Retry x3" avant Slack
```

**Ce qui a été vérifié/ajouté :**
```
 - activer l'option `Retry on fail` du node Slack.
```
