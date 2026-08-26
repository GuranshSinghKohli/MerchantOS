import base64
import hashlib
import hmac
from datetime import UTC, datetime

import pytest
from merchantos_domain import InvalidHmacError
from merchantos_shopify.hmac_verify import (
    verify_oauth_hmac,
    verify_oauth_timestamp,
    verify_webhook_hmac,
    verify_webhook_skew,
)

SECRET = "shpss_test_secret"


def _oauth_query(extra: dict[str, str] | None = None) -> dict[str, str]:
    query = {
        "code": "abc",
        "shop": "acme.myshopify.com",
        "state": "nonce",
        "timestamp": "1710000000",
    }
    if extra:
        query.update(extra)
    message = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    query["hmac"] = hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return query


def test_oauth_hmac_accepts_valid() -> None:
    verify_oauth_hmac(_oauth_query(), SECRET)


def test_oauth_hmac_rejects_tamper() -> None:
    query = _oauth_query()
    query["shop"] = "other.myshopify.com"
    with pytest.raises(InvalidHmacError):
        verify_oauth_hmac(query, SECRET)


def test_oauth_timestamp_skew() -> None:
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    with pytest.raises(InvalidHmacError):
        verify_oauth_timestamp(str(int(now.timestamp()) - 400), now=now)


def test_webhook_hmac() -> None:
    body = b'{"id":1}'
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    header = base64.b64encode(digest).decode()
    verify_webhook_hmac(body, header, SECRET)
    with pytest.raises(InvalidHmacError):
        verify_webhook_hmac(body, header, "wrong")
    with pytest.raises(InvalidHmacError):
        verify_webhook_hmac(body, None, SECRET)


def test_webhook_skew() -> None:
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    verify_webhook_skew("2026-08-25T12:00:00Z", now=now)
    with pytest.raises(InvalidHmacError):
        verify_webhook_skew("2026-08-25T11:00:00Z", now=now)
