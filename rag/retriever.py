"""Retrieve relevant passages from ChromaDB with a relevance (distance) cut-off."""
import sys
from dataclasses import dataclass
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import Settings, get_settings
from rag.embeddings import get_embedder


class KnowledgeBaseNotReady(Exception):
    """Collection missing/empty: the user must run the ingest command."""


class EmbeddingMismatch(Exception):
    pass


@dataclass
class RetrievedChunk:
    text: str
    metadata: dict
    distance: float


class Retriever:
    def __init__(self, settings: Optional[Settings] = None, embedder=None):
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder(self.settings)

    def _collection(self):
        s = self.settings
        client = chromadb.PersistentClient(path=str(s.chroma_dir),
                                           settings=ChromaSettings(anonymized_telemetry=False))
        names = [getattr(c, "name", c) for c in client.list_collections()]
        if s.chroma_collection not in names:
            raise KnowledgeBaseNotReady(
                "The knowledge base has not been built yet. Run: python -m rag.ingest --rebuild")
        col = client.get_collection(s.chroma_collection)
        if col.count() == 0:
            raise KnowledgeBaseNotReady("The knowledge base is empty. Run: python -m rag.ingest --rebuild")
        stored = (col.metadata or {}).get("embedding_backend")
        current = getattr(self.embedder, "name", None)
        if stored and current and stored != current:
            raise EmbeddingMismatch(
                f"Index was built with '{stored}' embeddings but '{current}' is configured. "
                "Rebuild with: python -m rag.ingest --rebuild")
        return col

    def count(self) -> int:
        try:
            return self._collection().count()
        except (KnowledgeBaseNotReady, EmbeddingMismatch):
            return 0

    def retrieve(self, query: str, k: Optional[int] = None,
                 max_distance: Optional[float] = None) -> list:
        s = self.settings
        col = self._collection()
        k = k or s.rag_top_k
        limit = s.rag_max_distance if max_distance is None else max_distance
        res = col.query(query_embeddings=[self.embedder.embed_query(query)], n_results=k,
                        include=["documents", "metadatas", "distances"])
        chunks = [RetrievedChunk(text=d, metadata=m, distance=float(dist))
                  for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]
        return [c for c in chunks if c.distance <= limit]


if __name__ == "__main__":
    # Tuning helper: python -m rag.retriever "what does SBI say about customer information"
    question = " ".join(sys.argv[1:]) or "customer information privacy"
    r = Retriever()
    for c in r.retrieve(question, k=8, max_distance=2.0):
        print(f"{c.distance:.3f}  p.{c.metadata.get('page', '-')}  {c.metadata['document_title'][:40]}  | {c.text[:90]}")
