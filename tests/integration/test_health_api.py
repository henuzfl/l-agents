import httpx
import pytest


@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "enterprise-agent"}


@pytest.mark.asyncio
async def test_chat_page_is_server_rendered(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "Agent Desk" in response.text
    assert "app/static" not in response.text
