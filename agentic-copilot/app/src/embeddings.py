# src/embeddings.py
from __future__ import annotations
import logging
from typing import List
from sentence_transformers import SentenceTransformer

log = logging.getLogger("embedder")

class Embedder:
    def __init__(self, model_name: str):
        self._model_name = model_name
        self.model = SentenceTransformer(model_name)

        # Dimension & device visibility
        try:
            self.dim = self.model.get_sentence_embedding_dimension()
        except Exception:
            self.dim = 0

        device = getattr(self.model, "device", "cpu")
        log.info("embedder: loaded model=%s dim=%s device=%s", self._model_name, self.dim, device)

    @property
    def name(self) -> str:
        return self._model_name

    def embed(self, texts: List[str], batch_size: int = 128) -> List[list[float]]:
        """
        Encode texts with progress logging (no progress bar noise).
        Returns a list of python lists (not numpy arrays) to keep JSON-friendly.
        """
        if not texts:
            return []

        out: List[list[float]] = []
        n = len(texts)
        batches = (n + batch_size - 1) // batch_size
        log.info("embedder: start encoding total=%d batch_size=%d batches=%d", n, batch_size, batches)

        for b in range(batches):
            start = b * batch_size
            end = min(start + batch_size, n)
            batch = texts[start:end]

            # normalize_embeddings=True can improve cosine search stability
            vecs = self.model.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            out.extend(v.tolist() for v in vecs)

            # Log every ~5 batches and the last batch
            if (b + 1) % 5 == 0 or (b + 1) == batches:
                log.info("embedder: batch %d/%d (items %d/%d)", b + 1, batches, end, n)

        log.info("embedder: done total=%d dim=%s", n, self.dim or (len(out[0]) if out else "n/a"))
        return out
