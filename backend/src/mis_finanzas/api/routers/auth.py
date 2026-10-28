from fastapi import APIRouter, HTTPException, Request, Response, status

from mis_finanzas.api.deps import SessionDep, SettingsDep
from mis_finanzas.api.schemas import AuthStatusOut, LoginIn
from mis_finanzas.auth import service as auth

router = APIRouter(tags=["auth"])


@router.get("/health")
def health() -> dict[str, str]:
    """For container healthchecks: no data, no login."""
    return {"status": "ok"}


@router.get("/auth/status", response_model=AuthStatusOut)
def auth_status(request: Request, session: SessionDep, settings: SettingsDep) -> AuthStatusOut:
    required = auth.login_required(settings.auth_file)
    token = request.cookies.get(auth.COOKIE)
    return AuthStatusOut(
        required=required, authenticated=not required or auth.session_valid(session, token)
    )


@router.post("/auth/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> None:
    throttle: auth.LoginThrottle = request.app.state.login_throttle
    if throttle.locked():
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong passwords; try again later"
        )
    if not auth.login_required(settings.auth_file):
        raise HTTPException(status.HTTP_409_CONFLICT, "no password is set")
    if not auth.check_password(settings.auth_file, body.password):
        throttle.failed()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong password")
    throttle.succeeded()
    token = auth.start_session(session, settings.session_days)
    response.set_cookie(
        auth.COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: SessionDep) -> None:
    auth.end_session(session, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
