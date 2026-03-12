import os
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()


def _load_tokens() -> list[str]:
    """
    Charge les tokens depuis la variable d'environnement API_TOKENS.
    Lève une erreur au démarrage si la variable est absente ou vide.
    """
    raw = os.getenv("API_TOKENS", "").strip()
    if not raw:
        raise RuntimeError(
            "API_TOKENS environment variable is not set. "
            "Define it as a comma-separated list of Bearer tokens."
        )
    return [t.strip() for t in raw.split(",") if t.strip()]


# Chargé une seule fois au démarrage — erreur immédiate si manquant
VALID_TOKENS = _load_tokens()


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Vérifie que le Bearer token est valide.
    Les tokens valides sont définis dans la variable d'environnement API_TOKENS
    (séparés par des virgules).
    """
    if credentials.credentials not in VALID_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Invalid or missing Bearer token"}
        )

    return credentials.credentials
