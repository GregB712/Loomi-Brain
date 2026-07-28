from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from loomi_api.api.dependencies import CsrfOwnerContext, DbSession, OwnerContext
from loomi_api.auth.schemas import (
    LoginRequest,
    LoginResponse,
    OwnerResponse,
    SessionResponse,
)
from loomi_api.auth.service import list_sessions, login_owner, logout_owner, revoke_session
from loomi_api.config import Settings
from loomi_api.db.models import OwnerSession, User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> LoginResponse:
    settings: Settings = request.app.state.settings
    result = await login_owner(
        session,
        settings,
        request,
        email=payload.email,
        password=payload.password,
    )
    max_age = settings.session_ttl_minutes * 60
    response.set_cookie(
        settings.session_cookie_name,
        result.session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        result.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return LoginResponse(owner=_owner_response(result.owner), csrf_token=result.csrf_token)


@router.get("/me", response_model=OwnerResponse)
async def me(owner: OwnerContext) -> OwnerResponse:
    return _owner_response(owner.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> None:
    settings: Settings = request.app.state.settings
    await logout_owner(session, request, owner)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.get("/sessions", response_model=list[SessionResponse])
async def sessions(session: DbSession, owner: OwnerContext) -> list[SessionResponse]:
    records = await list_sessions(session, owner)
    return [_session_response(record, current=record.id == owner.session.id) for record in records]


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    session_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> None:
    await revoke_session(session, request, owner, session_id)


def _owner_response(owner: User) -> OwnerResponse:
    return OwnerResponse(
        id=owner.id,
        email=owner.email,
        display_name=owner.display_name,
    )


def _session_response(record: OwnerSession, *, current: bool) -> SessionResponse:
    return SessionResponse(
        id=record.id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        current=current,
    )
