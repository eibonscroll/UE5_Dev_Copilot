from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .settings import SETTINGS
from .embeddings import Embedder
from .vectordb import VectorDB
from .indexer import index_all
from .agents import input_gate, rag_query, responder, formatter
from pathlib import Path
import os

app = FastAPI(title="UE Agentic Copilot")

EMB = Embedder(SETTINGS.embedding_model)
VDB = VectorDB()

class Ask(BaseModel):
    prompt: str

@app.on_event("startup")
def startup():
    # One-time index if collection empty (idempotent-ish)
    unreal = Path("/ingest/unreal_docs")
    project = Path("/ingest/project")
    plugins = Path("/ingest/plugins")
    # You can gate this with an env var or a sentinel file
    index_all(unreal, project, plugins, EMB, VDB)

@app.post("/ask")
def ask(q: Ask):
    gate = input_gate.handle(q.prompt)
    if gate.get("decision") != "YES":
        return {"decision": "NO", "message": "Prompt out-of-bounds for this copilot."}

    _ = rag_query.handle(q.prompt, EMB, VDB)
    resp = responder.handle(q.prompt)
    md = formatter.md_mermaid("UE Agentic Copilot", resp["bullets"], resp["top"], q.prompt)
    return {"decision": "YES", "markdown": md}

@app.get("/", response_class=HTMLResponse)
def ui():
    # Minimal vanilla HTML+JS page; uses Marked + Mermaid via CDN.
    # Posts to /ask, then renders returned .markdown.
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>UE Agentic Copilot (Local)</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body { font-family: system-ui, sans-serif; margin: 1.25rem 1.25rem 4rem; }
    textarea { width: 100%; height: 10rem; font-family: ui-monospace, monospace; }
    button { padding: .6rem 1rem; margin-top: .5rem; }
    #out { margin-top: 1.5rem; }
    pre { background:#111; color:#eee; padding:1rem; overflow:auto; border-radius:.5rem; }
  </style>
</head>
<body>
  <h1>UE Agentic Copilot</h1>
  <p>Enter a prompt related to Unreal docs, your game project, or plugins.</p>
  <textarea id="prompt" placeholder="e.g., Where does PlayerController spawn the companion actor?"></textarea><br/>
  <button id="ask">Ask</button>
  <div id="msg"></div>
  <div id="out"></div>

  <!-- Markdown & Mermaid renderers -->
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({ startOnLoad: false });</script>

  <script>
  const askBtn = document.getElementById('ask');
  const promptEl = document.getElementById('prompt');
  const out = document.getElementById('out');
  const msg = document.getElementById('msg');

  askBtn.onclick = async () => {
    msg.textContent = "Running…";
    out.innerHTML = "";
    try {
      const r = await fetch('/ask', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ prompt: promptEl.value })
      });
      const data = await r.json();
      if (data.decision !== "YES") {
        msg.textContent = "Out of bounds: " + (data.message || "");
        return;
      }
      msg.textContent = "";
      // Render markdown
      const html = marked.parse(data.markdown || "");
      out.innerHTML = html;

      // Upgrade any Mermaid code blocks
      const blocks = out.querySelectorAll('code.language-mermaid, pre code[class*="language-mermaid"]');
      for (const [i, block] of [...blocks].entries()) {
        const parent = block.closest('pre') || block.parentElement;
        const graph = block.textContent;
        const id = 'mmd-' + i + '-' + Math.random().toString(36).slice(2);
        const container = document.createElement('div');
        container.className = 'mermaid';
        container.textContent = graph;
        parent.replaceWith(container);
      }
      await mermaid.run({ querySelector: '.mermaid' });
    } catch (e) {
      console.error(e);
      msg.textContent = "Error: " + e;
    }
  };
  </script>
</body>
</html>
"""