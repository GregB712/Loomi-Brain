from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.auth.passwords import (
    hash_password,
    hash_token,
    new_secret_token,
    verify_password,
)
from loomi_api.config import Settings
from loomi_api.db.base import utc_now
from loomi_api.db.models import AuditEvent, AuthAccount, OwnerSession, User


@dataclass
class LoginResult:
    owner: User
    session: OwnerSession
    session_token: str
    csrf_token: str


@dataclass
class AuthenticatedOwner:
    user: User
    session: OwnerSession


_login_attempts: dict[str, list[float]] = {}


async def seed_owner(session: AsyncSession, settings: Settings) -> User:
    email = normalize_email(settings.owner_email)
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing

    owner = User(email=email, display_name=settings.owner_name, is_owner=True)
    session.add(owner)
    await session.flush()

    session.add(
        AuthAccount(
            user_id=owner.id,
            provider="local",
            provider_subject=email,
            password_hash=hash_password(
                settings.owner_password.get_secret_value(),
                iterations=settings.password_hash_iterations,
            ),
        )
    )
    session.add(
        AuditEvent(
            owner_user_id=owner.id,
            event_type="owner.seeded",
            event_metadata={"provider": "local"},
        )
    )
    await session.commit()
    return owner


async def login_owner(
    session: AsyncSession,
    settings: Settings,
    request: Request,
    *,
    email: str,
    password: str,
) -> LoginResult:
    normalized_email = normalize_email(email)
    _enforce_login_rate_limit(settings, request, normalized_email)
    row = await session.execute(
        select(AuthAccount, User)
        .join(User, AuthAccount.user_id == User.id)
        .where(
            AuthAccount.provider == "local",
            AuthAccount.provider_subject == normalized_email,
        )
    )
    result = row.one_or_none()
    if result is None:
        await _audit_login_failure(session, request, normalized_email)
        raise _invalid_credentials()

    account, owner = result
    if (
        account.password_hash is None
        or not owner.is_owner
        or owner.disabled_at is not None
        or not verify_password(password, account.password_hash)
    ):
        await _audit_login_failure(session, request, normalized_email)
        raise _invalid_credentials()

    _clear_login_rate_limit(request, normalized_email)
    session_token = new_secret_token()
    csrf_token = new_secret_token()
    owner_session = OwnerSession(
        user_id=owner.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
        expires_at=utc_now() + timedelta(minutes=settings.session_ttl_minutes),
    )
    session.add(owner_session)
    await session.flush()
    session.add(
        AuditEvent(
            owner_user_id=owner.id,
            event_type="auth.login",
            request_id=getattr(request.state, "request_id", None),
            trace_id=getattr(request.state, "trace_id", None),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            event_metadata={"session_id": owner_session.id},
        )
    )
    await session.commit()
    return LoginResult(
        owner=owner,
        session=owner_session,
        session_token=session_token,
        csrf_token=csrf_token,
    )


async def authenticate_session(
    session: AsyncSession,
    session_token: str | None,
) -> AuthenticatedOwner:
    if not session_token:
        raise _unauthorized()

    row = await session.execute(
        select(OwnerSession, User)
        .join(User, OwnerSession.user_id == User.id)
        .where(OwnerSession.token_hash == hash_token(session_token))
    )
    result = row.one_or_none()
    if result is None:
        raise _unauthorized()

    owner_session, owner = result
    if (
        owner_session.revoked_at is not None
        or _as_aware(owner_session.expires_at) <= utc_now()
        or not owner.is_owner
        or owner.disabled_at is not None
    ):
        raise _unauthorized()

    return AuthenticatedOwner(user=owner, session=owner_session)


def verify_csrf(authenticated: AuthenticatedOwner, csrf_token: str | None) -> None:
    if not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF token.",
        )
    if hash_token(csrf_token) != authenticated.session.csrf_token_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token.",
        )


async def logout_owner(
    session: AsyncSession,
    request: Request,
    authenticated: AuthenticatedOwner,
) -> None:
    authenticated.session.revoked_at = utc_now()
    session.add(
        AuditEvent(
            owner_user_id=authenticated.user.id,
            event_type="auth.logout",
            request_id=getattr(request.state, "request_id", None),
            trace_id=getattr(request.state, "trace_id", None),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            event_metadata={"session_id": authenticated.session.id},
        )
    )
    await session.commit()


async def list_sessions(
    session: AsyncSession, authenticated: AuthenticatedOwner
) -> list[OwnerSession]:
    result = await session.scalars(
        select(OwnerSession)
        .where(OwnerSession.user_id == authenticated.user.id)
        .order_by(OwnerSession.created_at.desc())
    )
    return list(result)


async def revoke_session(
    session: AsyncSession,
    request: Request,
    authenticated: AuthenticatedOwner,
    session_id: str,
) -> None:
    session_record = await session.scalar(
        select(OwnerSession).where(
            OwnerSession.id == session_id,
            OwnerSession.user_id == authenticated.user.id,
        )
    )
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    session_record.revoked_at = utc_now()
    session.add(
        AuditEvent(
            owner_user_id=authenticated.user.id,
            event_type="auth.session_revoked",
            request_id=getattr(request.state, "request_id", None),
            trace_id=getattr(request.state, "trace_id", None),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            event_metadata={"session_id": session_record.id},
        )
    )
    await session.commit()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def _enforce_login_rate_limit(settings: Settings, request: Request, normalized_email: str) -> None:
    now = monotonic()
    window_started = now - settings.auth_login_rate_limit_window_seconds
    key = f"{_client_ip(request) or 'unknown'}:{normalized_email}"
    attempts = [stamp for stamp in _login_attempts.get(key, []) if stamp >= window_started]
    attempts.append(now)
    _login_attempts[key] = attempts
    if len(attempts) > settings.auth_login_rate_limit_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )


def _clear_login_rate_limit(request: Request, normalized_email: str) -> None:
    key = f"{_client_ip(request) or 'unknown'}:{normalized_email}"
    _login_attempts.pop(key, None)


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid owner credentials.",
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Owner session required.",
    )


async def _audit_login_failure(
    session: AsyncSession, request: Request, normalized_email: str
) -> None:
    session.add(
        AuditEvent(
            owner_user_id=None,
            event_type="auth.login_failed",
            request_id=getattr(request.state, "request_id", None),
            trace_id=getattr(request.state, "trace_id", None),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            event_metadata={"email": normalized_email},
        )
    )
    await session.commit()


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
