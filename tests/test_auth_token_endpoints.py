"""Exercise JWT validation through HTTP, including error-to-401 translation."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from database import get_db
from routers.auth import router
from services.auth import dependency, jwt as token_service


SECRET = "opentutor-test-secret-at-least-32-bytes"  # pragma: allowlist secret
USER_ID = str(uuid.UUID(int=42))


def signed_token(claims, *, algorithm="HS256", secret=SECRET):
    """Create an independent HS256 fixture without using the JWT backend."""
    def segment(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    message = segment({"alg": algorithm, "typ": "JWT"}) + b"." + segment(claims)
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), message, hashlib.sha256).digest()
    ).rstrip(b"=")
    return (message + b"." + signature).decode()


@pytest_asyncio.fixture
async def auth_client(monkeypatch):
    settings = SimpleNamespace(
        auth_enabled=True,
        deployment_mode="multi_user",
        jwt_secret_key=SECRET,
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
    )
    monkeypatch.setattr(dependency, "settings", settings)
    monkeypatch.setattr(token_service, "settings", settings)

    user = SimpleNamespace(id=uuid.UUID(USER_ID), is_active=True)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = result

    async def override_db():
        yield db

    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_db] = override_db

    @app.get("/private")
    async def private(current_user=Depends(dependency.get_current_user)):
        return {"user_id": str(current_user.id)}

    # Unhandled validation exceptions become observable HTTP 500s.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["expired", "signature", "malformed", "algorithm"])
async def test_invalid_access_token_returns_401(auth_client, invalid_kind):
    client, db = auth_client
    claims = {"sub": USER_ID, "type": "access", "exp": int(time.time()) + 600}
    if invalid_kind == "expired":
        claims["exp"] = int(time.time()) - 60
        token = signed_token(claims)
    elif invalid_kind == "signature":
        token = signed_token(claims, secret="different-test-secret-at-least-32-bytes")
    elif invalid_kind == "algorithm":
        token = signed_token(claims, algorithm="none")
    else:
        token = "not.a.valid.jwt"

    response = await client.get("/private", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Invalid or expired token"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_access_token_reaches_current_user(auth_client):
    client, db = auth_client
    token = token_service.create_access_token(USER_ID)
    response = await client.get("/private", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"user_id": USER_ID}
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_token_cannot_access_protected_endpoint(auth_client):
    client, db = auth_client
    token = token_service.create_refresh_token(USER_ID)
    response = await client.get("/private", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token type"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("token_kind", ["expired", "malformed", "access"])
async def test_invalid_refresh_token_returns_401(auth_client, token_kind):
    client, db = auth_client
    token = {
        "expired": signed_token({"sub": USER_ID, "type": "refresh", "exp": int(time.time()) - 60}),
        "malformed": "not.a.valid.jwt",
        "access": token_service.create_access_token(USER_ID),
    }[token_kind]
    response = await client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_refresh_issues_usable_access_token(auth_client):
    client, _ = auth_client
    response = await client.post(
        "/auth/refresh", json={"refresh_token": token_service.create_refresh_token(USER_ID)}
    )
    assert response.status_code == 200
    tokens = response.json()
    assert token_service.decode_token(tokens["refresh_token"])["type"] == "refresh"
    response = await client.get("/private", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200
