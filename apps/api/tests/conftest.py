from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from loomi_api.auth.service import seed_owner
from loomi_api.config import Settings
from loomi_api.db.session import create_engine, create_sessionmaker
from loomi_api.db.testing import reset_database
from loomi_api.main import create_app


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'loomi-test.db'}",
        owner_email="owner@example.test",
        owner_password=SecretStr("phase1-owner-password"),  # noqa: S106
        session_cookie_secure=False,
    )


@pytest.fixture
def seeded_client(api_settings: Settings) -> Iterator[TestClient]:
    asyncio.run(reset_database(api_settings))
    asyncio.run(_seed(api_settings))
    app = create_app(api_settings)
    with TestClient(app) as client:
        yield client


async def _seed(settings: Settings) -> None:
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as session:
        await seed_owner(session, settings)
    await engine.dispose()
