from enum import StrEnum

from merchantos_domain import DomainError


class ToolErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    TENANT_MISMATCH = "tenant_mismatch"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    DEPENDENCY_FAILURE = "dependency_failure"
    RATE_LIMIT = "rate_limit"
    INTERNAL_FAILURE = "internal_failure"
    UNKNOWN_TOOL = "unknown_tool"
    TOOL_NOT_ALLOWED = "tool_not_allowed"


class ToolError(DomainError):
    """Safe tool failure. message is merchant/agent-safe; never a stack trace."""

    def __init__(
        self, code: ToolErrorCode, message: str, *, http_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status if http_status is not None else _STATUS[code]


class UnknownTool(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(ToolErrorCode.UNKNOWN_TOOL, f"unknown tool: {name}")


class ToolNotAllowed(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(ToolErrorCode.TOOL_NOT_ALLOWED, f"tool is not allowlisted: {name}")


_STATUS: dict[ToolErrorCode, int] = {
    ToolErrorCode.INVALID_INPUT: 400,
    ToolErrorCode.UNAUTHORIZED: 401,
    ToolErrorCode.FORBIDDEN: 403,
    ToolErrorCode.TENANT_MISMATCH: 403,
    ToolErrorCode.NOT_FOUND: 404,
    ToolErrorCode.TIMEOUT: 504,
    ToolErrorCode.DEPENDENCY_FAILURE: 503,
    ToolErrorCode.RATE_LIMIT: 429,
    ToolErrorCode.INTERNAL_FAILURE: 500,
    ToolErrorCode.UNKNOWN_TOOL: 404,
    ToolErrorCode.TOOL_NOT_ALLOWED: 403,
}
