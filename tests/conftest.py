import socket
import time
from typing import AsyncIterator, Callable, Iterator

import docker  # type: ignore
import pytest
import pytest_asyncio
import redis
import redis.asyncio


@pytest.fixture(scope="session")
def docker_client() -> docker.DockerClient:
    return docker.from_env()


@pytest.fixture(scope="session")
def redis_url(
    docker_client: docker.DockerClient, unused_tcp_port_factory: Callable[[], int]
) -> Iterator[str]:
    port = unused_tcp_port_factory()
    container = docker_client.containers.run(
        "redis:latest", detach=True, auto_remove=True, ports={"6379/tcp": port}
    )
    redis_url = f"redis://localhost:{port}"
    # wait for the container start
    delay = 0.01
    for i in range(100_000):
        with redis.from_url(redis_url) as redis_client:
            s = socket.socket()
            try:
                redis_client.ping()
                break
            except redis.ConnectionError:
                time.sleep(delay)
                delay *= 2
    else:
        raise RuntimeError("Cannot connect to Redis container")
    yield redis_url
    container.stop()


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> "AsyncIterator[redis.asyncio.Redis[str]]":
    client = redis.asyncio.from_url(redis_url)
    await client.initialize()
    yield client
    await client.close()
