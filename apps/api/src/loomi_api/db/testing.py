from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine

from loomi_api.config import Settings
from loomi_api.db import models as _models  # noqa: F401
from loomi_api.db.base import Base

__all__ = ["reset_database"]


async def reset_database(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
