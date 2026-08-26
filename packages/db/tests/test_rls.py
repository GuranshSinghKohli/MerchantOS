import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from merchantos_db import create_db_engine, session_scope
from merchantos_db.models import Base
from sqlalchemy import text
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[3]


def _require_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for integration tests")
    return url


def _app_role_url(owner_url: str) -> str:
    return make_url(owner_url).set(username="merchantos_app").render_as_string(hide_password=False)


def _upgrade_and_truncate(owner_url: str) -> None:
    alembic_cfg = Config(str(ROOT / "packages/db/alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(ROOT / "packages/db/alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", owner_url)
    command.upgrade(alembic_cfg, "head")
    engine = create_db_engine(owner_url)
    with session_scope(engine) as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))


@pytest.mark.integration
def test_compose_owner_is_superuser_and_bypasses_rls() -> None:
    owner_url = _require_database_url()
    _upgrade_and_truncate(owner_url)
    engine = create_db_engine(owner_url)
    with session_scope(engine) as session:
        role = session.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert role.rolsuper is True
        assert role.rolbypassrls is True
        forced = session.execute(
            text(
                "SELECT relforcerowsecurity FROM pg_class "
                "WHERE relname = 'products' AND relkind = 'r'"
            )
        ).scalar_one()
        assert forced is True


@pytest.mark.integration
def test_app_role_cannot_bypass_forced_rls() -> None:
    owner_url = _require_database_url()
    _upgrade_and_truncate(owner_url)
    merchant_a, merchant_b = uuid4(), uuid4()
    store_a, store_b = uuid4(), uuid4()
    product_a, product_b = uuid4(), uuid4()

    owner = create_db_engine(owner_url)
    with session_scope(owner) as session:
        app_role = session.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'merchantos_app'")
        ).one()
        assert app_role.rolsuper is False
        assert app_role.rolbypassrls is False
        for merchant_id, name in ((merchant_a, "alpha"), (merchant_b, "beta")):
            session.execute(
                text("INSERT INTO merchants (id, name, status) VALUES (:id, :name, 'active')"),
                {"id": merchant_id, "name": name},
            )
        for store_id, merchant_id, shop in (
            (store_a, merchant_a, "alpha.myshopify.com"),
            (store_b, merchant_b, "beta.myshopify.com"),
        ):
            session.execute(
                text(
                    "INSERT INTO stores "
                    "(id, merchant_id, shop_domain, myshopify_domain, currency, "
                    "iana_timezone, sync_status) "
                    "VALUES (:id, :mid, :shop, :shop, 'USD', 'UTC', 'not_started')"
                ),
                {"id": store_id, "mid": merchant_id, "shop": shop},
            )
        for product_id, merchant_id, store_id, gid in (
            (product_a, merchant_a, store_a, "gid://shopify/Product/1"),
            (product_b, merchant_b, store_b, "gid://shopify/Product/2"),
        ):
            session.execute(
                text(
                    "INSERT INTO products "
                    "(id, merchant_id, store_id, shopify_gid, title, status, "
                    "vendor, product_type, tags) "
                    "VALUES (:id, :mid, :sid, :gid, :title, 'active', '', '', '{}')"
                ),
                {
                    "id": product_id,
                    "mid": merchant_id,
                    "sid": store_id,
                    "gid": gid,
                    "title": gid,
                },
            )

    app = create_db_engine(_app_role_url(owner_url))
    with session_scope(app) as session:
        unscoped_products = (
            session.execute(text("SELECT shopify_gid FROM products")).scalars().all()
        )
        assert unscoped_products == []
        unscoped_stores = session.execute(text("SELECT shop_domain FROM stores")).scalars().all()
        assert set(unscoped_stores) == {"alpha.myshopify.com", "beta.myshopify.com"}

        session.execute(
            text("SELECT set_config('app.current_merchant_id', :mid, true)"),
            {"mid": str(merchant_a)},
        )
        scoped_products = session.execute(text("SELECT shopify_gid FROM products")).scalars().all()
        assert scoped_products == ["gid://shopify/Product/1"]
        scoped_stores = session.execute(text("SELECT shop_domain FROM stores")).scalars().all()
        assert scoped_stores == ["alpha.myshopify.com"]
