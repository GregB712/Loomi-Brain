"""phase 6 mcp client registry

Revision ID: 20260729_0006
Revises: 20260729_0005
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0006"
down_revision: str | None = "20260729_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mcp_servers", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("mcp_servers", sa.Column("secret_ref", sa.String(255), nullable=True))
    op.add_column("mcp_servers", sa.Column("environment_allowlist", sa.JSON(), nullable=True))
    op.add_column("mcp_servers", sa.Column("working_directory", sa.String(512), nullable=True))
    op.add_column(
        "mcp_servers", sa.Column("connection_timeout_seconds", sa.Integer(), nullable=True)
    )
    op.add_column("mcp_servers", sa.Column("tool_timeout_seconds", sa.Integer(), nullable=True))
    op.add_column("mcp_servers", sa.Column("output_size_limit", sa.Integer(), nullable=True))
    op.add_column("mcp_servers", sa.Column("health_status", sa.String(40), nullable=True))
    op.add_column("mcp_servers", sa.Column("health_detail", sa.Text(), nullable=True))
    op.add_column("mcp_servers", sa.Column("capability_cache", sa.JSON(), nullable=True))
    op.add_column(
        "mcp_servers", sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "mcp_servers",
        sa.Column("last_capability_refresh_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("mcp_servers", sa.Column("last_error", sa.JSON(), nullable=True))
    op.create_index(
        "ix_mcp_servers_owner_disabled",
        "mcp_servers",
        ["owner_user_id", "disabled_at"],
    )

    op.add_column("mcp_capabilities", sa.Column("owner_user_id", sa.String(36), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("title", sa.String(160), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("output_schema", sa.JSON(), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("approval_policy", sa.String(40), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("enabled", sa.Boolean(), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("schema_hash", sa.String(64), nullable=True))
    op.add_column("mcp_capabilities", sa.Column("capability_metadata", sa.JSON(), nullable=True))
    op.add_column(
        "mcp_capabilities",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_mcp_capabilities_unique",
        "mcp_capabilities",
        ["server_id", "capability_type", "name"],
        unique=True,
    )
    op.create_index(
        "ix_mcp_capabilities_owner_enabled",
        "mcp_capabilities",
        ["owner_user_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_capabilities_owner_enabled", table_name="mcp_capabilities")
    op.drop_index("ix_mcp_capabilities_unique", table_name="mcp_capabilities")
    for column_name in reversed(
        [
            "owner_user_id",
            "title",
            "description",
            "output_schema",
            "approval_policy",
            "enabled",
            "schema_hash",
            "capability_metadata",
            "last_seen_at",
        ]
    ):
        op.drop_column("mcp_capabilities", column_name)

    op.drop_index("ix_mcp_servers_owner_disabled", table_name="mcp_servers")
    for column_name in reversed(
        [
            "description",
            "secret_ref",
            "environment_allowlist",
            "working_directory",
            "connection_timeout_seconds",
            "tool_timeout_seconds",
            "output_size_limit",
            "health_status",
            "health_detail",
            "capability_cache",
            "last_connected_at",
            "last_capability_refresh_at",
            "last_error",
        ]
    ):
        op.drop_column("mcp_servers", column_name)
