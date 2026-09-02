from enum import StrEnum
from typing import Any

from merchantos_llm.openai_adapter import openai_strict_schema
from pydantic import BaseModel, Field


class _Band(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class _ToolReq(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class _Plan(BaseModel):
    plan: str
    tools: list[_ToolReq]
    insufficient_data: bool = False


class _Synthesis(BaseModel):
    summary: str = ""
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    proposed_confidence: _Band = _Band.MEDIUM


def _walk(node: object) -> list[object]:
    if isinstance(node, list):
        found: list[object] = []
        for item in node:
            found.extend(_walk(item))
        return found
    if not isinstance(node, dict):
        return []
    found = [node]
    for value in node.values():
        found.extend(_walk(value))
    return found


def test_openai_strict_schema_locks_freeform_objects() -> None:
    schema = openai_strict_schema(_Plan)
    objects = [
        node
        for node in _walk(schema)
        if isinstance(node, dict) and (node.get("type") == "object" or "properties" in node)
    ]
    assert objects
    for node in objects:
        assert node.get("additionalProperties") is False
        assert "required" in node
        assert set(node["required"]) == set(node.get("properties") or {})


def test_openai_strict_schema_strips_ref_siblings_and_constraints() -> None:
    schema = openai_strict_schema(_Synthesis)
    confidence = schema["properties"]["proposed_confidence"]
    assert confidence == {"$ref": "#/$defs/_Band"}
    evidence = schema["properties"]["evidence_ids"]
    assert "minItems" not in evidence
    assert "maxItems" not in evidence
    assert "default" not in schema["properties"]["summary"]
