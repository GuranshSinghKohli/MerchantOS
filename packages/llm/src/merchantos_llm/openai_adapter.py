from collections.abc import Sequence
from typing import Any, TypeVar

from merchantos_domain import ConfigurationError, LLMTimeoutError, ProviderFailureError
from pydantic import BaseModel, ValidationError

from merchantos_llm.port import LLMMessage, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)

_UNSUPPORTED = frozenset(
    {
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "default",
        "pattern",
        "format",
        "uniqueItems",
        "examples",
        "minProperties",
        "maxProperties",
    }
)


def openai_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON Schema plus OpenAI structured-output constraints.

    OpenAI rejects `additionalProperties: true`, objects that omit `required`,
    siblings next to `$ref` (Pydantic puts `default` on enum fields), and
    several JSON Schema keywords (`minItems`, `maxLength`, …).
    """
    schema = model.model_json_schema()
    _lock_objects(schema)
    return schema


def _lock_objects(node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _lock_objects(item)
        return
    if not isinstance(node, dict):
        return
    for key in ("$defs", "definitions"):
        defs = node.get(key)
        if isinstance(defs, dict):
            for child in defs.values():
                _lock_objects(child)
    props = node.get("properties")
    if isinstance(props, dict):
        for child in props.values():
            _lock_objects(child)
    for key in ("items", "prefixItems", "anyOf", "oneOf", "allOf"):
        if key in node:
            _lock_objects(node[key])
    if "$ref" in node:
        ref = node["$ref"]
        node.clear()
        node["$ref"] = ref
        return
    for key in list(node):
        if key in _UNSUPPORTED:
            node.pop(key)
    extra = node.get("additionalProperties")
    is_object = node.get("type") == "object" or "properties" in node or extra not in (None, False)
    if not is_object:
        return
    if not isinstance(props, dict):
        props = {}
        node["properties"] = props
    node["additionalProperties"] = False
    node["required"] = list(props)


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
                        "schema": openai_strict_schema(schema),
                    },
                },
                timeout=timeout_seconds,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError("llm timed out") from exc
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            hint = str(exc).replace("\n", " ")[:180]
            detail = f"llm provider failed ({status}): {hint}" if status else "llm provider failed"
            raise ProviderFailureError(detail) from exc
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
