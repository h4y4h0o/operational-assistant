import os
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Vérifie que le Bearer token est valide.
    Les tokens valides sont définis dans la variable d'environnement API_TOKENS
    (séparés par des virgules).
    """
    valid_tokens = [
        t.strip()
        for t in os.getenv("API_TOKENS", "dev-token-123").split(",")
        if t.strip()
    ]

    if credentials.credentials not in valid_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Invalid or missing Bearer token"}
        )

    return credentials.credentials
