"""Shared fixtures: deterministic mock mode, in-process banking API, throw-away ChromaDB."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tools import banking_tools


@pytest.fixture(autouse=True)
def deterministic_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKMATE_MOCK_LLM", "1")
    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0.9")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    yield
    banking_tools.set_http_client(None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def bank(client):
    """Route banking_tools through the in-process API (no network needed)."""
    banking_tools.set_http_client(client)
    return client
