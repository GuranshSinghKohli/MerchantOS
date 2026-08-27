class DomainError(Exception):
    """Base typed domain error. Never swallow; map to HTTP at the API edge."""

    http_status: int = 400


class ForbiddenFactoryError(DomainError):
    """Raised when a security-sensitive type is constructed without a trusted factory."""

    http_status = 403


class UnauthorizedError(DomainError):
    http_status = 401


class InvalidHmacError(DomainError):
    http_status = 401


class InvalidOAuthStateError(DomainError):
    http_status = 403


class InvalidShopDomainError(DomainError):
    http_status = 400


class InvalidDateRangeError(DomainError):
    http_status = 400


class InstallationFailedError(DomainError):
    http_status = 400


class StoreUninstalledError(DomainError):
    http_status = 403


class ConfigurationError(DomainError):
    http_status = 503


class TransientJobError(DomainError):
    """Retryable worker failure. Do not ack the queue message."""

    http_status = 503


class ShopifyThrottledError(TransientJobError):
    """Shopify leaky-bucket throttle (HTTP 429 or GraphQL THROTTLED)."""


class LLMTimeoutError(TransientJobError):
    http_status = 504


class ProviderFailureError(TransientJobError):
    http_status = 503


class InvalidModelOutputError(DomainError):
    http_status = 422


class AgentCancelledError(DomainError):
    http_status = 409


class NotFoundError(DomainError):
    http_status = 404


class NotApprovedError(DomainError):
    http_status = 409


class ActionExpiredError(DomainError):
    http_status = 409


class ActionConflictError(DomainError):
    http_status = 409


class InvalidActionError(DomainError):
    http_status = 422
