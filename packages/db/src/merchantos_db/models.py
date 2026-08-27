from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from merchantos_db.ids import uuid7


class Base(DeclarativeBase):
    pass


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    shop_domain: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    myshopify_domain: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    shopify_shop_gid: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD")
    iana_timezone: Mapped[str] = mapped_column(Text, nullable=False, default="UTC")
    plan_name: Mapped[str | None] = mapped_column(Text)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(Text, nullable=False, default="not_started")
    sync_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MerchantUser(Base):
    __tablename__ = "merchant_users"
    __table_args__ = (UniqueConstraint("merchant_id", "email"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchant_users.id")
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShopifyCredential(Base):
    __tablename__ = "shopify_credentials"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), unique=True, nullable=False
    )
    encrypted_offline_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    key_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    state: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    shop_domain: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id")
    )
    store_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("stores.id"))
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    shop_domain: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resource_gid: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="received")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("merchant_id", "shopify_gid"),
        Index("ix_products_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    shopify_gid: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    vendor: Mapped[str] = mapped_column(Text, nullable=False, default="")
    product_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (UniqueConstraint("merchant_id", "shopify_gid"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    shopify_gid: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    inventory_item_gid: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("merchant_id", "shopify_gid"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    shopify_gid: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("merchant_id", "shopify_gid"),
        Index("ix_customers_merchant_last_order", "merchant_id", "last_order_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    shopify_gid: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    orders_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="")
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("merchant_id", "shopify_gid"),
        Index("ix_orders_merchant_processed", "merchant_id", "processed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id")
    )
    shopify_gid: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    financial_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fulfillment_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_discounts: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (UniqueConstraint("merchant_id", "shopify_gid"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    variant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("variants.id"))
    shopify_gid: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_allocation: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    cost_at_sale: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        UniqueConstraint("merchant_id", "variant_id", "location_id", "captured_at"),
        Index("ix_inventory_merchant_captured", "merchant_id", "captured_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("variants.id"), nullable=False
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    available: Mapped[int] = mapped_column(Integer, nullable=False)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (UniqueConstraint("merchant_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchant_users.id")
    )
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    cursor: Mapped[str | None] = mapped_column(Text)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_merchant_created", "merchant_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchant_users.id")
    )
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    run_kind: Mapped[str] = mapped_column(Text, nullable=False, default="ask")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    classification: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ToolCallRecord(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_run", "merchant_id", "run_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="LOW")
    permission: Mapped[str] = mapped_column(Text, nullable=False)
    input_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (Index("ix_outbox_unpublished", "published_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    job_kind: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("merchant_id", "idempotency_key"),
        Index("ix_actions_merchant_created", "merchant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stores.id"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchant_users.id")
    )
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PROPOSED")
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    resource_gid: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_recommendation_id: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    before_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    after_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("action_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    action_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("actions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    frozen_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchant_users.id"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionResultRow(Base):
    __tablename__ = "action_results"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    action_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("actions.id"), nullable=False, unique=True
    )
    ok: Mapped[bool] = mapped_column(nullable=False, default=False)
    mutation_name: Mapped[str] = mapped_column(Text, nullable=False)
    shopify_request_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    before_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    after_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    response_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("merchant_id", "scope", "key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    merchant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    response_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
