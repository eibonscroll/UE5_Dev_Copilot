# src/main.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .settings import SETTINGS
from .embeddings import Embedder
from .vectordb import VectorDB
from .indexer import index_all
from .agents import input_gate, rag_query, responder, formatter
from pathlib import Path
from src.agents.pipeline import run_pipeline
import os, time, logging, asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from typing import Optional
from fastapi import HTTPException
from fastapi.responses import FileResponse


OUT_DIR = Path("/app/out")  # same dir used by write_markdown()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

app = FastAPI(title="UE Agentic Copilot")

EMB = Embedder(os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en"))
VDB = VectorDB()

class Ask(BaseModel):
    prompt: str

def _collection_count() -> int:
    # small helper to check if collection already has data
    try:
        return VDB.client.count(VDB.collection, exact=True).count
    except Exception:
        return 0

@app.on_event("startup")
def startup():
    t0 = time.perf_counter()
    policy = os.getenv("INDEX_ON_STARTUP", "auto").lower()
    logger.info("startup: policy=%s collection=%s", policy, VDB.collection)

    # Ensure collection exists with correct dim, but do NOT recreate if it already exists
    dim = getattr(EMB, "dim", 0) or 384
    VDB.ensure_collection(dim=dim, recreate_on_mismatch=True)

    existing = _collection_count()
    logger.info("startup: existing points in '%s' = %d", VDB.collection, existing)

    # Decide per policy
    if policy == "never":
        logger.info("startup: skipping indexing (policy=never)")
        return
    if policy == "auto" and existing > 0:
        logger.info("startup: skipping indexing (policy=auto, collection non-empty)")
        return

    # Otherwise run indexing
    logger.info("startup: starting indexing run…")
    stats = index_all(
        unreal_docs=Path("/ingest/unreal_docs"),
        project=Path("/ingest/project"),
        plugins=Path("/ingest/plugins"),
        embedder=EMB,
        vdb=VDB,
        log=logging.getLogger("indexer"),
        log_every_files=100,
        log_every_chunks=1000,
    )
    logger.info("startup: indexing done files=%s chunks=%s in %ss",
                stats.get("files"), stats.get("chunks"), stats.get("elapsed_s"))
    logger.info("startup: finished in %.1fs", time.perf_counter() - t0)

@app.post("/ask")
def ask(q: Ask):
    try:
        result = run_pipeline(q.prompt, EMB, VDB)
        return result
    except Exception as e:
        logger.exception("/ask failed: %s", e)
        return {"decision":"NO", "message": str(e)}

@app.post("/ingest")
def ingest(background: BackgroundTasks):
    background.add_task(index_all, Path("/ingest/unreal_docs"), Path("/ingest/project"),
                        Path("/ingest/plugins"), EMB, VDB,
                        logging.getLogger("indexer"), 100, 1000)
    return {"status": "started"}

@app.get("/download/{name}")
def download_md(name: str):
    # block path traversal
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = OUT_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="text/markdown", filename=name)

@app.get("/", response_class=HTMLResponse)
def ui():
    return r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>UE Agentic Copilot (Local)</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, sans-serif; margin: 1.25rem 1.25rem 4rem; line-height:1.4; }
    textarea { width: 100%; height: 10rem; font-family: ui-monospace, monospace; }
    button { padding: .55rem .9rem; margin-top: .5rem; border-radius:.45rem; cursor:pointer; }
    .row { display:flex; gap:.75rem; align-items:center; flex-wrap:wrap; }
    .muted { opacity:.7; font-size:.9rem; }
    #out { margin-top: 1.25rem; }
    pre { background:#111; color:#eee; padding:1rem; overflow:auto; border-radius:.5rem; }
    .panel { border:1px solid #9993; padding:.75rem; border-radius:.5rem; }
    .ok { color: #0a0; }
    .warn { color: #b80; }
    .err { color: #c00; }
    .kbd { font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; background: #0003; padding: .15rem .35rem; border-radius: .25rem; }
  </style>
</head>
<body>
  <h1>UE Agentic Copilot</h1>
  <p class="muted">Tip: Open <a href="/docs" target="_blank">/docs</a> for the API.</p>

  <!-- Ask UI -->
  <section class="panel" style="margin-bottom:1rem;">
    <h3 style="margin:0 0 .25rem;">Ask</h3>
    <p>Enter a prompt related to Unreal docs, your game project, or plugins.</p>
    <textarea id="prompt" placeholder="e.g., Where does PlayerController spawn the companion actor?"></textarea><br/>
    <div class="row">
      <button id="ask">Ask</button>
      <!-- NEW: download -->
      <button id="downloadBtn" disabled title="Download last answer as .md">Download .md</button>
      <span id="dlInfo" class="muted"></span>
      <!-- /NEW -->
      <span id="msg" class="muted"></span>
    </div>
    <div id="out"></div>
  </section>

  <!-- Admin: Reindex -->
  <section class="panel">
    <h3 style="margin:0 0 .25rem;">Admin</h3>
    <div class="row">
      <button id="reindexBtn">Reindex</button>
      <button id="refreshStatusBtn" title="Refresh status">Refresh</button>
      <label class="muted">Token:
        <input id="token" type="password" placeholder="optional X-Token" style="padding:.35rem;"/>
      </label>
      <span id="reindexMsg" class="muted"></span>
    </div>
    <pre id="status" style="margin-top:.6rem; max-height:18rem;"></pre>
  </section>

  <!-- Markdown & Mermaid renderers -->
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({ startOnLoad: false });</script>

  <script>
  // ---------- Ask ----------
  const askBtn = document.getElementById('ask');
  const promptEl = document.getElementById('prompt');
  const out = document.getElementById('out');
  const msg = document.getElementById('msg');
  // NEW: download controls
  const downloadBtn = document.getElementById('downloadBtn');
  const dlInfo = document.getElementById('dlInfo');
  let lastFileName = null; // just the basename
  // /NEW

  function basename(p) {
    if (!p) return "";
    return p.split('/').pop().split('\\').pop();
  }

  askBtn.onclick = async () => {
    const q = (promptEl.value || "").trim();
    if (!q) { msg.textContent = "Enter a prompt."; return; }
    msg.textContent = "Running…";
    out.innerHTML = "";
    // reset download UI
    lastFileName = null;
    downloadBtn.disabled = true;
    dlInfo.textContent = "";

    try {
      const r = await fetch('/ask', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ prompt: q })
      });
      if (!r.ok) {
        const text = await r.text();
        throw new Error("HTTP " + r.status + ": " + text);
      }
      const data = await r.json();
      if (data.decision && data.decision !== "YES") {
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
        const container = document.createElement('div');
        container.className = 'mermaid';
        container.textContent = graph;
        parent.replaceWith(container);
      }
      await mermaid.run({ querySelector: '.mermaid' });

      // NEW: enable download if server returned a file path
      if (data.file) {
        lastFileName = basename(data.file);
        if (lastFileName) {
          downloadBtn.disabled = false;
          dlInfo.textContent = "Ready: " + lastFileName;
        }
      }
      // /NEW
    } catch (e) {
      console.error(e);
      msg.textContent = "Error: " + e.message;
    }
  };

  // NEW: download click handler
  downloadBtn.onclick = () => {
    if (!lastFileName) return;
    const url = '/download/' + encodeURIComponent(lastFileName);
    // trigger browser download
    window.location.href = url;
  };
  // /NEW

  // ---------- Admin: Reindex ----------
  const tokenInput = document.getElementById('token');
  const reindexBtn = document.getElementById('reindexBtn');
  const refreshStatusBtn = document.getElementById('refreshStatusBtn');
  const statusPre = document.getElementById('status');
  const reindexMsg = document.getElementById('reindexMsg');

  // Persist token locally (optional)
  tokenInput.value = localStorage.getItem('reindex_token') || "";
  tokenInput.addEventListener('change', () => {
    localStorage.setItem('reindex_token', tokenInput.value || "");
  });

  let pollTimer = null;

  function hdrs() {
    const h = { };
    const t = tokenInput.value.trim();
    if (t) h['X-Token'] = t;
    return h;
  }

  async function fetchStatus() {
    try {
      const r = await fetch('/admin/reindex/status', { headers: hdrs() });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      statusPre.textContent = JSON.stringify(j, null, 2);

      if (j.running) {
        reindexBtn.disabled = true;
        reindexBtn.textContent = "Reindex (running…)";
        if (!pollTimer) pollTimer = setTimeout(fetchStatus, 1000);
      } else {
        reindexBtn.disabled = false;
        reindexBtn.textContent = "Reindex";
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      }

      if (j.last_error) {
        reindexMsg.textContent = "Last error: " + j.last_error;
        reindexMsg.className = "err";
      } else if (j.last_stats && j.last_stats.chunks) {
        reindexMsg.textContent = "Last run: " + j.last_stats.chunks + " chunks";
        reindexMsg.className = "ok";
      } else {
        reindexMsg.textContent = "";
        reindexMsg.className = "muted";
      }
    } catch (e) {
      statusPre.textContent = "Status error: " + e.message;
      reindexBtn.disabled = false;
      reindexBtn.textContent = "Reindex";
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    }
  }

  async function triggerReindex() {
    try {
      reindexBtn.disabled = true;
      reindexBtn.textContent = "Reindex (starting…)";
      reindexMsg.textContent = "Starting…";
      const r = await fetch('/admin/reindex', { method: 'POST', headers: hdrs() });
      if (!r.ok) {
        const t = await r.text();
        throw new Error("HTTP " + r.status + ": " + t);
      }
      reindexMsg.textContent = "Reindex started.";
      fetchStatus();
    } catch (e) {
      reindexMsg.textContent = "Start failed: " + e.message;
      reindexMsg.className = "err";
      reindexBtn.disabled = false;
      reindexBtn.textContent = "Reindex";
    }
  }

  reindexBtn.onclick = triggerReindex;
  refreshStatusBtn.onclick = fetchStatus;
  fetchStatus();
  </script>
</body>
</html>
"""


# simple in-memory state
class ReindexState:
    running: bool = False
    last_started: float | None = None
    last_finished: float | None = None
    last_stats: dict | None = None
    last_error: str | None = None

STATE = ReindexState()

async def _reindex_task():
    STATE.running = True
    STATE.last_error = None
    STATE.last_started = time.time()
    try:
        from .indexer import index_all
        stats = index_all(
            unreal_docs=Path("/ingest/unreal_docs"),
            project=Path("/ingest/project"),
            plugins=Path("/ingest/plugins"),
            embedder=EMB,
            vdb=VDB,
            log=logging.getLogger("indexer"),
            log_every_files=100,
            log_every_chunks=1000,
        )
        STATE.last_stats = stats
    except Exception as e:
        logging.getLogger("app").exception("reindex failed: %s", e)
        STATE.last_error = str(e)
    finally:
        STATE.last_finished = time.time()
        STATE.running = False

def _require_token(x_token: Optional[str]):
    expected = os.getenv("REINDEX_TOKEN")
    if not expected:
        return  # no guard set
    if not x_token or x_token != expected:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/admin/reindex")
async def trigger_reindex(background: BackgroundTasks, x_token: Optional[str] = Header(None)):
    _require_token(x_token)
    if STATE.running:
        raise HTTPException(status_code=409, detail="Reindex already running")
    # fire-and-forget background task
    background.add_task(lambda: asyncio.run(_reindex_task()))
    return {"status": "started"}

@app.get("/admin/reindex/status")
def reindex_status(x_token: Optional[str] = Header(None)):
    _require_token(x_token)
    return {
        "running": STATE.running,
        "last_started": STATE.last_started,
        "last_finished": STATE.last_finished,
        "last_error": STATE.last_error,
        "last_stats": STATE.last_stats,
    }