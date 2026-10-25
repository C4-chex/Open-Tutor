"""JWT token creation and verification."""

from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.serialization import load_pem_private_key
import jwt
from jwt.exceptions import InvalidTokenError as JWTError

from config import settings

__all__ = ["JWTError", "create_access_token", "create_refresh_token", "decode_token"]


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "type": "access", "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises JWTError on invalid/expired."""
    key = settings.jwt_secret_key
    # Existing RSA deployments use the same PEM private key for signing and
    # verification. PyJWT needs its public component when verifying RSA tokens.
    if settings.jwt_algorithm in {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512"}:
        if key.lstrip().startswith(("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----")):
            key = load_pem_private_key(key.encode(), password=None).public_key()
    return jwt.decode(token, key, algorithms=[settings.jwt_algorithm])
