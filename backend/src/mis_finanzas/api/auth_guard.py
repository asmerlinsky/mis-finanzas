"""Every `/api` route needs a login session once a password is set; these few don't."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from mis_finanzas.auth import service as auth
from mis_finanzas.core.config import Settings

OPEN_PATHS = frozenset({"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"})


def _allowed(app: FastAPI, token: str | None) -> bool:
    with app.state.session_factory() as session:
        return auth.session_valid(session, token)


class AuthGuard(BaseHTTPMiddleware):
    """401 for `/api` requests without a valid session cookie, when login is required.

    The built frontend (outside `/api`) is served to anyone: it holds no data.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        settings: Settings = request.app.state.settings
        if (
            path.startswith("/api/")
            and path not in OPEN_PATHS
            and auth.login_required(settings.auth_file)
            and not await run_in_threadpool(_allowed, request.app, request.cookies.get(auth.COOKIE))
        ):
            return JSONResponse({"detail": "login required"}, status.HTTP_401_UNAUTHORIZED)
        return await call_next(request)
