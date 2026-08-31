"""FORCE RLS on tenant tables and grant a non-bypass application role.

Revision ID: 0004_rls_force
Revises: 0003_phase3
Create Date: 2026-08-26

Compose POSTGRES_USER is a superuser (BYPASSRLS). ENABLE without FORCE is a
no-op for that role and for the table owner. FORCE makes tenant_scope bind
a non-superuser, non-BYPASSRLS role.

Privileged tables keep an unset-GUC path so shop-domain lookup, job-id load,
and unpublished outbox still work before TenantContext exists. Commerce
tables fail closed when the GUC is unset.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_rls_force"
down_revision: Union[str, None] = "0003_phase3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRIVILEGED_TABLES = (
    "stores",
    "merchant_users",
    "sessions",
    "shopify_credentials",
    "webhook_events",
    "audit_events",
    "sync_jobs",
    "outbox_messages",
)

COMMERCE_TABLES = (
    "products",
    "variants",
    "locations",
    "customers",
    "orders",
    "order_lines",
    "inventory_snapshots",
    "idempotency_keys",
)

UNSET_OR_MATCH = """
USING (
    NULLIF(current_setting('app.current_merchant_id', true), '') IS NULL
    OR merchant_id IS NULL
    OR merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::uuid
)
"""

MATCH_ONLY = """
USING (
    merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::uuid
)
"""

PHASE2_POLICY = """
USING (
    merchant_id IS NULL
    OR merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::uuid
)
"""


def _replace_policy(table: str, using_sql: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.execute(f"CREATE POLICY {table}_tenant ON {table} {using_sql}")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    for table in PRIVILEGED_TABLES:
        _replace_policy(table, UNSET_OR_MATCH)
    for table in COMMERCE_TABLES:
        _replace_policy(table, MATCH_ONLY)

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'merchantos_app') THEN
            CREATE ROLE merchantos_app LOGIN PASSWORD 'merchantos'
              NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
          END IF;
          -- RDS master cannot ALTER SUPERUSER/BYPASSRLS; CREATE already set them.
          BEGIN
            ALTER ROLE merchantos_app NOSUPERUSER NOBYPASSRLS;
          EXCEPTION
            WHEN insufficient_privilege THEN
              NULL;
          END;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          EXECUTE format(
            'GRANT CONNECT ON DATABASE %I TO merchantos_app',
            current_database()
          );
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO merchantos_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO merchantos_app"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO merchantos_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO merchantos_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO merchantos_app"
    )


def downgrade() -> None:
    for table in PRIVILEGED_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"CREATE POLICY {table}_tenant ON {table} {PHASE2_POLICY}")
    for table in COMMERCE_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"CREATE POLICY {table}_tenant ON {table} {MATCH_ONLY}")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM merchantos_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE USAGE, SELECT ON SEQUENCES FROM merchantos_app"
    )
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM merchantos_app"
    )
    op.execute("REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM merchantos_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM merchantos_app")
