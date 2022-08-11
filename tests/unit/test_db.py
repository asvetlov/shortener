import pytest
import pytest_asyncio
import redis
from yarl import URL

from shortener.db import Database, Record


@pytest_asyncio.fixture
async def db(redis_url):
    client = redis.from_url(redis_url)
    client.flushdb()
    ret = Database(redis_url)
    yield ret
    await ret.close()


async def test_redirect_doesnt_exist(db):
    assert await db.redirect("not-exist") is None


async def test_latests_empty(db):
    assert await db.latest() == {}


async def test_register(db):
    short = await db.register("https://google.com")
    latests = await db.latest()
    assert latests == {
        short: Record(short=short, url=URL("https://google.com"), clicks=0)
    }


async def test_redirect(db):
    short = await db.register("https://google.com")
    assert await db.redirect(short) == URL("https://google.com")
    latests = await db.latest()
    assert latests == {
        short: Record(short=short, url=URL("https://google.com"), clicks=1)
    }
