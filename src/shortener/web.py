import contextvars
import json
from collections.abc import MappingView
from dataclasses import asdict, is_dataclass
from functools import partial
from typing import Any, AsyncIterator, Awaitable, Callable

import jinja2
import structlog
from aiohttp import web
from aiohttp_jinja2 import render_template
from aiohttp_jinja2 import setup as setup_jinja
from prometheus_async.aio import time
from prometheus_async.aio.web import start_http_server
from prometheus_client import Histogram
from yarl import URL

from .config import Config
from .db import Database

logger = structlog.get_logger()

DB: contextvars.ContextVar[Database] = contextvars.ContextVar("DB")


ROUTES = web.RouteTableDef()

REQ_TIME = Histogram(
    "req_time_seconds", "time spent in requests", ["method", "endpoint"]
)


def json_default(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    elif isinstance(obj, MappingView):  # e.g. dict_values
        return list(obj)  # type: ignore[call-overload]
    elif isinstance(obj, URL):
        return str(obj)
    else:
        raise TypeError(type(obj))


REQ_TIME_INDEX = REQ_TIME.labels("get", "/")


@ROUTES.get("/")
@time(REQ_TIME_INDEX)
async def index(request: web.Request) -> web.Response:
    added_short = request.query.get("added_short")
    if added_short:
        added = {
            "href": f"/{added_short}",
            "caption": f"/{added_short}",
            "url": request.query["added_url"],
        }
    else:
        added = None
    latest = await DB.get().latest()
    dct = {"added": added, "latest": latest.values()}
    if "application/json" in request.headers["Accept"]:
        return web.json_response(dct, dumps=partial(json.dumps, default=json_default))
    else:
        return render_template("index.jinja2", request, dct)


REQ_TIME_CREATE = REQ_TIME.labels("post", "/")


@ROUTES.post("/")
@time(REQ_TIME_INDEX)
async def create(request: web.Request) -> web.Response:
    form = await request.post()
    url_str = form.get("url")
    if not url_str:
        logger.error("web.create.fail.absent", url=url_str)
        raise web.HTTPBadRequest(text="URL is absent")
    if not isinstance(url_str, str):
        logger.error("web.create.fail.type", url=url_str, url_type=type(url_str))
        raise web.HTTPBadRequest(text="URL is malfolmed")
    try:
        url = URL(url_str)
    except Exception as exc:
        logger.error("web.create.fail.malformed", url=url)
        raise web.HTTPBadRequest(text="URL is malfolmed")
    short = await DB.get().register(url)
    new_url = URL.build(path="/", query={"added_short": short, "added_url": url_str})
    logger.info("web.creat.ok", short=short, url=url_str)
    raise web.HTTPSeeOther(location=new_url)


REQ_TIME_REDIRECT = REQ_TIME.labels("get", "/{short}")


@ROUTES.get("/{short}")
@time(REQ_TIME_INDEX)
async def redirect(request: web.Request) -> web.Response:
    short = request.match_info["short"]
    url = await DB.get().redirect(short)
    if url is None:
        logger.info("web.redirect.missed", short=short, url=url)
        raise web.HTTPNotFound()
    logger.info("web.redirect.found", short=short, url=url)
    raise web.HTTPSeeOther(location=url)


@web.middleware
async def errors_handler(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException as exc:
        logger.exception("web.error.http")
        raise
    except Exception:
        logger.critical("web.error.unhandler")
        raise web.HTTPInternalServerError()


async def init(config: Config) -> web.Application:
    app = web.Application(middlewares=[errors_handler])
    setup_jinja(app, loader=jinja2.PackageLoader(__package__, "templates"))
    app.add_routes(ROUTES)

    async def setup_db(app: web.Application) -> AsyncIterator[None]:
        db = Database(config.redis_url)
        DB.set(db)
        app["db"] = db
        yield
        await db.close()

    async def setup_prometheus(app: web.Application) -> AsyncIterator[None]:
        srv = await start_http_server(
            addr=config.prometheus_host, port=config.prometheus_port
        )
        app["prometheus"] = srv
        yield
        await srv.close()

    app.cleanup_ctx.append(setup_db)
    app.cleanup_ctx.append(setup_prometheus)
    return app


def main() -> None:
    config = Config()
    logger.info("web.serve", host=config.http_host, port=config.http_port)
    web.run_app(init(config), host=config.http_host, port=config.http_port)
