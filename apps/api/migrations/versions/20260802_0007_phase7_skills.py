"""phase 7 declarative skills

Revision ID: 20260802_0007
Revises: 20260729_0006
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0007"
down_revision: str | None = "20260729_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("normalized_name", sa.String(120), nullable=True))
    op.add_column("skills", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("skills", sa.Column("provenance", sa.JSON(), nullable=True))
    op.create_index(
        "ix_skills_owner_normalized",
        "skills",
        ["owner_user_id", "normalized_name"],
        unique=True,
    )
    op.create_index("ix_skills_owner_state", "skills", ["owner_user_id", "state"])

    op.add_column("skill_versions", sa.Column("owner_user_id", sa.String(36), nullable=True))
    op.add_column("skill_versions", sa.Column("canonical_manifest", sa.JSON(), nullable=True))
    op.add_column("skill_versions", sa.Column("manifest_checksum", sa.String(64), nullable=True))
    op.add_column("skill_versions", sa.Column("state", sa.String(40), nullable=True))
    op.add_column("skill_versions", sa.Column("parent_version_id", sa.String(36), nullable=True))
    op.add_column("skill_versions", sa.Column("validation_results", sa.JSON(), nullable=True))
    op.add_column("skill_versions", sa.Column("publication_metadata", sa.JSON(), nullable=True))
    op.add_column("skill_versions", sa.Column("provenance", sa.JSON(), nullable=True))
    op.add_column(
        "skill_versions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "skill_versions", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_skill_versions_skill_version",
        "skill_versions",
        ["skill_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_skill_versions_owner_state",
        "skill_versions",
        ["owner_user_id", "state"],
    )

    op.add_column("skill_tests", sa.Column("skill_version_id", sa.String(36), nullable=True))
    op.add_column("skill_tests", sa.Column("owner_user_id", sa.String(36), nullable=True))
    op.add_column("skill_tests", sa.Column("test_metadata", sa.JSON(), nullable=True))
    op.create_index("ix_skill_tests_version", "skill_tests", ["skill_version_id"])

    _create_table(
        "skill_test_runs",
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("skills.id", ondelete="CASCADE")),
        sa.Column(
            "skill_version_id",
            sa.String(36),
            sa.ForeignKey("skill_versions.id", ondelete="CASCADE"),
        ),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_skill_test_runs_version_status",
        "skill_test_runs",
        ["skill_version_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_skill_test_runs_version_status", table_name="skill_test_runs")
    op.drop_table("skill_test_runs")

    op.drop_index("ix_skill_tests_version", table_name="skill_tests")
    for column_name in reversed(["skill_version_id", "owner_user_id", "test_metadata"]):
        op.drop_column("skill_tests", column_name)

    op.drop_index("ix_skill_versions_owner_state", table_name="skill_versions")
    op.drop_index("ix_skill_versions_skill_version", table_name="skill_versions")
    for column_name in reversed(
        [
            "owner_user_id",
            "canonical_manifest",
            "manifest_checksum",
            "state",
            "parent_version_id",
            "validation_results",
            "publication_metadata",
            "provenance",
            "archived_at",
            "disabled_at",
        ]
    ):
        op.drop_column("skill_versions", column_name)

    op.drop_index("ix_skills_owner_state", table_name="skills")
    op.drop_index("ix_skills_owner_normalized", table_name="skills")
    for column_name in reversed(["normalized_name", "description", "provenance"]):
        op.drop_column("skills", column_name)


def _create_table(name: str, *columns: sa.Column[str]) -> None:
    op.create_table(name, _id_column(), *_timestamp_columns(), *columns)


def _id_column() -> sa.Column[str]:
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamp_columns() -> tuple[sa.Column[datetime], sa.Column[datetime]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
