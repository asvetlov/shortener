import contextvars
from typing import Any, TypedDict

import jinja2
import structlog
from aiohttp import web
from aiohttp_jinja2 import setup as setup_jinja
from aiohttp_jinja2 import template
from yarl import URL

from .config import Config
from .db import AbstractDB, create_db

logger = structlog.get_logger()

DB: contextvars.ContextVar[AbstractDB] = contextvars.ContextVar("DB")


ROUTES = web.RouteTableDef()


class _LatestItem(TypedDict):
    href: str
    caption: str


async def _read_latest() -> list[_LatestItem]:
    latest = []
    for short in await DB.get().latest():
        latest.append(_LatestItem(href=f"/{short}", caption=short))
    return latest


@ROUTES.get("/")
@template("index.jinja2")
async def index(request: web.Request) -> dict[str, Any]:
    added_short = request.query.get("added_short")
    if added_short:
        added = {
            "href": f"/{added_short}",
            "caption": f"/{added_short}",
            "url": request.query["added_url"],
        }
    latest = await _read_latest()
    return {"added": added, "latest": latest}


@ROUTES.post("/")
async def create(request: web.Request) -> web.Response:
    form = await request.post()
    url = form["url"]
    assert isinstance(url, str)
    short = await DB.get().register(URL(url))
    new_url = URL.build(path="/", query={"added_short": short, "added_url": url})
    raise web.HTTPSeeOther(location=new_url)


@ROUTES.get("/{short}")
async def redirect(request: web.Request) -> web.Response:
    pass


def init(config: Config) -> web.Application:
    app = web.Application()
    setup_jinja(app, loader=jinja2.PackageLoader(__package__, "templates"))
    app.add_routes(ROUTES)
    db = create_db(config.redis_url)
    DB.set(db)
    return app


def main() -> None:
    config = Config()
    app = init(config)
    logger.info("web.serve", port=config.http_port)
    web.run_app(app, port=config.http_port)
