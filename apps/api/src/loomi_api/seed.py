from __future__ import annotations

import asyncio

from loomi_api.auth.service import seed_owner
from loomi_api.config import Settings
from loomi_api.db.session import create_engine, create_sessionmaker


async def seed(settings: Settings) -> None:
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as session:
        owner = await seed_owner(session, settings)
        print(f"Seeded owner: {owner.email}")
    await engine.dispose()


def main() -> None:
    asyncio.run(seed(Settings()))


if __name__ == "__main__":
    main()
