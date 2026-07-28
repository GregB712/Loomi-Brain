"""phase 4 agent runtime fields

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("agent_runs", sa.Column("run_kind", sa.String(40), nullable=True))
    op.add_column("agent_runs", sa.Column("status_reason", sa.String(160), nullable=True))
    op.add_column("agent_runs", sa.Column("owner_request", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("provider", sa.String(80), nullable=True))
    op.add_column("agent_runs", sa.Column("model", sa.String(160), nullable=True))
    op.add_column("agent_runs", sa.Column("allowed_tools", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("limits", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("usage", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("sanitized_input", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("sanitized_output", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("retry_count", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("agent_runs", sa.Column("last_error", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("trace_metadata", sa.JSON(), nullable=True))
    op.create_index("ix_agent_runs_kind_state", "agent_runs", ["run_kind", "state"])
    op.create_index("ix_agent_runs_idempotency", "agent_runs", ["owner_user_id", "idempotency_key"])

    op.add_column("tool_calls", sa.Column("tool_id", sa.String(160), nullable=True))
    op.add_column("tool_calls", sa.Column("input_schema", sa.JSON(), nullable=True))
    op.add_column("tool_calls", sa.Column("output_schema", sa.JSON(), nullable=True))
    op.add_column("tool_calls", sa.Column("arguments_hash", sa.String(64), nullable=True))
    op.add_column("tool_calls", sa.Column("idempotency_key", sa.String(180), nullable=True))
    op.add_column("tool_calls", sa.Column("policy_decision", sa.JSON(), nullable=True))
    op.add_column("tool_calls", sa.Column("timeout_seconds", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("output_size_limit", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("retry_count", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tool_calls",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("tool_calls", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("tool_calls", sa.Column("error_code", sa.String(120), nullable=True))
    op.add_column("tool_calls", sa.Column("trace_id", sa.String(160), nullable=True))
    op.create_index(
        "ix_tool_calls_run_tool_hash",
        "tool_calls",
        ["run_id", "tool_id", "arguments_hash"],
    )

    op.add_column("approvals", sa.Column("tool_id", sa.String(160), nullable=True))
    op.add_column("approvals", sa.Column("arguments_hash", sa.String(64), nullable=True))
    op.add_column("approvals", sa.Column("risk_class", sa.String(40), nullable=True))
    if bind.dialect.name == "sqlite":
        op.add_column(
            "approvals",
            sa.Column("decided_by_user_id", sa.String(36), nullable=True),
        )
    else:
        op.add_column(
            "approvals",
            sa.Column(
                "decided_by_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    op.add_column("approvals", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("approvals", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("approvals", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("approvals", sa.Column("denial_reason", sa.Text(), nullable=True))
    op.add_column("approvals", sa.Column("approval_metadata", sa.JSON(), nullable=True))
    op.create_index(
        "ix_approvals_owner_status_expires",
        "approvals",
        ["owner_user_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_approvals_run_tool_hash",
        "approvals",
        ["run_id", "tool_id", "arguments_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_approvals_run_tool_hash", table_name="approvals")
    op.drop_index("ix_approvals_owner_status_expires", table_name="approvals")
    for column_name in reversed(
        [
            "tool_id",
            "arguments_hash",
            "risk_class",
            "decided_by_user_id",
            "used_at",
            "expired_at",
            "cancelled_at",
            "denial_reason",
            "approval_metadata",
        ]
    ):
        op.drop_column("approvals", column_name)

    op.drop_index("ix_tool_calls_run_tool_hash", table_name="tool_calls")
    for column_name in reversed(
        [
            "tool_id",
            "input_schema",
            "output_schema",
            "arguments_hash",
            "idempotency_key",
            "policy_decision",
            "timeout_seconds",
            "output_size_limit",
            "retry_count",
            "started_at",
            "completed_at",
            "latency_ms",
            "error_code",
            "trace_id",
        ]
    ):
        op.drop_column("tool_calls", column_name)

    op.drop_index("ix_agent_runs_idempotency", table_name="agent_runs")
    op.drop_index("ix_agent_runs_kind_state", table_name="agent_runs")
    for column_name in reversed(
        [
            "run_kind",
            "status_reason",
            "owner_request",
            "provider",
            "model",
            "allowed_tools",
            "limits",
            "usage",
            "sanitized_input",
            "sanitized_output",
            "retry_count",
            "latency_ms",
            "started_at",
            "completed_at",
            "cancel_requested_at",
            "last_error",
            "trace_metadata",
        ]
    ):
        op.drop_column("agent_runs", column_name)
