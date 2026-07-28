from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from loomi_api.db.base import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OwnerSetting(IdMixin, TimestampMixin, Base):
    __tablename__ = "owner_settings"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_owner_settings_owner_key", "owner_user_id", "key"),)


class AuthAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "auth_accounts"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(80), default="local")
    provider_subject: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_auth_accounts_provider_subject",
            "provider",
            "provider_subject",
            unique=True,
        ),
    )


class OwnerSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderConfiguration(IdMixin, TimestampMixin, Base):
    __tablename__ = "provider_configurations"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    source_kind: Mapped[str] = mapped_column(String(40), default="upload")
    status: Mapped[str] = mapped_column(String(40), default="created")
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_documents_owner_status", "owner_user_id", "status"),)


class DocumentVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(512))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    media_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extraction_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IngestionJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(40), default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="created")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)

    __table_args__ = (Index("ix_ingestion_jobs_owner_status", "owner_user_id", "status"),)


class Chunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "chunks"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_chunks_document_ordinal", "document_id", "ordinal"),)


class Embedding(IdMixin, TimestampMixin, Base):
    __tablename__ = "embeddings"

    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(160))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector_json: Mapped[list[float]] = mapped_column(JSON, default=list)


class Tag(IdMixin, TimestampMixin, Base):
    __tablename__ = "tags"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))

    __table_args__ = (Index("ix_tags_owner_name", "owner_user_id", "name", unique=True),)


class DocumentTag(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_tags"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"))

    __table_args__ = (Index("ix_document_tags_unique", "document_id", "tag_id", unique=True),)


class Collection(IdMixin, TimestampMixin, Base):
    __tablename__ = "collections"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CollectionDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "collection_documents"

    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))

    __table_args__ = (
        Index(
            "ix_collection_documents_unique",
            "collection_id",
            "document_id",
            unique=True,
        ),
    )


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MessageCitation(IdMixin, TimestampMixin, Base):
    __tablename__ = "message_citations"

    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AgentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(60), default="created")
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AgentEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_events"

    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(80))
    sequence_number: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_agent_events_run_sequence", "run_id", "sequence_number"),)


class ToolCall(IdMixin, TimestampMixin, Base):
    __tablename__ = "tool_calls"

    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tool_name: Mapped[str] = mapped_column(String(160))
    risk_class: Mapped[str] = mapped_column(String(40), default="read")
    status: Mapped[str] = mapped_column(String(40), default="created")
    redacted_arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    redacted_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Approval(IdMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    tool_call_id: Mapped[str | None] = mapped_column(
        ForeignKey("tool_calls.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), default="pending")
    policy_version: Mapped[str] = mapped_column(String(80), default="phase1")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Skill(IdMixin, TimestampMixin, Base):
    __tablename__ = "skills"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(40), default="draft")
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class SkillVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "skill_versions"

    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(String(40))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SkillTest(IdMixin, TimestampMixin, Base):
    __tablename__ = "skill_tests"

    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    fixture: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MCPServer(IdMixin, TimestampMixin, Base):
    __tablename__ = "mcp_servers"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    transport: Mapped[str] = mapped_column(String(40))
    command_template: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MCPCapability(IdMixin, TimestampMixin, Base):
    __tablename__ = "mcp_capabilities"

    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id", ondelete="CASCADE"))
    capability_type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_class: Mapped[str] = mapped_column(String(40), default="read")


class AuditEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UserFeedback(IdMixin, TimestampMixin, Base):
    __tablename__ = "user_feedback"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvaluationDataset(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_datasets"

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvaluationRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_runs"

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE")
    )
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(40), default="created")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EvaluationResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_results"

    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"))
    case_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
