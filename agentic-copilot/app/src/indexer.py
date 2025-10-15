from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .embeddings import Embedder
from .vectordb import VectorDB
from .utils.code_parsing import extract_symbols, read_text

EXTS = {".cpp", ".h", ".hpp", ".cs", ".py", ".md", ".uasset.meta", ".ini", ".txt"}

def iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in EXTS:
            yield p

def build_corpus(base_dirs: list[Path]):
    for base in base_dirs:
        for f in iter_files(base):
            text = read_text(f)
            if text.strip():
                yield f, text

def index_all(unreal_docs, project, plugins, embedder: Embedder, vdb: VectorDB):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)
    payloads, chunks = [], []
    for f, text in build_corpus([unreal_docs, project, plugins]):
        for chunk in splitter.split_text(text):
            payloads.append({"file": str(f), "chunk": chunk})
            chunks.append(chunk)
    vectors = embedder.embed(chunks)
    vdb.ensure_collection(dim=len(vectors[0]))
    vdb.upsert(payloads, vectors)
