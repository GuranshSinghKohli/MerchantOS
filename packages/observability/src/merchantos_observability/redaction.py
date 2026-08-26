from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "access_token",
        "offline_token",
        "id_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "token",
        "hmac",
        "x-shopify-access-token",
        "aws_secret_access_key",
        "client_secret",
    }
)


def _is_sensitive(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in _SENSITIVE_KEYS:
        return True
    return any(part in normalized for part in ("secret", "token", "password", "hmac"))


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive(str(key)):
            redacted[key] = REDACTED
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted
