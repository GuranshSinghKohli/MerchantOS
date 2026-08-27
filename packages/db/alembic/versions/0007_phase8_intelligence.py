"""Phase 8 intelligence run kind on agent_runs.

Revision ID: 0007_phase8
Revises: 0006_phase6
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase8"
down_revision: Union[str, None] = "0006_phase6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("run_kind", sa.Text(), nullable=False, server_default="ask"),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "run_kind")
