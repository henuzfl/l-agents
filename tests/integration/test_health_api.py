import httpx
import pytest


@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "enterprise-agent"}


@pytest.mark.asyncio
async def test_chat_page_is_server_rendered(client: httpx.AsyncClient) -> None:
    class WebAuth:
        async def validate_refresh(self, _token: str) -> None:
            return None

    app = client._transport.app  # type: ignore[attr-defined]
    app.state.container.auth_service = WebAuth()
    client.cookies.set("refresh_token", "test")
    response = await client.get("/")
    assert response.status_code == 200
    assert "Agent Desk" in response.text
    assert "/static/markdown.css" in response.text
    assert "/static/trace.css" in response.text
    assert "app/static" not in response.text


@pytest.mark.asyncio
async def test_protected_page_redirects_to_login(client: httpx.AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_page_is_public(client: httpx.AsyncClient) -> None:
    response = await client.get("/login")
    assert response.status_code == 200
    assert "loginForm" in response.text
