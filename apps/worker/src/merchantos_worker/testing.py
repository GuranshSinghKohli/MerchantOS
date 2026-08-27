"""Test helpers. Not used on the production worker loop."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from merchantos_db.repositories import IdentityRepository, InstallView
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.port import ShopInfo
from sqlalchemy.orm import Session


def seed_installed_store(
    session: Session,
    *,
    shop: str,
    encryptor: TokenEncryptor,
    token: str = "shpua_test_token",
) -> InstallView:
    return IdentityRepository(session).persist_installation(
        shop_info=ShopInfo(
            shopify_shop_gid=f"gid://shopify/Shop/{shop}",
            name=shop.split(".")[0],
            myshopify_domain=shop,
            primary_host=shop,
            currency="USD",
            iana_timezone="UTC",
            plan_name="dev",
        ),
        encrypted_token=encryptor.encrypt(token),
        encrypted_refresh=None,
        token_expires_at=None,
        refresh_expires_at=None,
        scopes=(
            "read_products",
            "write_products",
            "read_orders",
            "read_customers",
            "read_inventory",
            "read_locations",
        ),
        key_version="test",
        session_ttl=datetime.now(UTC) + timedelta(hours=1),
        request_id=uuid4(),
    )
