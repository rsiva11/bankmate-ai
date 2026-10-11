"""Ollama client error handling (requests is mocked; no Ollama needed)."""
import pytest
import requests

import llm


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_success(monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: FakeResp(200, {"message": {"content": '{"intents": []}'}}))
    assert llm.chat_json("s", "u") == '{"intents": []}'


def test_timeout(monkeypatch):
    def raise_timeout(*a, **k):
        raise requests.Timeout()
    monkeypatch.setattr(requests, "post", raise_timeout)
    with pytest.raises(llm.LLMTimeout):
        llm.chat_text("s", "u")


def test_service_unavailable(monkeypatch):
    def refuse(*a, **k):
        raise requests.ConnectionError()
    monkeypatch.setattr(requests, "post", refuse)
    with pytest.raises(llm.LLMUnavailable):
        llm.chat_text("s", "u")


def test_model_missing_and_server_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp(404))
    with pytest.raises(llm.LLMUnavailable, match="ollama pull"):
        llm.chat_text("s", "u")
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp(500))
    with pytest.raises(llm.LLMUnavailable):
        llm.chat_text("s", "u")


@pytest.mark.parametrize("payload", [{"unexpected": 1}, {"message": {"content": "  "}}])
def test_bad_shapes(monkeypatch, payload):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp(200, payload))
    with pytest.raises(llm.LLMInvalidOutput):
        llm.chat_text("s", "u")


def test_status_when_ollama_down(monkeypatch):
    def refuse(*a, **k):
        raise requests.ConnectionError()
    monkeypatch.setattr(requests, "get", refuse)
    assert llm.ollama_status()["running"] is False
