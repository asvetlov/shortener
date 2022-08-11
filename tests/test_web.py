import re
from typing import AsyncIterator, Awaitable, Callable, cast

import pytest_asyncio
from aiohttp.test_utils import TestClient
from redis.asyncio import Redis

from shortener.config import Config
from shortener.db import Database
from shortener.web import init


@pytest_asyncio.fixture
async def client(
    redis_url: str,
    unused_tcp_port: int,
    aiohttp_client: Callable[..., Awaitable[TestClient]],
    redis_client: "Redis[str]",
) -> AsyncIterator[TestClient]:
    await redis_client.flushdb()
    cfg = Config(http_port=unused_tcp_port, redis_url=redis_url)
    app = await init(cfg)
    client = await aiohttp_client(app)
    yield client
    await app.cleanup()


async def test_index_empty(client: TestClient) -> None:
    async with await client.get("/", headers={"Accept": "application/json"}) as resp:
        assert resp.status == 200
        assert await resp.json() == {"added": None, "latest": []}


async def test_register(client: TestClient, redis_client: "Redis[str]") -> None:
    assert client.app is not None
    db = cast(Database, client.app["db"])
    async with client.post(
        "/", data={"url": "https://google.com"}, allow_redirects=False
    ) as resp:
        assert resp.status == 303
        match = re.match(
            r"/\?added_short=(?P<short>[0-9a-zA-Z]{5})&added_url=https://google\.com",
            resp.headers["Location"],
        )
        assert match is not None
        short = match.group("short")
    async with await client.get(
        resp.headers["Location"], headers={"Accept": "application/json"}
    ) as resp:
        assert resp.status == 200
        assert await resp.json() == {
            "added": {
                "caption": f"/{short}",
                "href": f"/{short}",
                "url": "https://google.com",
            },
            "latest": [{"clicks": 0, "short": short, "url": "https://google.com"}],
        }


async def test_redirect(client: TestClient, redis_client: "Redis[str]") -> None:
    assert client.app is not None
    db = cast(Database, client.app["db"])
    async with client.post(
        "/",
        data={"url": "https://example.com"},
        allow_redirects=False,
    ) as resp:
        assert resp.status == 303
        match = re.match(
            r"/\?added_short=(?P<short>[0-9a-zA-Z]{5})&added_url=https://example\.com",
            resp.headers["Location"],
        )
        assert match is not None
        short = match.group("short")
    async with await client.get(
        f"/{short}",
        allow_redirects=False,
    ) as resp:
        assert resp.status == 303
        assert resp.headers["Location"] == "https://example.com"

    async with await client.get("/", headers={"Accept": "application/json"}) as resp:
        assert resp.status == 200
        assert await resp.json() == {
            "added": None,
            "latest": [{"clicks": 1, "short": short, "url": "https://example.com"}],
        }


async def test_redirect_doesnt_exists(client: TestClient) -> None:
    async with await client.get(
        "/12345",
        allow_redirects=False,
    ) as resp:
        assert resp.status == 404
