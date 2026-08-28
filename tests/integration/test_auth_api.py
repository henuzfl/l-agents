import httpx
import pytest

from app.api.dependencies import get_auth_service


class FakeAuthService:
    access_token_seconds = 900
    refresh_token_seconds = 604800
    secure_cookie = False

    async def login(self, username: str, password: str) -> tuple[str, str]:
        assert (username, password) == ("demo1", "password")
        return "access-token", "refresh-token"

    async def refresh(self, token: str) -> tuple[str, str]:
        assert token == "refresh-token"
        return "next-access", "next-refresh"

    async def logout(self, token: str | None) -> None:
        assert token in {"refresh-token", "next-refresh"}


@pytest.mark.asyncio
async def test_login_sets_http_only_refresh_cookie(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "demo1", "password": "password"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access-token",
        "token_type": "bearer",
        "expires_in": 900,
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie


@pytest.mark.asyncio
async def test_refresh_rotates_cookie_and_logout_clears_it(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    client.cookies.set("refresh_token", "refresh-token", path="/")
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] == "next-access"
    assert "next-refresh" in refreshed.headers["set-cookie"]

    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204
    assert "Max-Age=0" in logged_out.headers["set-cookie"]
