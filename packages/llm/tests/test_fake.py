import pytest
from merchantos_domain import LLMTimeoutError, ProviderFailureError
from merchantos_llm import FakeLLM, FakeTurn, LLMMessage
from pydantic import BaseModel, ValidationError


class _Out(BaseModel):
    answer: str


def test_fake_llm_returns_scripted_output() -> None:
    llm = FakeLLM([FakeTurn({"answer": "hello"})])
    result = llm.complete([LLMMessage(role="user", content="q")], _Out, timeout_seconds=1)
    assert result.data.answer == "hello"
    assert result.usage.model == "fake"
    assert len(llm.calls) == 1


def test_fake_llm_invalid_output_and_timeout() -> None:
    llm = FakeLLM([FakeTurn({"nope": True})])
    with pytest.raises(ValidationError):
        llm.complete([LLMMessage(role="user", content="q")], _Out, timeout_seconds=1)
    timed = FakeLLM([FakeTurn({"answer": "late"}, delay_seconds=5)])
    with pytest.raises(LLMTimeoutError):
        timed.complete([LLMMessage(role="user", content="q")], _Out, timeout_seconds=0.01)
    failing = FakeLLM([FakeTurn(error=ProviderFailureError("down"))])
    with pytest.raises(ProviderFailureError):
        failing.complete([LLMMessage(role="user", content="q")], _Out, timeout_seconds=1)
