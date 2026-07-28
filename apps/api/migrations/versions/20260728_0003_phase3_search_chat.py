"""phase 3 search and cited chat indexes

Revision ID: 20260728_0003
Revises: 20260728_0002
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_0003"
down_revision: str | None = "20260728_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS vector vector(16)")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_embeddings_vector_cosine
            ON embeddings USING hnsw (vector vector_cosine_ops)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_chunks_text_fts
            ON chunks USING gin (to_tsvector('english', text))
            """
        )
    else:
        op.create_index("ix_chunks_owner_document", "chunks", ["owner_user_id", "document_id"])

    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_agent_runs_owner_state",
        "agent_runs",
        ["owner_user_id", "state"],
    )
    op.create_index(
        "ix_message_citations_message",
        "message_citations",
        ["message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_citations_message", table_name="message_citations")
    op.drop_index("ix_agent_runs_owner_state", table_name="agent_runs")
    op.drop_index("ix_messages_conversation_created", table_name="messages")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_chunks_text_fts")
        op.execute("DROP INDEX IF EXISTS ix_embeddings_vector_cosine")
        op.execute("ALTER TABLE embeddings DROP COLUMN IF EXISTS vector")
    else:
        op.drop_index("ix_chunks_owner_document", table_name="chunks")
