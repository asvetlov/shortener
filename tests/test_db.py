from typing import AsyncIterator

import pytest
import pytest_asyncio
import redis
from yarl import URL

from shortener.db import Database, Record


@pytest_asyncio.fixture
async def db(redis_url: str) -> AsyncIterator[Database]:
    client = redis.from_url(redis_url)
    client.flushdb()
    ret = Database(redis_url)
    yield ret
    await ret.close()


async def test_redirect_doesnt_exist(db: Database) -> None:
    assert await db.redirect("not-exist") is None


async def test_latests_empty(db: Database) -> None:
    assert await db.latest() == {}


async def test_register(db: Database) -> None:
    short = await db.register(URL("https://google.com"))
    latests = await db.latest()
    assert latests == {
        short: Record(short=short, url=URL("https://google.com"), clicks=0)
    }


async def test_redirect(db: Database) -> None:
    short = await db.register(URL("https://google.com"))
    assert await db.redirect(short) == URL("https://google.com")
    latests = await db.latest()
    assert latests == {
        short: Record(short=short, url=URL("https://google.com"), clicks=1)
    }


async def test_smoke(db: Database) -> None:
    short1 = await db.register(URL("https://a.com"))
    short2 = await db.register(URL("https://b.com"))
    for i in range(3):
        assert await db.redirect(short1) == URL("https://a.com")
    for i in range(5):
        assert await db.redirect(short2) == URL("https://b.com")
    for i in range(7):
        assert await db.redirect("not-exists") is None
    latests = await db.latest()
    assert latests == {
        short1: Record(short=short1, url=URL("https://a.com"), clicks=3),
        short2: Record(short=short2, url=URL("https://b.com"), clicks=5),
    }
