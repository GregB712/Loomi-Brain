"""phase 9 voice mode

Revision ID: 20260802_0008
Revises: 20260802_0007
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0008"
down_revision: str | None = "20260802_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_table(
        "voice_sessions",
        _owner_fk(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("stt_provider", sa.String(80), nullable=False),
        sa.Column("stt_model", sa.String(160), nullable=False),
        sa.Column("tts_provider", sa.String(80), nullable=True),
        sa.Column("tts_model", sa.String(160), nullable=True),
        sa.Column("tts_voice", sa.String(80), nullable=True),
        sa.Column("language", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False),
        sa.Column("retention_policy", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(160), nullable=True),
        sa.Column("trace_id", sa.String(160), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_voice_sessions_owner_created",
        "voice_sessions",
        ["owner_user_id", "created_at"],
    )
    op.create_index("ix_voice_sessions_conversation", "voice_sessions", ["conversation_id"])
    op.create_index("ix_voice_sessions_trace_id", "voice_sessions", ["trace_id"])

    _create_table(
        "voice_transcripts",
        sa.Column(
            "voice_session_id",
            sa.String(36),
            sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _owner_fk(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("language", sa.String(24), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(160), nullable=True),
        sa.Column("transcript_metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_voice_transcripts_session", "voice_transcripts", ["voice_session_id"])
    op.create_index(
        "ix_voice_transcripts_owner_created",
        "voice_transcripts",
        ["owner_user_id", "created_at"],
    )

    _create_table(
        "voice_audio_assets",
        sa.Column(
            "voice_session_id",
            sa.String(36),
            sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _owner_fk(),
        sa.Column("object_key", sa.String(512), nullable=True),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_audio_assets_session", "voice_audio_assets", ["voice_session_id"])
    op.create_index(
        "ix_voice_audio_assets_owner_deleted",
        "voice_audio_assets",
        ["owner_user_id", "deleted_at"],
    )

    _create_table(
        "voice_provider_events",
        sa.Column(
            "voice_session_id",
            sa.String(36),
            sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        _owner_fk(),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("trace_id", sa.String(160), nullable=True),
    )
    op.create_index(
        "ix_voice_provider_events_session",
        "voice_provider_events",
        ["voice_session_id"],
    )
    op.create_index(
        "ix_voice_provider_events_owner_created",
        "voice_provider_events",
        ["owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_provider_events_owner_created", table_name="voice_provider_events")
    op.drop_index("ix_voice_provider_events_session", table_name="voice_provider_events")
    op.drop_table("voice_provider_events")

    op.drop_index("ix_voice_audio_assets_owner_deleted", table_name="voice_audio_assets")
    op.drop_index("ix_voice_audio_assets_session", table_name="voice_audio_assets")
    op.drop_table("voice_audio_assets")

    op.drop_index("ix_voice_transcripts_owner_created", table_name="voice_transcripts")
    op.drop_index("ix_voice_transcripts_session", table_name="voice_transcripts")
    op.drop_table("voice_transcripts")

    op.drop_index("ix_voice_sessions_trace_id", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_conversation", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_owner_created", table_name="voice_sessions")
    op.drop_table("voice_sessions")


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
    return sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"))
