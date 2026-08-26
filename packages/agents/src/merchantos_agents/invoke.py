from __future__ import annotations

from typing import Any

from merchantos_domain import InvalidModelOutputError, LLMTimeoutError, ProviderFailureError
from merchantos_llm import LLMMessage, LLMPort
from merchantos_observability import get_logger
from pydantic import BaseModel, ValidationError

logger = get_logger(__name__)

LLM_TIMEOUT = 8.0
LLM_OUTPUT_RETRIES = 2


def complete_llm[T: BaseModel](
    llm: LLMPort,
    schema: type[T],
    *,
    system: str,
    user: str,
) -> tuple[T, int, int, str, int]:
    messages = (
        LLMMessage(role="system", content=system),
        LLMMessage(role="user", content=user[:12000]),
    )
    last_error: Exception | None = None
    for attempt in range(LLM_OUTPUT_RETRIES + 1):
        try:
            result = llm.complete(messages, schema, timeout_seconds=LLM_TIMEOUT)
            return (
                result.data,
                result.usage.input_tokens,
                result.usage.output_tokens,
                result.usage.model,
                attempt,
            )
        except ValidationError as exc:
            last_error = exc
            logger.info(
                "llm_invalid_output",
                attempt=attempt + 1,
                error_category="invalid_model_output",
            )
        except (LLMTimeoutError, ProviderFailureError):
            raise
    raise InvalidModelOutputError("model output failed schema validation") from last_error


def add_usage(
    state: Any,
    *,
    input_tokens: int,
    output_tokens: int,
    model: str,
    retries: int,
) -> dict[str, Any]:
    return {
        "token_input": state.token_input + input_tokens,
        "token_output": state.token_output + output_tokens,
        "model": model,
        "llm_retries": state.llm_retries + retries,
    }
