import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from merchantos_db import IdentityRepository, JobRepository, session_scope
from merchantos_domain import InvalidHmacError, InvalidShopDomainError
from merchantos_observability import get_logger
from merchantos_shopify.constants import COMMERCE_WEBHOOK_TOPICS, MANDATORY_WEBHOOK_TOPICS
from merchantos_shopify.hmac_verify import verify_webhook_hmac, verify_webhook_skew
from merchantos_shopify.shop_domain import normalize_shop_domain
from merchantos_shopify.webhook_ref import extract_webhook_ref

from merchantos_api.deps import db_engine, queue, settings
from merchantos_api.oauth_service import OAuthService
from merchantos_api.publisher import publish_unpublished
from merchantos_api.routers.auth import _service

router = APIRouter(prefix="/api/v1/webhooks/shopify", tags=["webhooks"])
logger = get_logger(__name__)


@router.post("/{topic:path}")
async def shopify_webhook(topic: str, request: Request) -> JSONResponse:
    cfg = settings()
    raw = await request.body()
    try:
        hmac_header = request.headers.get("x-shopify-hmac-sha256")
        verify_webhook_hmac(raw, hmac_header, cfg.shopify_api_secret)
        verify_webhook_skew(request.headers.get("x-shopify-triggered-at"))
        shop = normalize_shop_domain(request.headers.get("x-shopify-shop-domain") or "")
    except (InvalidHmacError, InvalidShopDomainError) as exc:
        logger.warning("webhook_rejected", topic=topic, error_type=type(exc).__name__)
        return JSONResponse(status_code=401, content={"status": "rejected"})

    event_id = request.headers.get("x-shopify-webhook-id") or hashlib.sha256(raw).hexdigest()
    payload_hash = hashlib.sha256(raw).hexdigest()
    request_id = str(getattr(request.state, "request_id", event_id))
    normalized_topic = (request.headers.get("x-shopify-topic") or topic).strip("/")
    resource_gid, payload_json = extract_webhook_ref(normalized_topic, raw)

    is_new = False
    with session_scope(db_engine()) as db:
        repo = IdentityRepository(db)
        event = repo.record_webhook(
            event_id=event_id,
            topic=normalized_topic,
            shop_domain=shop,
            payload_hash=payload_hash,
            resource_gid=resource_gid,
            payload_json=payload_json,
        )
        is_new = event is not None
        if is_new and event is not None and normalized_topic == "app/uninstalled":
            service: OAuthService = _service(db)
            service.handle_uninstall(shop, request_id)
        elif is_new and normalized_topic in MANDATORY_WEBHOOK_TOPICS:
            logger.info("compliance_webhook_acked", topic=normalized_topic, shop_domain=shop)
        elif is_new and event is not None and normalized_topic in COMMERCE_WEBHOOK_TOPICS:
            JobRepository(db).enqueue_webhook_job(event)

    if is_new and normalized_topic in COMMERCE_WEBHOOK_TOPICS:
        publish_unpublished(db_engine(), queue())

    logger.info(
        "webhook_received",
        topic=normalized_topic,
        shop_domain=shop,
        duplicate=not is_new,
        async_enqueued=is_new and normalized_topic in COMMERCE_WEBHOOK_TOPICS,
        at=datetime.now(UTC).isoformat(),
    )
    return JSONResponse(status_code=200, content={"status": "ok"})
