from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from .settings import SETTINGS
import time
from typing import Iterable, Optional, Union, List
import logging
log = logging.getLogger("vectordb")

class VectorDB:
    def __init__(self):
        self.collection = SETTINGS.collection
        self.url = SETTINGS.qdrant_url
        self.client = QdrantClient(
            url=SETTINGS.qdrant_url,
            grpc_port=6334,
            prefer_grpc=True,
            timeout=120.0,
        )

    @property
    def endpoint(self) -> str:
        return self.url

    # --- helpers -------------------------------------------------------------

    def _existing_vector_size(self) -> int | None:
        """
        Return current vector dim if the collection exists, else None.
        Handles both object and dict responses across client versions.
        """
        try:
            info = self.client.get_collection(self.collection)
        except Exception:
            return None

        # qdrant_client can return an object or dict depending on version
        cfg = getattr(info, "config", None) or getattr(info, "result", None) or info

        # Navigate to vectors.size
        # Object-style:
        vectors = getattr(getattr(getattr(cfg, "params", None), "vectors", None), "size", None)
        if isinstance(vectors, int):
            return vectors

        # Dict-style:
        try:
            return cfg["params"]["vectors"]["size"]
        except Exception:
            return None

    def _create_collection(self, dim: int, distance=Distance.COSINE):
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=dim, distance=distance),
        )

    def _delete_collection_if_exists(self):
        cols = self.client.get_collections().collections
        if any(c.name == self.collection for c in cols):
            self.client.delete_collection(self.collection)

    # --- public API ----------------------------------------------------------

    def ensure_collection(self, dim: int, *, recreate_on_mismatch: bool = True):
        import logging, time
        log = logging.getLogger("vectordb")

        t0 = time.perf_counter()
        log.info(
            "vectordb: ensure_collection start name=%s expected_dim=%d recreate_on_mismatch=%s",
            self.collection, dim, recreate_on_mismatch,
        )

        try:
            cols = self.client.get_collections().collections
            exists = any(c.name == self.collection for c in cols)
            log.info(
                "vectordb: collections found=%d exists=%s",
                len(cols), exists,
            )

            if not exists:
                log.info(
                    "vectordb: creating collection '%s' (dim=%d, distance=cosine)",
                    self.collection, dim,
                )
                self._create_collection(dim)
                log.info(
                    "vectordb: created collection '%s' in %.2fs",
                    self.collection, time.perf_counter() - t0,
                )
                return

            current = self._existing_vector_size()
            log.info(
                "vectordb: existing collection '%s' vector_size=%s",
                self.collection, current if current is not None else "unknown",
            )

            if current is None:
                if recreate_on_mismatch:
                    log.warning(
                        "vectordb: unknown existing vector size; recreating '%s' as dim=%d",
                        self.collection, dim,
                    )
                    self._delete_collection_if_exists()
                    self._create_collection(dim)
                    log.info(
                        "vectordb: recreated '%s' in %.2fs",
                        self.collection, time.perf_counter() - t0,
                    )
                    return
                raise RuntimeError(
                    f"Could not determine vector size for existing collection '{self.collection}'."
                )

            if current != dim:
                msg = (
                    f"vectordb: size mismatch for '{self.collection}': existing={current}, "
                    f"expected={dim}"
                )
                if recreate_on_mismatch:
                    log.warning("%s — recreating collection", msg)
                    self._delete_collection_if_exists()
                    self._create_collection(dim)
                    log.info(
                        "vectordb: recreated '%s' with dim=%d in %.2fs",
                        self.collection, dim, time.perf_counter() - t0,
                    )
                    return
                else:
                    log.error("%s — refusing to recreate", msg)
                    raise ValueError(
                        f"Collection '{self.collection}' exists with size {current}, "
                        f"but you requested {dim}. Set recreate_on_mismatch=True or "
                        f"drop the collection manually."
                    )

            log.info(
                "vectordb: collection '%s' already correct (dim=%d); no action needed (%.2fs)",
                self.collection, dim, time.perf_counter() - t0,
            )

        except Exception:
            log.exception(
                "vectordb: ensure_collection failed for '%s' (expected_dim=%d) after %.2fs",
                self.collection, dim, time.perf_counter() - t0,
            )
            raise

    def recreate_collection(self, dim: int):
        """Force fresh collection with given dim."""
        self._delete_collection_if_exists()
        self._create_collection(dim)

    def upsert(self, payloads, vectors, ids=None, batch_size: int = 256):
        import logging, time
        log = logging.getLogger("vectordb")

        if ids is None:
            ids = list(range(1, len(vectors) + 1))
        assert len(ids) == len(vectors) == len(payloads)

        total = len(vectors)
        if total == 0:
            log.warning("vectordb: upsert called with 0 vectors; nothing to do")
            return

        batches = (total + batch_size - 1) // batch_size
        log.info(
            "vectordb: upsert starting total=%d batch_size=%d batches=%d collection=%s",
            total, batch_size, batches, self.collection,
        )

        def chunk(seq, n):
            for i in range(0, len(seq), n):
                yield seq[i:i + n]

        started = time.perf_counter()
        for b, (id_chunk, vec_chunk, pay_chunk) in enumerate(
                zip(chunk(ids, batch_size), chunk(vectors, batch_size), chunk(payloads, batch_size)),
                start=1,
        ):
            points = [
                PointStruct(id=i, vector=v, payload=p)
                for i, v, p in zip(id_chunk, vec_chunk, pay_chunk)
            ]
            t0 = time.perf_counter()
            try:
                self.client.upsert(
                    collection_name=self.collection,
                    points=points,
                    wait=True,
                )
                dt = time.perf_counter() - t0
                rate = (len(points) / dt) if dt > 0 else float("inf")
                log.info(
                    "vectordb: upsert batch %d/%d size=%d ok in %.2fs (%.0f pts/s)",
                    b, batches, len(points), dt, rate,
                )
            except Exception as e:
                log.exception(
                    "vectordb: upsert batch %d/%d FAILED (size=%d): %s",
                    b, batches, len(points), e,
                )
                raise

        total_dt = time.perf_counter() - started
        overall_rate = (total / total_dt) if total_dt > 0 else float("inf")
        log.info(
            "vectordb: upsert finished total=%d batches=%d in %.2fs (%.0f pts/s)",
            total, batches, total_dt, overall_rate,
        )

    def search(
        self,
        query_vector: Union[list[float], "np.ndarray"],
        k: int = 5,
        *,
        score_threshold: Optional[float] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> List[dict]:
        """
        KNN search in the current collection.
        Returns a list of dicts: [{id, score, payload}] (payload only if requested).
        """
        log = logging.getLogger("vectordb")

        # Normalize query vector to a plain list
        try:
            # works for numpy arrays too
            qvec = query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)
        except Exception:
            raise TypeError("query_vector must be an iterable of floats")

        if not qvec:
            raise ValueError("query_vector is empty")

        # Optional sanity check: warn if dim mismatches current collection size
        try:
            dim = len(qvec)
            existing = self._existing_vector_size()
            if existing is not None and existing != dim:
                log.warning("vectordb: search vector dim=%d differs from collection dim=%d", dim, existing)
        except Exception:
            pass

        log.info("vectordb: search k=%d threshold=%s payload=%s vectors=%s", k, score_threshold, with_payload, with_vectors)

        res = self.client.search(
            collection_name=self.collection,
            query_vector=qvec,
            limit=k,
            with_payload=with_payload,
            with_vectors=with_vectors,
            score_threshold=score_threshold,
        )

        # qdrant_client returns ScoredPoint objects; normalize to simple dicts
        hits = [
            {
                "id": getattr(p, "id", None),
                "score": getattr(p, "score", None),
                "payload": getattr(p, "payload", None) if with_payload else None,
            }
            for p in res
        ]

        log.info("vectordb: search returned %d hits (top score: %s)", len(hits), hits[0]["score"] if hits else None)
        return hits