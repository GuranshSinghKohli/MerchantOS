class DomainError(Exception):
    """Base typed domain error. Never swallow; map to HTTP at the API edge."""


class ForbiddenFactoryError(DomainError):
    """Raised when a security-sensitive type is constructed without a trusted factory."""
