"""Phase 4 analytics indexes justified by dashboard aggregations.

Revision ID: 0005_phase4
Revises: 0004_rls_force
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_phase4"
down_revision: Union[str, None] = "0004_rls_force"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_orders_merchant_store_processed",
        "orders",
        ["merchant_id", "store_id", "processed_at"],
    )
    op.create_index(
        "ix_customers_merchant_first_order",
        "customers",
        ["merchant_id", "first_order_at"],
    )
    op.create_index(
        "ix_order_lines_merchant_order",
        "order_lines",
        ["merchant_id", "order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_order_lines_merchant_order", table_name="order_lines")
    op.drop_index("ix_customers_merchant_first_order", table_name="customers")
    op.drop_index("ix_orders_merchant_store_processed", table_name="orders")
