import abc
import secrets
import string

import redis.asyncio as redis
import structlog
from yarl import URL

logger = structlog.get_logger()

SYMBOLS = string.digits + string.ascii_letters
SIZE = 5


class AbstractDB(abc.ABC):
    @abc.abstractmethod
    async def close(self) -> None:
        pass

    @abc.abstractmethod
    async def register(self, url: URL) -> str:
        """Return a hash for registered long_url."""

    @abc.abstractmethod
    async def get(self, short: str) -> URL | None:
        """Return long url for registered short hash if present.

        Return None if a hash was not registered yet.
        """

    @abc.abstractmethod
    async def latest(self) -> list[str]:
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
        self._db: dict[str, URL] = {}

    async def close(self) -> None:
        pass

    async def register(self, url: URL) -> str:
        while True:
            short = _gen_random()
            if short not in self._db:
                break
        self._db[short] = url
        return short

    async def get(self, short: str) -> URL | None:
        return self._db.get(short)

    async def latest(self) -> list[str]:
        ret = []
        for pos, item in enumerate(self._db.keys()):
            if pos >= 100:
                break
            ret.append(item)
        return ret


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
            is_set = await self._redis.setnx(f"shorts:{short}", str(url))
            if is_set:
                logger.info("db.registered", short=short, url=url)
                break
            else:
                logger.debug("db.collision", short=short, url=url)
        await self._redis.lpush("latest.shorts", short)
        await self._redis.ltrim("latest.shorts", 0, 99)
        return short

    async def get(self, short: str) -> URL | None:
        res = await self._redis.get(f"shorts:{short}")
        if res is not None:
            url = URL(res)
        else:
            url = None
        logger.info("db.get", short=short, url=url)
        return url

    async def latest(self) -> list[str]:
        return await self._redis.lrange("latest.shorts", 0, 99)
