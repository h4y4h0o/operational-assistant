-- =============================================================
-- REQUÊTES SQL — Assistant Opérationnel
-- =============================================================


-- -------------------------------------------------------------
-- REQUÊTE 1 : Vols avec un retard supérieur à 30 minutes
-- -------------------------------------------------------------
-- Logique : retard = actual_dep_utc - sched_dep_utc
-- On ne garde que les vols où cette différence dépasse 30 min
-- actual_dep_utc peut être NULL (vol pas encore parti) → on les exclut
-- -------------------------------------------------------------
SELECT
    flight_id,
    route,
    sched_dep_utc,
    actual_dep_utc,
    EXTRACT(EPOCH FROM (actual_dep_utc - sched_dep_utc)) / 60 AS delay_minutes,
    status
FROM flights
WHERE actual_dep_utc IS NOT NULL
  AND actual_dep_utc - sched_dep_utc > INTERVAL '30 minutes'
ORDER BY delay_minutes DESC;


-- -------------------------------------------------------------
-- REQUÊTE 2 : Nombre d'incidents par route + sévérité moyenne
-- -------------------------------------------------------------
-- Logique : on joint incidents → flights pour récupérer la route
-- On groupe par route et on calcule les agrégats
-- -------------------------------------------------------------
SELECT
    f.route,
    COUNT(i.incident_id)        AS total_incidents,
    ROUND(AVG(i.severity), 2)   AS avg_severity,
    MAX(i.severity)             AS max_severity
FROM flights f
JOIN incidents i ON i.flight_id = f.flight_id
GROUP BY f.route
ORDER BY avg_severity DESC, total_incidents DESC;


-- =============================================================
-- RÉPONSE À LA QUESTION : Pourquoi ces index ?
-- =============================================================
--
-- idx_flights_route :
--   La requête 2 fait un GROUP BY f.route après un JOIN.
--   Sans index, Postgres scanne toute la table flights pour chaque groupe.
--   Avec l'index, il accède directement aux lignes d'une route donnée.
--
-- idx_flights_sched_dep :
--   L'API GET /ops/summary?date=YYYY-MM-DD filtre sur la date de départ.
--   Un index sur ce champ évite un full scan à chaque appel API.
--
-- idx_incidents_flight_id :
--   Le JOIN incidents → flights utilise ce champ comme clé de jointure.
--   C'est l'index le plus critique : sans lui, chaque JOIN = scan complet.
--
-- idx_incidents_severity :
--   Pour les alertes (severity >= 4), cet index permet un accès direct.
--
-- Si la volumétrie est multipliée par 100 :
--   - Les index deviennent indispensables (sans eux, les requêtes passent
--     de quelques ms à plusieurs secondes)
--   - Il faudrait envisager le partitionnement de la table flights par mois
--     (PARTITION BY RANGE sur sched_dep_utc)
--   - Un index partiel sur les vols en retard serait pertinent :
--     CREATE INDEX idx_delayed ON flights(actual_dep_utc)
--     WHERE actual_dep_utc - sched_dep_utc > INTERVAL '30 minutes';
--   - Pour ai_insights, une stratégie d'archivage des vieilles analyses
--     serait nécessaire pour garder des performances correctes
-- =============================================================
