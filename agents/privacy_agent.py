"""Privacy Knowledge Agent: answers ONLY from retrieved public SBI document passages."""
from typing import Optional

import llm
from agents.base import AgentResult, TraceStep
from config import get_settings
from rag.retriever import EmbeddingMismatch, KnowledgeBaseNotReady, Retriever

NAME = "Privacy Knowledge Agent"

INSUFFICIENT = ("The current knowledge base does not contain enough information to answer this. "
                "I don't want to guess about SBI policies. Try rephrasing, or add more official "
                "documents with the ingest command.")

SYSTEM_PROMPT = (
    "You answer questions about publicly available SBI privacy information using ONLY the numbered "
    "context passages provided. Rules: (1) If the passages do not answer the question, say the "
    "available documents do not contain enough information. (2) Never add facts, policies, dates or "
    "quotes that are not in the passages. (3) Cite passages like [1] or [2]. (4) Be concise: at most "
    "5 sentences. (5) You are an educational demo, not SBI, and have no access to confidential systems."
)


def _extractive_answer(chunks: list) -> str:
    lines = ["Most relevant passages from the public documents:"]
    for i, c in enumerate(chunks[:2], start=1):
        text = c.text if len(c.text) <= 350 else c.text[:350].rsplit(" ", 1)[0] + "…"
        lines.append(f"- {text} [{i}]")
    return "\n".join(lines)


def _source_entry(i: int, c) -> dict:
    m = c.metadata
    return {
        "id": i,
        "title": m.get("document_title", "Unknown document"),
        "url": m.get("source_url", ""),
        "section": m.get("section_title"),
        "page": m.get("page"),
        "retrieval_date": m.get("retrieval_date"),
        "excerpt": c.text,
        "distance": round(c.distance, 3),
    }


def answer_question(question: str, retriever: Optional[Retriever] = None) -> AgentResult:
    res = AgentResult(NAME)
    question = (question or "").strip()[:500]
    if not question:
        res.ok = False
        res.error = "Please type a privacy question."
        return res
    retriever = retriever or Retriever()
    try:
        chunks = retriever.retrieve(question)
    except (KnowledgeBaseNotReady, EmbeddingMismatch) as exc:
        res.ok = False
        res.error = str(exc)
        res.trace.append(TraceStep(NAME, "retrieve_passages", "error", str(exc)))
        return res
    except (ImportError, OSError) as exc:
        res.ok = False
        res.error = ("Embedding model could not be loaded (needs a first-time download or installed "
                     f"sentence-transformers): {exc}")
        res.trace.append(TraceStep(NAME, "retrieve_passages", "error", res.error))
        return res
    res.trace.append(TraceStep(NAME, "retrieve_passages", "ok", f"{len(chunks)} relevant passage(s)"))

    if not chunks:
        res.data = {"answer": INSUFFICIENT, "grounded": False}
        return res

    res.sources = [_source_entry(i, c) for i, c in enumerate(chunks, start=1)]
    if get_settings().mock_llm:
        res.data = {"answer": _extractive_answer(chunks), "grounded": True, "generator": "extractive (mock mode)"}
        res.trace.append(TraceStep(NAME, "generate_answer", "info", "mock mode: extractive answer"))
        return res

    context = "\n\n".join(f"[{i}] ({c.metadata.get('document_title', '')}) {c.text}"
                          for i, c in enumerate(chunks, start=1))
    try:
        answer = llm.chat_text(SYSTEM_PROMPT, f"Context passages:\n{context}\n\nQuestion: {question}")
        res.data = {"answer": answer.strip(), "grounded": True, "generator": get_settings().ollama_model}
        res.trace.append(TraceStep(NAME, "generate_answer", "ok", get_settings().ollama_model))
    except llm.LLMError as exc:
        res.data = {"answer": _extractive_answer(chunks), "grounded": True,
                    "generator": "extractive (LLM unavailable)"}
        res.trace.append(TraceStep(NAME, "generate_answer", "fallback", f"{exc} Showing passages instead."))
    return res
