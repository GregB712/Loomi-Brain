"""phase 1 foundation schema

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    _create_table(
        "users",
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"])

    _create_table(
        "owner_settings",
        _owner_fk(),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.create_index("ix_owner_settings_owner_key", "owner_settings", ["owner_user_id", "key"])

    _create_table(
        "auth_accounts",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_subject", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_auth_accounts_provider_subject",
        "auth_accounts",
        ["provider", "provider_subject"],
        unique=True,
    )

    _create_table(
        "sessions",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(80), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"])
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"])

    _create_table(
        "provider_configurations",
        _owner_fk(),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("secret_ref", sa.String(255), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table(
        "documents",
        _owner_fk(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_owner_status", "documents", ["owner_user_id", "status"])

    _create_table(
        "tags",
        _owner_fk(),
        sa.Column("name", sa.String(80), nullable=False),
    )
    op.create_index("ix_tags_owner_name", "tags", ["owner_user_id", "name"], unique=True)

    _create_table(
        "collections",
        _owner_fk(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    _create_table(
        "conversations",
        _owner_fk(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table(
        "skills",
        _owner_fk(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("current_version_id", sa.String(36), nullable=True),
    )

    _create_table(
        "mcp_servers",
        _owner_fk(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("transport", sa.String(40), nullable=False),
        sa.Column("command_template", sa.JSON(), nullable=True),
        sa.Column("url", sa.String(512), nullable=True),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table(
        "evaluation_datasets",
        _owner_fk(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    _create_table(
        "audit_events",
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("request_id", sa.String(160), nullable=True),
        sa.Column("trace_id", sa.String(160), nullable=True),
        sa.Column("ip_address", sa.String(80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
    )
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"])

    _create_table(
        "document_versions",
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=True),
        sa.Column("extraction_metadata", sa.JSON(), nullable=False),
    )
    op.create_index(
        op.f("ix_document_versions_content_sha256"),
        "document_versions",
        ["content_sha256"],
    )

    _create_table(
        "ingestion_jobs",
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
        ),
        _owner_fk(),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
    )
    op.create_index(
        "ix_ingestion_jobs_owner_status",
        "ingestion_jobs",
        ["owner_user_id", "status"],
    )

    _create_table(
        "chunks",
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
        ),
        _owner_fk(),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
    )
    op.create_index("ix_chunks_document_ordinal", "chunks", ["document_id", "ordinal"])

    _create_table(
        "embeddings",
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("chunks.id", ondelete="CASCADE")),
        _owner_fk(),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.JSON(), nullable=False),
    )

    _create_table(
        "document_tags",
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
        ),
        sa.Column("tag_id", sa.String(36), sa.ForeignKey("tags.id", ondelete="CASCADE")),
    )
    op.create_index(
        "ix_document_tags_unique", "document_tags", ["document_id", "tag_id"], unique=True
    )

    _create_table(
        "collection_documents",
        sa.Column(
            "collection_id",
            sa.String(36),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
        ),
    )
    op.create_index(
        "ix_collection_documents_unique",
        "collection_documents",
        ["collection_id", "document_id"],
        unique=True,
    )

    _create_table(
        "messages",
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        ),
        _owner_fk(),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
    )

    _create_table(
        "message_citations",
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
        ),
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("chunks.id", ondelete="CASCADE")),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("citation_metadata", sa.JSON(), nullable=False),
    )

    _create_table(
        "agent_runs",
        _owner_fk(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state", sa.String(60), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("trace_id", sa.String(160), nullable=True),
        sa.Column("budget", sa.JSON(), nullable=False),
    )

    _create_table(
        "agent_events",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_agent_events_run_sequence",
        "agent_events",
        ["run_id", "sequence_number"],
    )

    _create_table(
        "tool_calls",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        _owner_fk(),
        sa.Column("tool_name", sa.String(160), nullable=False),
        sa.Column("risk_class", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("redacted_arguments", sa.JSON(), nullable=False),
        sa.Column("redacted_result", sa.JSON(), nullable=True),
    )

    _create_table(
        "approvals",
        _owner_fk(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column(
            "tool_call_id",
            sa.String(36),
            sa.ForeignKey("tool_calls.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table(
        "skill_versions",
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("skills.id", ondelete="CASCADE")),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

    _create_table(
        "skill_tests",
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("skills.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("fixture", sa.JSON(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False),
    )

    _create_table(
        "mcp_capabilities",
        sa.Column(
            "server_id",
            sa.String(36),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        ),
        sa.Column("capability_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("schema", sa.JSON(), nullable=False),
        sa.Column("risk_class", sa.String(40), nullable=False),
    )

    _create_table(
        "user_feedback",
        _owner_fk(),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
    )

    _create_table(
        "evaluation_runs",
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        ),
        _owner_fk(),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
    )

    _create_table(
        "evaluation_results",
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        ),
        sa.Column("case_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("failure_detail", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    for table_name in reversed(
        [
            "users",
            "owner_settings",
            "auth_accounts",
            "sessions",
            "provider_configurations",
            "documents",
            "tags",
            "collections",
            "conversations",
            "skills",
            "mcp_servers",
            "evaluation_datasets",
            "audit_events",
            "document_versions",
            "ingestion_jobs",
            "chunks",
            "embeddings",
            "document_tags",
            "collection_documents",
            "messages",
            "message_citations",
            "agent_runs",
            "agent_events",
            "tool_calls",
            "approvals",
            "skill_versions",
            "skill_tests",
            "mcp_capabilities",
            "user_feedback",
            "evaluation_runs",
            "evaluation_results",
        ]
    ):
        op.drop_table(table_name)


def _create_table(name: str, *columns: sa.Column[str]) -> None:
    op.create_table(name, _id_column(), *_timestamp_columns(), *columns)


def _id_column() -> sa.Column[str]:
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamp_columns() -> tuple[sa.Column[datetime], sa.Column[datetime]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _owner_fk() -> sa.Column[str]:
    return sa.Column(
        "owner_user_id",
        sa.String(36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
