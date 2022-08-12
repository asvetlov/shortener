import abc
import dataclasses
import secrets
import string
from collections import defaultdict

import redis.asyncio as redis
import structlog
from yarl import URL

logger = structlog.get_logger()


@dataclasses.dataclass(frozen=True, kw_only=True)
class Record:
    short: str
    url: URL
    clicks: int


class Database:
    SYMBOLS = string.digits + string.ascii_letters
    SIZE = 5

    def __init__(self, redis_url: str, *, cluster: bool = False) -> None:
        logger.info("db.connect", url=redis_url)
        # plain Redis should be enough for the demo;
        # the battle deployent can use RedisCluster
        if not cluster:
            self._redis = redis.from_url(redis_url)
        else:
            self._redis = redis.RedisCluster.from_url(redis_url)  # type: ignore

    async def close(self) -> None:
        logger.info("db.close")
        await self._redis.close()

    async def register(self, url: URL) -> str:
        """Return a hash for registered long_url."""
        while True:
            short = self._gen_random()
            is_set = await self._redis.setnx(f"shorts:{{{short}}}", str(url))
            if is_set:
                logger.info("db.registered", short=short, url=url)
                break
            else:
                logger.debug("db.collision", short=short, url=url)
        await self._redis.lpush("latest.shorts", short)
        await self._redis.ltrim("latest.shorts", 0, 99)
        return short

    async def redirect(self, short: str) -> URL | None:
        """Return long url for registered short hash if present.

        Return None if a hash was not registered yet.

        Increment internal counter for requested short hash.
        The method should be used to redirecting only, not for getting statistical info.
        """
        res = await self._redis.get(f"shorts:{{{short}}}")
        if res is not None:
            url = URL(res.decode("ascii"))
        else:
            url = None
        await self._redis.incr(f"clicks:{{{short}}}")
        logger.info("db.get", short=short, url=url)
        return url

    async def latest(self) -> dict[str, Record]:
        """Return last 100 registered short hashes."""
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

    def _gen_random(self) -> str:
        return "".join(secrets.choice(self.SYMBOLS) for i in range(self.SIZE))
