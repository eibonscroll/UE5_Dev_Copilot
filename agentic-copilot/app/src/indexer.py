# src/indexer.py
from __future__ import annotations
import time
from pathlib import Path
from typing import Iterable, Tuple, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .embeddings import Embedder
from .vectordb import VectorDB
from .utils.code_parsing import read_text
import hashlib

EXTS = {".cpp", ".h", ".hpp", ".cs", ".py", ".md", ".uasset.meta", ".ini", ".txt"}

def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in EXTS:
            yield p

def build_corpus(unreal_docs: Path, project: Path, plugins: Path) -> Iterable[Tuple[str, Path, str]]:
    for source, base in (("unreal_docs", unreal_docs), ("project", project), ("plugins", plugins)):
        for f in iter_files(base):
            try:
                text = read_text(f)
            except Exception:
                continue
            if text and text.strip():
                yield source, f, text

def index_all(
    unreal_docs: Path,
    project: Path,
    plugins: Path,
    embedder: Embedder,
    vdb: VectorDB,
    log: Optional["logging.Logger"] = None,
    log_every_files: int = 100,
    log_every_chunks: int = 1000,
) -> dict:
    if log is None:
        import logging
        log = logging.getLogger("indexer")

    t0 = time.perf_counter()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)

    payloads, chunks = [], []
    file_count = 0
    chunk_count = 0

    log.info("indexer: scanning sources: %s, %s, %s", unreal_docs, project, plugins)

    for source, path, text in build_corpus(unreal_docs, project, plugins):
        file_count += 1
        if file_count % log_every_files == 0:
            log.info("indexer: scanned %d files so far...", file_count)

        for chunk in splitter.split_text(text):
            # Truncate payload text to keep request sizes small
            payloads.append({
                "text": chunk[:2000],
                "path": str(path),
                "source": source,
                "hash": file_hash(text),  # same hash for all chunks of a file is fine
            })
            chunks.append(chunk)
            chunk_count += 1
            if chunk_count % log_every_chunks == 0:
                log.info("indexer: chunked %d chunks so far (last file: %s)", chunk_count, path)

    if not chunks:
        log.warning("indexer: no eligible files or chunks found; skipping index")
        return {"files": 0, "chunks": 0, "elapsed_s": round(time.perf_counter() - t0, 1)}

    log.info("indexer: chunking complete: files=%d chunks=%d (%.1fs)",
             file_count, chunk_count, time.perf_counter() - t0)

    t1 = time.perf_counter()
    log.info("indexer: embedding %d chunks with model=%s", len(chunks), getattr(embedder, "name", "unknown"))
    vectors = embedder.embed(chunks)  # consider batching inside Embedder
    dim = getattr(embedder, "dim", len(vectors[0]))
    log.info("indexer: embeddings ready dim=%d (%.1fs)", dim, time.perf_counter() - t1)

    t2 = time.perf_counter()
    log.info("indexer: ensuring collection '%s' (dim=%d) at %s",vdb.collection, dim, getattr(vdb, "endpoint", "qdrant"))
    vdb.ensure_collection(dim)

    log.info("indexer: upserting %d vectors in batches...", len(vectors))
    vdb.upsert(payloads, vectors)  # VectorDB.upsert logs per-batch below
    log.info("indexer: upsert complete (%.1fs)", time.perf_counter() - t2)

    total_time = round(time.perf_counter() - t0, 1)
    log.info("indexer: done files=%d chunks=%d total=%.1fs", file_count, chunk_count, total_time)
    return {"files": file_count, "chunks": chunk_count, "elapsed_s": total_time}
