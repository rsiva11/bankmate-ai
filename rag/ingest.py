"""Ingestion pipeline: fetch/import -> clean -> chunk -> embed -> store in ChromaDB.

Usage (from project root):
    python -m rag.ingest --rebuild            # fetch official URLs + local files
    python -m rag.ingest --rebuild --skip-fetch   # local files in data/sbi_docs only
    python -m rag.ingest --url https://sbi.co.in/...   # add another official SBI page
"""
import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import Settings, get_settings
from rag.document_loader import (DocumentFetchError, LoadedDocument, fetch_source,
                                 load_local_documents)
from rag.embeddings import get_embedder

# (url, title) pairs. Titles are shown in citations.
OFFICIAL_SOURCES = [
    ("https://sbi.bank.in/documents/26274/109521/26122025_Private+Policy.pdf/"
     "ed6a8697-80ba-a1dc-8fc1-2c93c2c113a4?t=1766743311511",
     "SBI Privacy Statement"),
    ("https://sbi.co.in/web/customer-care/contact-centre",
     "SBI Contact Centre and Privacy Statement"),
    ("https://sbi.co.in/documents/17826/0/Sustainability%2BReport%2BFY%2B2024-25.pdf/"
     "600d0a64-b30b-c23e-7b71-5cb1e3fbb299?t=1751026510426",
     "SBI Sustainability Report FY 2024-25"),
]


@dataclass
class IngestReport:
    loaded: list = field(default_factory=list)   # (title, url, n_sections)
    failed: list = field(default_factory=list)   # (source, reason)
    chunks: int = 0


def chunk_text(text: str, size: int, overlap: int) -> list:
    """Split into overlapping chunks, preferring sentence/word boundaries."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            cut = window.rfind(". ")
            if cut > size * 0.6:
                end = start + cut + 1
            else:
                space = window.rfind(" ")
                if space > size * 0.6:
                    end = start + space
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_records(doc: LoadedDocument, size: int, overlap: int) -> tuple:
    ids, texts, metas = [], [], []
    for s_idx, section in enumerate(doc.sections):
        for c_idx, piece in enumerate(chunk_text(section.text, size, overlap)):
            meta = {
                "source_url": doc.source_url,
                "document_title": doc.title,
                "retrieval_date": doc.retrieval_date,
                "origin": doc.origin,
            }
            if section.section_title:
                meta["section_title"] = section.section_title
            if section.page is not None:
                meta["page"] = section.page
            raw_id = f"{doc.source_url}|{s_idx}|{c_idx}|{piece[:60]}"
            ids.append(hashlib.sha1(raw_id.encode()).hexdigest())
            texts.append(piece)
            metas.append(meta)
    return ids, texts, metas


def open_collection(settings: Settings, embedder_name: str, rebuild: bool = False):
    client = chromadb.PersistentClient(path=str(settings.chroma_dir),
                                       settings=ChromaSettings(anonymized_telemetry=False))
    if rebuild:
        existing = [getattr(c, "name", c) for c in client.list_collections()]
        if settings.chroma_collection in existing:
            client.delete_collection(settings.chroma_collection)
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine", "embedding_backend": embedder_name},
    )


def ingest_documents(docs: list, settings: Optional[Settings] = None, embedder=None,
                     rebuild: bool = False, report: Optional[IngestReport] = None) -> IngestReport:
    s = settings or get_settings()
    embedder = embedder or get_embedder(s)
    report = report or IngestReport()
    collection = open_collection(s, getattr(embedder, "name", "unknown"), rebuild=rebuild)
    for doc in docs:
        ids, texts, metas = build_records(doc, s.chunk_size, s.chunk_overlap)
        report.loaded.append((doc.title, doc.source_url, len(doc.sections)))
        for i in range(0, len(texts), 64):  # batch to keep RAM low
            batch = slice(i, i + 64)
            collection.upsert(ids=ids[batch], documents=texts[batch], metadatas=metas[batch],
                              embeddings=embedder.embed_documents(texts[batch]))
        report.chunks += len(texts)
    return report


def run(rebuild: bool, skip_fetch: bool, extra_urls: list) -> IngestReport:
    s = get_settings()
    report, docs = IngestReport(), []
    if not skip_fetch:
        for url, title in OFFICIAL_SOURCES + [(u, None) for u in extra_urls]:
            print(f"Fetching: {url[:90]}")
            try:
                docs.append(fetch_source(url, title=title))
            except DocumentFetchError as exc:
                report.failed.append((url, str(exc)))
                print(f"  FAILED: {exc}")
    local_docs, problems = load_local_documents(s.docs_dir)
    docs.extend(local_docs)
    report.failed.extend(problems)
    if not docs:
        return report
    print("Embedding and storing (first run downloads the embedding model)...")
    return ingest_documents(docs, s, rebuild=rebuild, report=report)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the SBI public-document knowledge base.")
    ap.add_argument("--rebuild", action="store_true", help="delete and recreate the collection first")
    ap.add_argument("--skip-fetch", action="store_true", help="only import local files from data/sbi_docs")
    ap.add_argument("--url", action="append", default=[], help="extra official SBI URL (repeatable)")
    args = ap.parse_args(argv)
    report = run(args.rebuild, args.skip_fetch, args.url)
    print("\n=== Ingestion report ===")
    for title, url, n in report.loaded:
        print(f"  LOADED  {title[:60]}  ({n} sections)  {url[:70]}")
    for src, reason in report.failed:
        print(f"  MISSING {src[:80]}\n          reason: {reason}")
    print(f"Chunks stored: {report.chunks}")
    if report.chunks == 0:
        print("\nNothing was ingested. Download the documents manually into data/sbi_docs/ "
              "(see data/sbi_docs/README.md) and run: python -m rag.ingest --rebuild --skip-fetch")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())