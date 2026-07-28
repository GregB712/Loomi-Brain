"""phase 2 ingestion metadata and indexes

Revision ID: 20260728_0002
Revises: 20260728_0001
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("document_versions") as batch:
        batch.add_column(
            sa.Column("storage_size_bytes", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("parser_name", sa.String(120), nullable=True))
        batch.add_column(sa.Column("parser_version", sa.String(80), nullable=True))

    with op.batch_alter_table("ingestion_jobs") as batch:
        batch.add_column(sa.Column("document_version_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("stage_log", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_ingestion_jobs_document_version_id_document_versions",
            "document_versions",
            ["document_version_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("chunks") as batch:
        batch.add_column(sa.Column("stable_id", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("text_sha256", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("chunker_version", sa.String(80), nullable=False, server_default="phase2-v1")
        )
        batch.create_index(
            "ix_chunks_version_stable_id",
            ["document_version_id", "stable_id"],
            unique=True,
        )

    with op.batch_alter_table("embeddings") as batch:
        batch.add_column(
            sa.Column(
                "embedding_version", sa.String(80), nullable=False, server_default="phase2-v1"
            )
        )
        batch.add_column(
            sa.Column("vector_checksum", sa.String(64), nullable=False, server_default="")
        )

    op.create_index(
        "ix_collections_owner_name", "collections", ["owner_user_id", "name"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_collections_owner_name", table_name="collections")

    with op.batch_alter_table("embeddings") as batch:
        batch.drop_column("vector_checksum")
        batch.drop_column("embedding_version")

    with op.batch_alter_table("chunks") as batch:
        batch.drop_index("ix_chunks_version_stable_id")
        batch.drop_column("chunker_version")
        batch.drop_column("token_count")
        batch.drop_column("text_sha256")
        batch.drop_column("stable_id")

    with op.batch_alter_table("ingestion_jobs") as batch:
        batch.drop_constraint(
            "fk_ingestion_jobs_document_version_id_document_versions", type_="foreignkey"
        )
        batch.drop_column("cancel_requested_at")
        batch.drop_column("completed_at")
        batch.drop_column("started_at")
        batch.drop_column("metrics")
        batch.drop_column("stage_log")
        batch.drop_column("progress_percent")
        batch.drop_column("document_version_id")

    with op.batch_alter_table("document_versions") as batch:
        batch.drop_column("parser_version")
        batch.drop_column("parser_name")
        batch.drop_column("storage_size_bytes")
