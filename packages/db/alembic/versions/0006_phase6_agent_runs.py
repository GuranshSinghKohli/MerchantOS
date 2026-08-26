"""Phase 6 agent run persistence and tool call audit.

Revision ID: 0006_phase6
Revises: 0005_phase4
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase6"
down_revision: Union[str, None] = "0005_phase4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNSET_OR_MATCH = """
USING (
    NULLIF(current_setting('app.current_merchant_id', true), '') IS NULL
    OR merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::uuid
)
"""

MATCH_ONLY = """
USING (
    merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::uuid
)
"""


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchants.id"),
            nullable=False,
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stores.id"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchant_users.id")),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("classification", sa.Text()),
        sa.Column("plan", sa.Text()),
        sa.Column("result_json", sa.Text()),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("error_code", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_runs_merchant_created", "agent_runs", ["merchant_id", "created_at"])

    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchants.id"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False, server_default="LOW"),
        sa.Column("permission", sa.Text(), nullable=False),
        sa.Column("input_redacted", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_redacted", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_code", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tool_calls_run", "tool_calls", ["merchant_id", "run_id"])

    op.execute("ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_runs FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY agent_runs_tenant ON agent_runs {UNSET_OR_MATCH}")
    op.execute("ALTER TABLE tool_calls ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tool_calls FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tool_calls_tenant ON tool_calls {MATCH_ONLY}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tool_calls_tenant ON tool_calls")
    op.execute("DROP POLICY IF EXISTS agent_runs_tenant ON agent_runs")
    op.drop_index("ix_tool_calls_run", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index("ix_agent_runs_merchant_created", table_name="agent_runs")
    op.drop_table("agent_runs")
