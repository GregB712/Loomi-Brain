from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_creates_phase1_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {
        "users",
        "owner_settings",
        "auth_accounts",
        "sessions",
        "documents",
        "document_versions",
        "ingestion_jobs",
        "chunks",
        "embeddings",
        "conversations",
        "messages",
        "agent_runs",
        "tool_calls",
        "approvals",
        "skills",
        "skill_versions",
        "mcp_servers",
        "mcp_capabilities",
        "audit_events",
        "telemetry_spans",
        "evaluation_datasets",
        "evaluation_runs",
        "evaluation_results",
    }.issubset(table_names)
