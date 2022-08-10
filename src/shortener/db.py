import abc
import dataclasses
import secrets
import string
from collections import defaultdict

import redis.asyncio as redis
import structlog
from yarl import URL

logger = structlog.get_logger()

SYMBOLS = string.digits + string.ascii_letters
SIZE = 5


@dataclasses.dataclass(frozen=True, kw_only=True)
class Record:
    short: str
    url: URL
    clicks: int


class AbstractDB(abc.ABC):
    @abc.abstractmethod
    async def close(self) -> None:
        pass

    @abc.abstractmethod
    async def register(self, url: URL) -> str:
        """Return a hash for registered long_url."""

    @abc.abstractmethod
    async def redirect(self, short: str) -> URL | None:
        """Return long url for registered short hash if present.

        Return None if a hash was not registered yet.

        Increment internal counter for requested short hash.
        The method should be used to redirecting only, not for getting statistical info.
        """

    @abc.abstractmethod
    async def latest(self) -> dict[str, Record]:
        """Return last 100 registered short hashes."""


def create_db(redis_url: str) -> AbstractDB:
    if not redis_url:
        return InMemoryDB()
    else:
        return RedisDB(redis_url)


def _gen_random() -> str:
    return "".join(secrets.choice(SYMBOLS) for i in range(SIZE))


class InMemoryDB(AbstractDB):
    # DB implementation for unittest purposes.

    def __init__(self) -> None:
        self._urls: dict[str, URL] = {}
        self._clicks: defaultdict[str, int] = defaultdict(int)

    async def close(self) -> None:
        pass

    async def register(self, url: URL) -> str:
        while True:
            short = _gen_random()
            if short not in self._urls:
                break
        self._urls[short] = url
        return short

    async def redirect(self, short: str) -> URL | None:
        url = self._urls.get(short)
        if url is not None:
            self._clicks[short] += 1
        return url

    async def latest(self) -> dict[str, Record]:
        shorts = []
        for pos, item in enumerate(self._urls.keys()):
            if pos >= 100:
                break
            shorts.append(item)
        return {
            short: Record(
                short=short,
                url=self._urls[short],
                clicks=self._clicks.get(short, 0),
            )
            for short in shorts
        }


class RedisDB(AbstractDB):
    def __init__(self, redis_url: str) -> None:
        logger.info("db.connect", url=redis_url)
        # plain Redis should be enough for the demo;
        # the battle deployent can use RedisCluster
        self._redis = redis.from_url(redis_url)

    async def close(self) -> None:
        logger.info("db.close")
        await self._redis.close()

    async def register(self, url: URL) -> str:
        while True:
            short = _gen_random()
            is_set = await self._redis.setnx(f"shorts:{{{short}}}", str(url))
            if is_set:
                logger.info("db.registered", short=short, url=url)
                break
            else:
                logger.debug("db.collision", short=short, url=url)
        await self._redis.lpush("latest.shorts", short)
        await self._redis.ltrim("latest.shorts", 0, 99)
        await self._redis.incr(f"clicks:{{{short}}}")
        return short

    async def redirect(self, short: str) -> URL | None:
        res = await self._redis.get(f"shorts:{{{short}}}")
        if res is not None:
            url = URL(res.decode("ascii"))
        else:
            url = None
        logger.info("db.get", short=short, url=url)
        return url

    async def latest(self) -> dict[str, Record]:
        shorts = [
            item.decode("ascii")
            for item in await self._redis.lrange("latest.shorts", 0, 99)
        ]
        short_keys = [f"shorts:{{{short}}}" for short in shorts]
        urls = [
            URL(item.decode("utf8") if item else "")
            for item in await self._redis.mget(short_keys)
        ]
        clicks_keys = [f"clicks:{{{short}}}" for short in shorts]
        counts = [
            int(item if item else 0) for item in await self._redis.mget(clicks_keys)
        ]
        return {
            short: Record(short=short, url=url, clicks=clicks)
            for short, url, clicks in zip(shorts, urls, counts)
        }
