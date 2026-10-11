"""Embedding backends.

* sentence-transformers (default): real semantic embeddings, CPU, cached locally.
* hash: tiny deterministic bag-of-words embedder used by tests / offline demos.
  It is NOT semantic; it only matches shared words.
"""
import hashlib
import math
import re
from typing import Optional

from config import Settings, get_settings

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "be", "it",
         "what", "does", "do", "say", "says", "about", "how", "my", "me", "i", "you", "your", "with",
         "that", "this", "as", "by", "at", "from", "can", "will", "which", "who", "when", "their"}


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = 8192):
        self.dim = dim

    def _embed(self, text: str) -> list:
        vec = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            if tok in _STOP:
                continue
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed_documents(self, texts: list) -> list:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list:
        return self._embed(text)


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_name: str, cache_dir):
        self.model_name = model_name
        self.cache_dir = str(cache_dir)
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, load lazily
            self._model = SentenceTransformer(self.model_name, cache_folder=self.cache_dir, device="cpu")
        return self._model

    def embed_documents(self, texts: list) -> list:
        return self._load().encode(texts, batch_size=32, normalize_embeddings=True,
                                   show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list:
        return self.embed_documents([text])[0]


def get_embedder(settings: Optional[Settings] = None):
    s = settings or get_settings()
    if s.embedding_backend == "hash":
        return HashEmbedder()
    if s.embedding_backend == "sentence-transformers":
        return SentenceTransformerEmbedder(s.embedding_model, s.model_cache_dir)
    raise ValueError(f"Unknown EMBEDDING_BACKEND '{s.embedding_backend}' (use sentence-transformers or hash)")
