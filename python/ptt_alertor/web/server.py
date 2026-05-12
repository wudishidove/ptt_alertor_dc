from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp_jinja2
import jinja2
from aiohttp import web

from ..context import AppContext
from ..logger import get_logger
from . import handlers
from .auth import basic_auth_middleware

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


def build_app(ctx: AppContext) -> web.Application:
    app = web.Application(middlewares=[basic_auth_middleware])
    app["ctx"] = ctx

    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates")),
    )

    # public
    app.router.add_get("/", handlers.index)
    app.router.add_get("/boards", handlers.boards)

    # admin (Basic Auth via flag)
    auth_routes = [
        ("GET", "/users", handlers.users_index),
        ("GET", r"/users/{account}", handlers.user_find),
        ("POST", "/users", handlers.user_create),
        ("PUT", r"/users/{account}", handlers.user_modify),
        ("POST", "/broadcast", handlers.broadcast_handler),
    ]
    for method, path, handler in auth_routes:
        resource = app.router.add_resource(path)
        route = resource.add_route(method, handler)
        setattr(route, "_requires_auth", True)  # noqa: B010

    return app


async def start_web_server(ctx: AppContext) -> tuple[web.AppRunner, web.TCPSite]:
    app = build_app(ctx)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, ctx.settings.web_host, ctx.settings.web_port)
    await site.start()
    log.info("Web server listening on %s:%d", ctx.settings.web_host, ctx.settings.web_port)
    return runner, site


async def stop_web_server(runner: web.AppRunner) -> None:
    await runner.cleanup()
    log.info("Web server stopped")
