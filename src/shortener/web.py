import contextvars
import json
from collections.abc import MappingView
from dataclasses import asdict, is_dataclass
from functools import partial
from typing import Any, AsyncIterator

import jinja2
import structlog
from aiohttp import web
from aiohttp_jinja2 import render_template
from aiohttp_jinja2 import setup as setup_jinja
from yarl import URL

from .config import Config
from .db import Database

logger = structlog.get_logger()

DB: contextvars.ContextVar[Database] = contextvars.ContextVar("DB")


ROUTES = web.RouteTableDef()


def json_default(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    elif isinstance(obj, MappingView):  # e.g. dict_values
        return list(obj)
    elif isinstance(obj, URL):
        return str(obj)
    else:
        raise TypeError(type(obj))


@ROUTES.get("/")
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


@ROUTES.post("/")
async def create(request: web.Request) -> web.Response:
    form = await request.post()
    url = form["url"]
    assert isinstance(url, str)
    short = await DB.get().register(URL(url))
    new_url = URL.build(path="/", query={"added_short": short, "added_url": url})
    logger.info("web.created", short=short, url=url)
    raise web.HTTPSeeOther(location=new_url)


@ROUTES.get("/{short}")
async def redirect(request: web.Request) -> web.Response:
    short = request.match_info["short"]
    url = await DB.get().redirect(short)
    if url is None:
        raise web.HTTPNotFound()
    logger.info("web.redirect", short=short, url=url)
    raise web.HTTPSeeOther(location=url)


async def init(config: Config) -> web.Application:
    app = web.Application()
    setup_jinja(app, loader=jinja2.PackageLoader(__package__, "templates"))
    app.add_routes(ROUTES)

    async def setup_db(app: web.Application) -> AsyncIterator[None]:
        db = Database(config.redis_url)
        DB.set(db)
        app["db"] = db
        yield
        await db.close()

    app.cleanup_ctx.append(setup_db)
    return app


def main() -> None:
    config = Config()
    logger.info("web.serve", port=config.http_port)
    web.run_app(init(config), port=config.http_port)
