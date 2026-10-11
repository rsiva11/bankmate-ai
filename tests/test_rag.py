"""RAG: ingestion, chunking, retrieval, grounded answers with citations, insufficient context."""
import pytest

import llm
from agents import privacy_agent
from config import get_settings
from rag.document_loader import (DocumentFetchError, html_to_document, load_local_documents,
                                 pdf_to_document, text_to_document)
from rag.embeddings import get_embedder
from rag.ingest import build_records, chunk_text, ingest_documents
from rag.retriever import KnowledgeBaseNotReady, Retriever
import supervisor

PRIVACY_HTML = """
<html><head><title>Demo Privacy Statement</title></head><body>
<nav>menu junk</nav>
<h2>Collection of customer information</h2>
<p>The bank collects customer information such as name, address and contact details when you open an account or use services.</p>
<h2>Sharing of customer information</h2>
<p>Customer information is not sold to third parties. It may be shared with regulators and service providers as required by law.</p>
<h2>Cookies</h2>
<p>The website uses cookies to remember preferences and measure how visitors use the site pages.</p>
</body></html>
"""

CONTACT_HTML = """<html><head><title>Contact Centre</title></head><body><h2>Helpline</h2>
<p>Call the toll free helpline number available all day for card blocking and account enquiries.</p></body></html>"""


def tiny_pdf(pages: list) -> bytes:
    """Hand-built minimal PDF (no extra library) with one text line per page."""
    bodies = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    kids, n = [], 3
    for text in pages:
        content = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
        bodies[n] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {n+1} 0 R /Resources "
                     "<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>").encode()
        bodies[n + 1] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
        kids.append(f"{n} 0 R")
        n += 2
    bodies[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    out, offsets = b"%PDF-1.4\n", {}
    for num in sorted(bodies):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for num in range(1, n):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    return out + f"trailer\n<< /Root 1 0 R /Size {n} >>\nstartxref\n{xref_at}\n%%EOF".encode()


@pytest.fixture
def kb():
    docs = [html_to_document(PRIVACY_HTML, "https://sbi.co.in/demo-privacy"),
            html_to_document(CONTACT_HTML, "https://sbi.co.in/demo-contact")]
    report = ingest_documents(docs, get_settings(), rebuild=True)
    assert report.chunks >= 3
    return Retriever(get_settings())


# ---------- loading & chunking ----------
def test_html_extraction_keeps_headings_and_drops_navigation():
    doc = html_to_document(PRIVACY_HTML, "https://sbi.co.in/demo-privacy")
    assert doc.title == "Demo Privacy Statement"
    assert [s.section_title for s in doc.sections] == [
        "Collection of customer information", "Sharing of customer information", "Cookies"]
    assert all("menu junk" not in s.text for s in doc.sections)


def test_pdf_extraction_preserves_page_numbers():
    doc = pdf_to_document(tiny_pdf(["First page about customer privacy and data handling practices.",
                                    "Second page about cookies and website usage statistics collected."]),
                          "https://sbi.co.in/x.pdf", "Demo PDF")
    assert [s.page for s in doc.sections] == [1, 2]


def test_corrupt_pdf_reports_clear_error():
    with pytest.raises(DocumentFetchError):
        pdf_to_document(b"this is not a pdf", "u", "t")


def test_chunking_overlaps_and_respects_size():
    text = " ".join(f"Sentence number {i} talks about privacy." for i in range(60))
    chunks = chunk_text(text, 300, 60)
    assert len(chunks) > 3 and all(len(c) <= 300 for c in chunks)
    assert chunks[0][-20:] in chunks[1]  # overlap carries context forward
    with pytest.raises(ValueError):
        chunk_text("abc", 100, 100)


def test_chunk_metadata_complete():
    doc = html_to_document(PRIVACY_HTML, "https://sbi.co.in/demo-privacy")
    ids, texts, metas = build_records(doc, 900, 150)
    assert len(ids) == len(set(ids)) == len(texts) == len(metas)
    for m in metas:
        assert m["source_url"] and m["document_title"] and m["retrieval_date"] and m["section_title"]


def test_manual_import_never_invents_urls(tmp_path):
    (tmp_path / "notes.txt").write_text("This is a long enough paragraph about privacy and customer data handling.")
    docs, problems = load_local_documents(tmp_path)
    assert docs[0].source_url == "manual-import:notes.txt" and docs[0].origin == "manual" and not problems


def test_missing_source_is_reported_not_hidden(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"garbage")
    docs, problems = load_local_documents(tmp_path)
    assert docs == [] and problems[0][0] == "broken.pdf"


# ---------- retrieval ----------
def test_retrieves_relevant_passage_with_metadata(kb):
    hits = kb.retrieve("What does the privacy statement say about customer information?")
    assert hits and "customer information" in hits[0].text.lower()
    assert hits[0].metadata["source_url"].startswith("https://sbi.co.in/")
    assert hits[0].metadata["section_title"]


def test_irrelevant_question_returns_nothing(kb):
    assert kb.retrieve("recipe for chocolate cake with strawberries") == []


def test_retrieval_before_ingestion_is_a_clear_error():
    with pytest.raises(KnowledgeBaseNotReady):
        Retriever(get_settings()).retrieve("anything")


def test_embedding_backend_mismatch_detected(kb, monkeypatch):
    from rag.retriever import EmbeddingMismatch

    class Other:
        name = "other-model"
        def embed_query(self, t): return [0.0]
    with pytest.raises(EmbeddingMismatch):
        Retriever(get_settings(), embedder=Other()).retrieve("customer information")


# ---------- privacy agent: grounded answers & citations ----------
def test_privacy_answer_has_sources_and_urls(kb):
    res = privacy_agent.answer_question("What does the privacy statement say about customer information?", kb)
    assert res.ok and res.data["grounded"] and res.sources
    assert res.sources[0]["url"] == "https://sbi.co.in/demo-privacy"
    assert res.sources[0]["title"] == "Demo Privacy Statement"


def test_privacy_insufficient_context_is_stated(kb):
    res = privacy_agent.answer_question("recipe for chocolate cake with strawberries", kb)
    assert res.ok and res.data["grounded"] is False and res.sources == []
    assert "does not contain enough information" in res.data["answer"]


def test_privacy_before_ingestion_gives_instructions():
    res = privacy_agent.answer_question("customer information")
    assert not res.ok and "rag.ingest" in res.error


def test_privacy_llm_prompt_contains_only_retrieved_context(kb, monkeypatch):
    monkeypatch.setenv("BANKMATE_MOCK_LLM", "0")
    seen = {}

    def fake(system, user):
        seen["user"] = user
        return "Customer information is not sold to third parties [1]."
    monkeypatch.setattr(llm, "chat_text", fake)
    res = privacy_agent.answer_question("Is customer information shared with third parties?", kb)
    assert "Context passages:" in seen["user"] and "third parties" in seen["user"]
    assert res.data["answer"].endswith("[1].") and res.sources


def test_privacy_llm_failure_falls_back_to_passages(kb, monkeypatch):
    monkeypatch.setenv("BANKMATE_MOCK_LLM", "0")

    def down(system, user):
        raise llm.LLMTimeout("slow")
    monkeypatch.setattr(llm, "chat_text", down)
    res = privacy_agent.answer_question("What is said about customer information?", kb)
    assert res.ok and res.trace[-1].status == "fallback" and "Most relevant passages" in res.data["answer"]


def test_supervisor_routes_privacy_question_with_citations(bank, kb):
    r = supervisor.handle_message(
        "What does the public SBI privacy statement say about customer information?", "CUST1001", retriever=kb)
    assert r.intents == ["privacy_policy_question"] and r.agents == ["Privacy Knowledge Agent"]
    assert r.sources and "Sources:" in r.text and "synthetic" in r.text.lower()


def test_hash_embedder_is_deterministic():
    e = get_embedder(get_settings())
    assert e.embed_query("customer privacy") == e.embed_query("customer privacy")
