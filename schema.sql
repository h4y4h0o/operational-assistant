-- =============================================================
-- SCHÉMA POSTGRES — Assistant Opérationnel Vols & Incidents
-- =============================================================

-- -------------------------------------------------------------
-- TABLE 1 : flights
-- Stocke les données de chaque vol (réel ou prévu)
-- -------------------------------------------------------------
CREATE TABLE flights (
    flight_id       VARCHAR(20)  PRIMARY KEY,          -- ex: "LC123" — identifiant unique du vol
    route           VARCHAR(20)  NOT NULL,              -- ex: "ORY-EWR" — aéroport départ - arrivée
    sched_dep_utc   TIMESTAMPTZ  NOT NULL,              -- heure de départ prévue (UTC)
    actual_dep_utc  TIMESTAMPTZ,                        -- heure de départ réelle (NULL si pas encore parti)
    status          VARCHAR(30)  NOT NULL               -- ex: "departed", "delayed", "cancelled"
);

-- Index sur la route : on filtre et groupe souvent par route
CREATE INDEX idx_flights_route ON flights(route);

-- Index sur la date de départ prévue : les requêtes "vols du jour" sont fréquentes
CREATE INDEX idx_flights_sched_dep ON flights(sched_dep_utc);


-- -------------------------------------------------------------
-- TABLE 2 : incidents
-- Stocke les incidents signalés, toujours liés à un vol
-- -------------------------------------------------------------
CREATE TABLE incidents (
    incident_id     VARCHAR(20)  PRIMARY KEY,           -- ex: "INC45"
    flight_id       VARCHAR(20)  NOT NULL               -- référence au vol concerné
                    REFERENCES flights(flight_id)
                    ON DELETE CASCADE,                  -- si le vol est supprimé, ses incidents aussi
    description     TEXT         NOT NULL,              -- texte libre décrivant l'incident
    severity        SMALLINT     NOT NULL               -- niveau de gravité (ex: 1 à 5)
                    CHECK (severity BETWEEN 1 AND 5),
    created_at_utc  TIMESTAMPTZ  NOT NULL DEFAULT NOW() -- horodatage de création
);

-- Index sur flight_id : on cherche souvent "tous les incidents d'un vol"
CREATE INDEX idx_incidents_flight_id ON incidents(flight_id);

-- Index sur severity : pour filtrer les incidents critiques rapidement
CREATE INDEX idx_incidents_severity ON incidents(severity);


-- -------------------------------------------------------------
-- TABLE 3 : ai_insights
-- Stocke les résultats de l'analyse IA pour chaque incident
-- -------------------------------------------------------------
CREATE TABLE ai_insights (
    id                  SERIAL       PRIMARY KEY,        -- auto-incrémenté
    incident_id         VARCHAR(20)  NOT NULL UNIQUE     -- 1 analyse max par incident
                        REFERENCES incidents(incident_id)
                        ON DELETE CASCADE,
    normalized_category VARCHAR(50)  NOT NULL,           -- catégorie normalisée (ex: "baggage", "delay")
    ops_summary         TEXT         NOT NULL,           -- résumé opérationnel court
    recommended_action  TEXT         NOT NULL,           -- action recommandée par l'IA
    confidence_score    NUMERIC(3,2) NOT NULL            -- score de confiance entre 0.00 et 1.00
                        CHECK (confidence_score BETWEEN 0 AND 1),
    analyzed_at_utc     TIMESTAMPTZ  NOT NULL DEFAULT NOW() -- quand l'analyse a été faite
);
