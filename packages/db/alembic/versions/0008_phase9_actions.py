"""Phase 9 actions, approvals, and action results.

Revision ID: 0008_phase9
Revises: 0007_phase8
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase9"
down_revision: Union[str, None] = "0007_phase8"
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
    op.add_column(
        "products",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "actions",
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
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="PROPOSED"),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_gid", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_recommendation_id", sa.Text()),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("before_state_json", sa.Text(), nullable=False),
        sa.Column("after_state_json", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("merchant_id", "idempotency_key"),
    )
    op.create_index("ix_actions_merchant_created", "actions", ["merchant_id", "created_at"])
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchants.id"),
            nullable=False,
        ),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("frozen_payload_hash", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchant_users.id"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "action_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchants.id"),
            nullable=False,
        ),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutation_name", sa.Text(), nullable=False),
        sa.Column("shopify_request_id", sa.Text()),
        sa.Column("error_code", sa.Text()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("before_state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("response_redacted", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for table, policy in (
        ("actions", UNSET_OR_MATCH),
        ("approvals", MATCH_ONLY),
        ("action_results", MATCH_ONLY),
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant ON {table} {policy}")


def downgrade() -> None:
    for table in ("action_results", "approvals", "actions"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("action_results")
    op.drop_table("approvals")
    op.drop_index("ix_actions_merchant_created", table_name="actions")
    op.drop_table("actions")
    op.drop_column("products", "description")
