# =============================================================
# Dockerfile — API Opérationnel Vols & Incidents
# Base : Python 3.11 slim (image légère, sans outils inutiles)
# =============================================================

# --- ÉTAPE 1 : Image de base ---
# "python:3.11-slim" = Python officiel sans les extras (moins de failles de sécurité)
# On évite "python:3.11" (trop lourd) et "python:3.11-alpine" (problèmes de compatibilité)
FROM python:3.11-slim

# --- ÉTAPE 2 : Métadonnées ---
LABEL maintainer="ops-team"
LABEL description="API FastAPI pour l'assistant opérationnel vols & incidents"
LABEL version="1.0.0"

# --- ÉTAPE 3 : Variables d'environnement ---
# PYTHONDONTWRITEBYTECODE : n'écrit pas les fichiers .pyc (inutiles en conteneur)
# PYTHONUNBUFFERED : les logs apparaissent immédiatement (pas de buffer)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# --- ÉTAPE 4 : Répertoire de travail dans le conteneur ---
# Toutes les commandes suivantes s'exécutent depuis /app
WORKDIR /app

# --- ÉTAPE 5 : Installer les dépendances système minimales ---
# libpq-dev : nécessaire pour psycopg2 (driver Postgres)
# gcc : compilateur requis pour certains packages Python
# On nettoie le cache apt pour garder l'image légère
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- ÉTAPE 6 : Copier et installer les dépendances Python ---
# On copie SEULEMENT requirements.txt d'abord (optimisation cache Docker)
# Si le code change mais pas les dépendances, Docker réutilise le cache de cette étape
COPY api/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- ÉTAPE 7 : Copier le code source ---
# On copie APRÈS les dépendances pour maximiser l'utilisation du cache
COPY api/ .

# --- ÉTAPE 8 : Sécurité — utilisateur non-root ---
# Par défaut Docker tourne en root (dangereux). On crée un utilisateur dédié.
RUN adduser --disabled-password --gecos "" appuser
USER appuser

# --- ÉTAPE 9 : Port exposé ---
# Documentation : indique que le conteneur écoute sur ce port
# (à mapper avec -p 8000:8000 au lancement)
EXPOSE 8000

# --- ÉTAPE 10 : Health check ---
# Docker vérifie toutes les 30s que l'API répond correctement
# Si elle ne répond pas 3 fois → conteneur marqué "unhealthy"
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# --- ÉTAPE 11 : Commande de démarrage ---
# uvicorn : serveur ASGI pour FastAPI
# --host 0.0.0.0 : écoute sur toutes les interfaces réseau (obligatoire en conteneur)
# --workers 2 : 2 processus parallèles (adapter selon les ressources)
# --no-access-log : les logs d'accès sont gérés par Azure Application Insights
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
