# src/agents/pipeline.py
from __future__ import annotations
import os, time, logging, hashlib
from typing import List, Dict, Any
from openai import OpenAI

from ..embeddings import Embedder
from ..vectordb import VectorDB

log = logging.getLogger("pipeline")

def _cfg(name: str, default: str) -> str:
    return os.getenv(name, default)

def _md_escape(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;")

# ---------- Agent 1: Retrieve (with optional simple rerank) ----------

def retrieve(query: str, embedder: Embedder, vdb: VectorDB, k: int, top_n: int) -> List[Dict[str, Any]]:
    qvec = embedder.embed([query])[0]
    hits = vdb.search(qvec, k=k, with_payload=True, with_vectors=False)

    # minimal lexical bump: prefer chunks mentioning important query terms
    q_terms = [w.lower() for w in query.split() if len(w) > 3]
    def lexical_boost(payload_text: str) -> int:
        t = payload_text.lower()
        return sum(1 for w in q_terms if w in t)

    scored: List[Dict[str, Any]] = []
    for h in hits:
        p = h.get("payload", {})
        text = p.get("text", "")
        boost = lexical_boost(text)
        scored.append({
            "id": h.get("id"),
            "score": float(h.get("score", 0.0)) + 0.01 * boost,  # gentle lexical nudge
            "path": p.get("path") or p.get("file") or "",
            "source": p.get("source", ""),
            "text": text,
        })

    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:top_n]
    log.info("retrieve: got %d → keeping %d; top path=%s", len(scored), len(top), top[0]["path"] if top else "n/a")
    return top

# ---------- Agent 2: LLM synthesis (OpenAI) ----------

def synthesize_answer(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Produces a markdown answer with inline citations like [^1], and a References list
    mapping to your indexed file paths.
    """
    client = OpenAI()
    model = _cfg("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    temperature = float(_cfg("OPENAI_TEMPERATURE", "0.2"))

    # Build context list for the model (short, but sufficient)
    refs = []
    for i, c in enumerate(contexts, 1):
        refs.append(f"[{i}] path: {c['path']}\n{c['text'][:1200]}")  # keep below context limits

    system = (
        "You are a senior Unreal/Gameplay engineer assistant.\n"
        "Answer *only* using the provided CONTEXT snippets.\n"
        "When you assert a fact, add a citation like [^n] that refers to the numbered reference.\n"
        "If not enough info, say what’s missing and suggest where to look in the codebase."
    )
    user = (
        f"QUESTION:\n{query}\n\n"
        "CONTEXT (numbered snippets):\n" + "\n\n".join(refs) +
        "\n\nOutput clean, concise Markdown. Prefer bullet steps and small code blocks where helpful."
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":user},
        ],
        temperature=temperature,
    )
    markdown = resp.choices[0].message.content

    # build references block the UI can render
    references = "\n".join([f"[^{i}] {c['path']}" for i, c in enumerate(contexts, 1)])
    return {
        "markdown": markdown + "\n\n---\n**References**\n\n" + references,
        "contexts": contexts,
    }

# ---------- Agent 3: Grounding validator ----------

def validate_grounding(markdown: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Simple checks:
      - has at least 1 citation [^n]
      - each citation index exists
      - penalize hallucinated functions/classes not present anywhere in snippets (best-effort)
    """
    ok = True
    issues = []

    cites = []
    import re
    for m in re.finditer(r"\[\^(\d+)\]", markdown):
        cites.append(int(m.group(1)))

    if not cites:
        ok = False
        issues.append("No citations [^n] found in the answer.")

    max_ref = len(contexts)
    if any(i < 1 or i > max_ref for i in cites):
        ok = False
        issues.append("Citations reference a non-existent index.")

    # Heuristic: if answer claims code symbols not present in any context text
    # Look for CamelCase or snake_case identifiers; ensure at least one ref contains them.
    tokens = re.findall(r"\b([A-Z][A-Za-z0-9_]{2,}|[a-z_][a-z0-9_]{2,})\b", markdown)
    check = set(t for t in tokens if len(t) > 3)
    big_ctx = " ".join(c["text"] for c in contexts).lower()
    missing = [t for t in check if t.lower() not in big_ctx]
    # only flag if it appears *outside* code fence-like formatting, but keep it simple here.
    if len(missing) > 10:  # be conservative
        issues.append("Many identifiers are not present in sources; review for hallucinations.")

    return {"ok": ok, "issues": issues}

# ---------- Agent 4: Mermaid formatter (optional) ----------

def add_mermaid(markdown: str, query: str, contexts: List[Dict[str, Any]]) -> str:
    """
    If the question hints at architecture/flow (‘how does X connect to Y?’),
    append a Mermaid diagram scaffolding using file paths as nodes.
    """
    lower = query.lower()
    wants_diagram = any(w in lower for w in ["diagram", "flow", "connect", "sequence", "structure", "architecture", "outline"])
    if not wants_diagram:
        return markdown

    # crude node list from top contexts
    nodes = []
    edges = set()
    for c in contexts[:6]:
        p = c["path"]
        if not p:
            continue
        short = p.split("/")[-1]
        nodes.append(short)

    # create a simple chain (you can replace with smarter static analysis later)
    for i in range(len(nodes)-1):
        edges.add((nodes[i], nodes[i+1]))

    if not nodes:
        return markdown

    mer = ["```mermaid", "flowchart TD"]
    for a, b in edges:
        mer.append(f'  {a.replace(".","_")}["{_md_escape(a)}"] --> {b.replace(".","_")}["{_md_escape(b)}"]')
    mer.append("```")

    return markdown + "\n\n### Diagram\n" + "\n".join(mer)

# ---------- Agent 5: Packager (.md) ----------

def write_markdown(markdown: str, out_dir: str = "/app/out") -> str:
    os.makedirs(out_dir, exist_ok=True)
    h = hashlib.sha1(markdown.encode("utf-8", errors="ignore")).hexdigest()[:10]
    ts = int(time.time())
    fn = f"answer-{ts}-{h}.md"
    path = os.path.join(out_dir, fn)
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path

# ---------- Orchestrate all agents ----------

def run_pipeline(query: str, embedder: Embedder, vdb: VectorDB) -> Dict[str, Any]:
    k = int(os.getenv("RAG_TOP_K", "60"))
    top_n = int(os.getenv("RERANK_TOP_N", "8"))

    ctxs = retrieve(query, embedder, vdb, k=k, top_n=top_n)
    if not ctxs:
        return {"decision":"YES", "markdown":"_No relevant results._"}

    draft = synthesize_answer(query, ctxs)
    md = draft["markdown"]

    val = validate_grounding(md, ctxs)
    if not val["ok"]:
        warn = "\n".join(f"- {i}" for i in val["issues"])
        md = f"> ⚠️ **Grounding issues detected**\n>\n{warn}\n\n" + md

    md = add_mermaid(md, query, ctxs)
    outfile = write_markdown(md)

    return {"decision":"YES", "markdown": md, "file": outfile}
