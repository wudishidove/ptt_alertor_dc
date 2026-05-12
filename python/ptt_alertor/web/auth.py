from __future__ import annotations

import base64

from aiohttp import web

from ..context import AppContext

REALM = "ptt-alertor admin"


def _unauthorized() -> web.Response:
    return web.Response(
        status=401,
        text="Unauthorized\n",
        headers={"WWW-Authenticate": f'Basic realm="{REALM}"'},
    )


@web.middleware
async def basic_auth_middleware(request: web.Request, handler):
    """Apply Basic Auth to routes flagged with `requires_auth=True` in their info."""
    route = request.match_info.route
    needs_auth = bool(getattr(route, "_requires_auth", False))
    if not needs_auth:
        return await handler(request)

    ctx: AppContext = request.app["ctx"]
    expected_user = ctx.settings.auth_user
    expected_pw = ctx.settings.auth_pw

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return _unauthorized()

    try:
        encoded = auth_header.split(" ", 1)[1].strip()
        decoded = base64.b64decode(encoded).decode("utf-8")
        user, _, password = decoded.partition(":")
    except Exception:
        return _unauthorized()

    if user != expected_user or password != expected_pw or not expected_pw:
        return _unauthorized()
    return await handler(request)


def require_auth(route_def: web.RouteDef) -> web.RouteDef:
    """Mark a RouteDef as requiring Basic Auth."""
    setattr(route_def, "_requires_auth", True)  # noqa: B010
    return route_def


class AuthRoute:
    """Helper: routes added through this need auth."""

    def __init__(self, app: web.Application) -> None:
        self.app = app

    def add(self, method: str, path: str, handler) -> None:
        resource = self.app.router.add_resource(path)
        route = resource.add_route(method, handler)
        setattr(route, "_requires_auth", True)  # noqa: B010
