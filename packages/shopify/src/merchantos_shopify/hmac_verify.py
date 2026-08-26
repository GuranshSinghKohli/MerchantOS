import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

from merchantos_domain import InvalidHmacError

_SKEW = timedelta(minutes=5)


def verify_oauth_hmac(query: dict[str, str], client_secret: str) -> None:
    """Callback HMAC: drop hmac, sort remaining params, HMAC-SHA256 hex.

    Official: https://shopify.dev/docs/apps/build/authentication-authorization/authenticate-standalone-apps
    """
    received = query.get("hmac")
    if not received:
        raise InvalidHmacError("missing OAuth hmac")
    message = "&".join(f"{key}={value}" for key, value in sorted(query.items()) if key != "hmac")
    digest = hmac.new(client_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, received):
        raise InvalidHmacError("invalid OAuth hmac")


def verify_oauth_query_string(query_string: str, client_secret: str) -> dict[str, str]:
    """Parse a raw query string (values as Shopify sent them) and verify HMAC."""
    pairs = parse_qsl(query_string, keep_blank_values=True)
    query = {key: value for key, value in pairs}
    verify_oauth_hmac(query, client_secret)
    return query


def verify_oauth_timestamp(timestamp_raw: str | None, *, now: datetime | None = None) -> None:
    if timestamp_raw is None:
        raise InvalidHmacError("missing OAuth timestamp")
    try:
        ts = datetime.fromtimestamp(int(timestamp_raw), tz=UTC)
    except (TypeError, ValueError) as exc:
        raise InvalidHmacError("invalid OAuth timestamp") from exc
    current = now or datetime.now(UTC)
    if abs(current - ts) > _SKEW:
        raise InvalidHmacError("OAuth timestamp outside 5-minute window")


def verify_webhook_hmac(raw_body: bytes, header_b64: str | None, client_secret: str) -> None:
    """Webhook HMAC: SHA256(body) as base64 vs X-Shopify-Hmac-SHA256."""
    if not header_b64:
        raise InvalidHmacError("missing webhook hmac")
    digest = hmac.new(client_secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    if not hmac.compare_digest(expected, header_b64):
        raise InvalidHmacError("invalid webhook hmac")


def verify_webhook_skew(triggered_at: str | None, *, now: datetime | None = None) -> None:
    if not triggered_at:
        raise InvalidHmacError("missing X-Shopify-Triggered-At")
    current = now or datetime.now(UTC)
    try:
        ts = datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
    except ValueError as exc:
        raise InvalidHmacError("invalid X-Shopify-Triggered-At") from exc
    if abs(current - ts) > _SKEW:
        raise InvalidHmacError("webhook timestamp outside 5-minute window")
