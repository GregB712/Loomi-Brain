from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.auth.service import AuthenticatedOwner, authenticate_session, verify_csrf
from loomi_api.config import Settings
from loomi_api.db.session import get_db_session

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_settings_from_app(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def require_owner(
    request: Request,
    session: DbSession,
) -> AuthenticatedOwner:
    settings = get_settings_from_app(request)
    session_token = request.cookies.get(settings.session_cookie_name)
    return await authenticate_session(session, session_token)


OwnerContext = Annotated[AuthenticatedOwner, Depends(require_owner)]


async def require_csrf(
    request: Request,
    owner: OwnerContext,
) -> AuthenticatedOwner:
    settings = get_settings_from_app(request)
    verify_csrf(owner, request.headers.get(settings.csrf_header_name))
    return owner


CsrfOwnerContext = Annotated[AuthenticatedOwner, Depends(require_csrf)]
