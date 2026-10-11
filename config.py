"""Central configuration for BankMate AI.

All settings come from environment variables (loaded from .env if present),
with safe defaults so the project runs without any setup. No secrets here.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DISCLAIMER = (
    "BankMate AI is an independent educational simulation. All customer, account and "
    "transaction data is synthetic. It is not an official SBI or banking service, is "
    "not affiliated with or endorsed by SBI, and does not make real credit decisions."
)


def _get_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _get_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _get_list(name: str, default: str) -> tuple:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    # LLM
    ollama_base_url: str
    ollama_model: str
    ollama_timeout: int
    mock_llm: bool
    # Banking API
    bank_api_base_url: str
    bank_api_timeout: int
    demo_data_path: Path
    # RAG
    embedding_backend: str
    embedding_model: str
    chroma_dir: Path
    chroma_collection: str
    rag_top_k: int
    rag_max_distance: float
    chunk_size: int
    chunk_overlap: int
    docs_dir: Path
    model_cache_dir: Path
    # Risk rules
    risk_large_amount: float
    risk_burst_count: int
    risk_burst_window_minutes: int
    risk_repeat_count: int
    risk_demo_indicators: tuple
    # Loan demo rule
    loan_max_dti: float
    loan_min_residual_income: float
    loan_annual_interest_pct: float
    loan_default_tenure_months: int


def get_settings() -> Settings:
    """Build Settings from the current environment (re-read on every call so
    tests can override values with monkeypatch.setenv)."""
    return Settings(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct"),
        ollama_timeout=_get_int("OLLAMA_TIMEOUT_SECONDS", 90),
        mock_llm=os.getenv("BANKMATE_MOCK_LLM", "0") == "1",
        bank_api_base_url=os.getenv("BANK_API_BASE_URL", "http://localhost:8000"),
        bank_api_timeout=_get_int("BANK_API_TIMEOUT_SECONDS", 10),
        demo_data_path=BASE_DIR / "data" / "demo_data.json",
        embedding_backend=os.getenv("EMBEDDING_BACKEND", "sentence-transformers"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        chroma_dir=BASE_DIR / os.getenv("CHROMA_DIR", "chroma_db"),
        chroma_collection=os.getenv("CHROMA_COLLECTION", "sbi_public_docs"),
        rag_top_k=_get_int("RAG_TOP_K", 4),
        rag_max_distance=_get_float("RAG_MAX_DISTANCE", 0.70),
        chunk_size=_get_int("CHUNK_SIZE_CHARS", 900),
        chunk_overlap=_get_int("CHUNK_OVERLAP_CHARS", 150),
        docs_dir=BASE_DIR / "data" / "sbi_docs",
        model_cache_dir=BASE_DIR / ".cache" / "models",
        risk_large_amount=_get_float("RISK_LARGE_AMOUNT", 50000),
        risk_burst_count=_get_int("RISK_BURST_COUNT", 3),
        risk_burst_window_minutes=_get_int("RISK_BURST_WINDOW_MINUTES", 15),
        risk_repeat_count=_get_int("RISK_REPEAT_COUNT", 3),
        risk_demo_indicators=_get_list("RISK_DEMO_INDICATORS", "foreign_location,new_beneficiary"),
        loan_max_dti=_get_float("LOAN_MAX_DTI", 0.50),
        loan_min_residual_income=_get_float("LOAN_MIN_RESIDUAL_INCOME", 10000),
        loan_annual_interest_pct=_get_float("LOAN_ANNUAL_INTEREST_PCT", 10.5),
        loan_default_tenure_months=_get_int("LOAN_DEFAULT_TENURE_MONTHS", 36),
    )
