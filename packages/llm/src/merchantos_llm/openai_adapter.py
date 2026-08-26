from collections.abc import Sequence
from typing import TypeVar

from merchantos_domain import ConfigurationError, LLMTimeoutError, ProviderFailureError
from pydantic import BaseModel, ValidationError

from merchantos_llm.port import LLMMessage, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


class OpenAIAdapter:
    """Thin OpenAI adapter. API key stays in the client, never in messages or results."""

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise ConfigurationError("OPENAI_API_KEY is required for the OpenAI adapter")
        self._api_key = api_key
        self._model = model

    def complete(
        self,
        messages: Sequence[LLMMessage],
        schema: type[T],
        *,
        timeout_seconds: float,
    ) -> LLMResult[T]:
        try:
            from openai import APITimeoutError, OpenAI
        except ImportError as exc:
            raise ConfigurationError("openai package is not installed") from exc
        client = OpenAI(api_key=self._api_key, timeout=timeout_seconds)
        try:
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=self._model,
                messages=[{"role": item.role, "content": item.content} for item in messages],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
                timeout=timeout_seconds,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError("llm timed out") from exc
        except Exception as exc:
            raise ProviderFailureError("llm provider failed") from exc
        content = response.choices[0].message.content or ""
        usage = response.usage
        try:
            data = schema.model_validate_json(content)
        except ValidationError as exc:
            raise exc
        return LLMResult(
            data=data,
            usage=LLMUsage(
                model=self._model,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                estimated_cost_usd=None,
            ),
        )
