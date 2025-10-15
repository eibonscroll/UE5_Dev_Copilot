from ..embeddings import Embedder
from ..vectordb import VectorDB
from ..memory_store import MEMORY
from ..utils.code_parsing import extract_symbols

def handle(prompt: str, embedder: Embedder, vdb: VectorDB, k=12):
    qvec = embedder.embed([prompt])[0]
    hits = vdb.search(qvec, k=k)
    # collect symbols by file
    by_file = {}
    for h in hits:
        file = h.payload["file"]
        chunk = h.payload["chunk"]
        syms = extract_symbols(chunk)
        if file not in by_file:
            by_file[file] = {"file": file, "classes": set(), "functions": set()}
        by_file[file]["classes"].update(syms["classes"])
        by_file[file]["functions"].update(syms["functions"])
    entries = [
        {"file": f, "classes": sorted(v["classes"]), "functions": sorted(v["functions"])}
        for f, v in by_file.items()
        if v["classes"] or v["functions"]
    ]
    MEMORY.put_symbols(entries)
    return {"symbol_count": sum(len(e["classes"])+len(e["functions"]) for e in entries), "files": len(entries)}
