"""phase 5 observability and evaluation

Revision ID: 20260729_0005
Revises: 20260728_0004
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_spans",
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("trace_id", sa.String(160), nullable=False),
        sa.Column("span_id", sa.String(32), nullable=False),
        sa.Column("parent_span_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("component", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("sampled", sa.Boolean(), nullable=False),
        sa.Column("exporter_status", sa.String(40), nullable=False),
        sa.Column("exporter_error", sa.String(240), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telemetry_spans_trace_id", "telemetry_spans", ["trace_id"])
    op.create_index("ix_telemetry_spans_span_id", "telemetry_spans", ["span_id"])
    op.create_index(
        "ix_telemetry_spans_owner_created",
        "telemetry_spans",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_telemetry_spans_trace_created",
        "telemetry_spans",
        ["trace_id", "created_at"],
    )
    op.create_index(
        "ix_telemetry_spans_component_name",
        "telemetry_spans",
        ["component", "name"],
    )

    op.add_column("evaluation_datasets", sa.Column("dataset_metadata", sa.JSON(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("run_kind", sa.String(40), nullable=True))
    op.add_column("evaluation_runs", sa.Column("baseline_name", sa.String(160), nullable=True))
    op.add_column("evaluation_runs", sa.Column("threshold_profile", sa.JSON(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("report", sa.JSON(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("regression_count", sa.Integer(), nullable=True))
    op.add_column(
        "evaluation_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for column_name in reversed(
        [
            "run_kind",
            "baseline_name",
            "threshold_profile",
            "report",
            "regression_count",
            "started_at",
            "completed_at",
        ]
    ):
        op.drop_column("evaluation_runs", column_name)
    op.drop_column("evaluation_datasets", "dataset_metadata")

    op.drop_index("ix_telemetry_spans_component_name", table_name="telemetry_spans")
    op.drop_index("ix_telemetry_spans_trace_created", table_name="telemetry_spans")
    op.drop_index("ix_telemetry_spans_owner_created", table_name="telemetry_spans")
    op.drop_index("ix_telemetry_spans_span_id", table_name="telemetry_spans")
    op.drop_index("ix_telemetry_spans_trace_id", table_name="telemetry_spans")
    op.drop_table("telemetry_spans")
