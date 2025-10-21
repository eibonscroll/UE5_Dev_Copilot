"use client";

import React from "react";

type AskResponse = {
  decision?: string;
  message?: string;
  markdown?: string;
  file?: string; // server returns /download/<name> or basename
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") || "http://localhost:8080";

export default function HomePage() {
  const [prompt, setPrompt] = React.useState("");
  const [msg, setMsg] = React.useState<string>("");
  const [html, setHtml] = React.useState<string>("");
  const [lastFileName, setLastFileName] = React.useState<string | null>(null);

  // Admin state
  const [token, setToken] = React.useState<string>("");
  const [statusJson, setStatusJson] = React.useState<string>("{}");
  const [reindexBtnBusy, setReindexBtnBusy] = React.useState(false);

  // Lazy-load marked + mermaid in the browser
  const markedRef = React.useRef<any>(null);
  const mermaidRef = React.useRef<any>(null);

  React.useEffect(() => {
    (async () => {
      if (!markedRef.current) {
        const m = await import("marked");
        // Optionally tighten security; here we keep default.
        markedRef.current = m.marked;
      }
      if (!mermaidRef.current) {
        // IMPORTANT: use ESM version for v11
        const mermaid = await import("mermaid/dist/mermaid.esm.mjs");
        mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });
        mermaidRef.current = mermaid;
      }
      // restore token if present
      const saved = window.localStorage.getItem("reindex_token") || "";
      if (saved) setToken(saved);
    })();
  }, []);

  // Utility to parse markdown to HTML
  const mdToHtml = React.useCallback(async (markdown: string) => {
    const marked = markedRef.current;
    if (!marked) return "";
    return marked.parse(markdown || "");
  }, []);

  // Transform ```mermaid code blocks into <div class="mermaid"> and render
  const renderMermaidBlocks = React.useCallback(async () => {
    const mermaid = mermaidRef.current;
    if (!mermaid) return;

    // Convert code blocks (produced by marked) to <div class="mermaid">
    // We expect code blocks like: <pre><code class="language-mermaid">...</code></pre>
    document.querySelectorAll("pre > code.language-mermaid").forEach((code) => {
      const pre = code.parentElement as HTMLElement;
      const div = document.createElement("div");
      div.className = "mermaid";
      // Keep raw text content; Mermaid parses it
      div.textContent = (code as HTMLElement).textContent || "";
      pre.replaceWith(div);
    });

    try {
      await mermaid.run({ querySelector: ".mermaid" });
    } catch (e) {
      console.error("Mermaid render error:", e);
    }
  }, []);

  // When HTML changes, (re)render Mermaid
  React.useEffect(() => {
    if (!html) return;
    // let the HTML land in the DOM before running Mermaid
    const t = setTimeout(() => {
      renderMermaidBlocks();
    }, 0);
    return () => clearTimeout(t);
  }, [html, renderMermaidBlocks]);

  function basename(p?: string | null) {
    if (!p) return "";
    const leaf = p.split("/").pop() || "";
    return leaf.split("\\").pop() || leaf;
  }

  const onAsk = async () => {
    const q = (prompt || "").trim();
    if (!q) {
      setMsg("Enter a prompt.");
      return;
    }
    setMsg("Running…");
    setHtml("");
    setLastFileName(null);

    try {
      const r = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: q }),
      });
      if (!r.ok) {
        const text = await r.text();
        throw new Error(`HTTP ${r.status}: ${text}`);
      }
      const data: AskResponse = await r.json();
      if (data.decision && data.decision !== "YES") {
        setMsg(`Out of bounds: ${data.message || ""}`);
        return;
      }

      setMsg("");
      const htmlOut = await mdToHtml(data.markdown || "");
      setHtml(htmlOut);

      if (data.file) {
        const name = basename(data.file);
        if (name) setLastFileName(name);
      }
    } catch (e: any) {
      console.error(e);
      setMsg(`Error: ${e.message || e.toString()}`);
    }
  };

  const onDownload = React.useCallback(() => {
    if (!lastFileName) return;
    const url = `${API_BASE}/download/${encodeURIComponent(lastFileName)}`;
    // open in same tab to trigger download
    window.location.href = url;
  }, [lastFileName]);

  // ---- Admin: Reindex & Status ----
  const hdrs = React.useCallback(() => {
    const h: Record<string, string> = {};
    if (token?.trim()) h["X-Token"] = token.trim();
    return h;
  }, [token]);

  const fetchStatus = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/admin/reindex/status`, {
        headers: hdrs(),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setStatusJson(JSON.stringify(j, null, 2));
    } catch (e: any) {
      setStatusJson(`Status error: ${e.message || e.toString()}`);
    }
  }, [hdrs]);

  const triggerReindex = React.useCallback(async () => {
    try {
      setReindexBtnBusy(true);
      const r = await fetch(`${API_BASE}/admin/reindex`, {
        method: "POST",
        headers: hdrs(),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(`HTTP ${r.status}: ${t}`);
      }
      await fetchStatus();
    } catch (e: any) {
      setStatusJson(`Start failed: ${e.message || e.toString()}`);
    } finally {
      setReindexBtnBusy(false);
    }
  }, [hdrs, fetchStatus]);

  // Persist the token locally
  React.useEffect(() => {
    try {
      window.localStorage.setItem("reindex_token", token || "");
    } catch {}
  }, [token]);

  // initial status fetch
  React.useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  return (
    <main style={{ padding: "1.25rem", maxWidth: 1100, margin: "0 auto" }}>
      <style
        // lightweight styles; you can move to globals.css
        dangerouslySetInnerHTML={{
          __html: `
          :root { color-scheme: light dark; }
          body { font-family: system-ui, sans-serif; line-height:1.4; }
          textarea { width: 100%; height: 10rem; font-family: ui-monospace, monospace; }
          button { padding: .55rem .9rem; margin-top: .5rem; border-radius:.45rem; cursor:pointer; }
          .row { display:flex; gap:.75rem; align-items:center; flex-wrap:wrap; }
          .muted { opacity:.7; font-size:.9rem; }
          .panel { border:1px solid #9993; padding:.75rem; border-radius:.5rem; margin-bottom:1rem; }
          pre { background:#111; color:#eee; padding:1rem; overflow:auto; border-radius:.5rem; }
          .ok { color: #0a0; }
          .err { color: #c00; }
        `,
        }}
      />
      <h1 style={{ marginBottom: ".25rem" }}>UE Agentic Copilot</h1>
      <p className="muted">
        API base: <code>{API_BASE}</code>
      </p>

      {/* Ask */}
      <section className="panel">
        <h3 style={{ margin: "0 0 .25rem" }}>Ask</h3>
        <p>Enter a prompt related to Unreal docs, your game project, or plugins.</p>
        <textarea
          placeholder="e.g., Where does PlayerController spawn the companion actor?"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <div className="row">
          <button onClick={onAsk}>Ask</button>
          <button onClick={onDownload} disabled={!lastFileName} title="Download last answer as .md">
            Download .md
          </button>
          <span className="muted">{lastFileName ? `Ready: ${lastFileName}` : ""}</span>
          <span className="muted">{msg}</span>
        </div>
        {/* Rendered markdown */}
        <div
          id="out"
          dangerouslySetInnerHTML={{ __html: html }}
          style={{ marginTop: "1rem" }}
        />
      </section>

      {/* Admin */}
      <section className="panel">
        <h3 style={{ margin: "0 0 .25rem" }}>Admin</h3>
        <div className="row">
          <button onClick={triggerReindex} disabled={reindexBtnBusy}>
            {reindexBtnBusy ? "Reindex (starting…)" : "Reindex"}
          </button>
          <button onClick={fetchStatus}>Refresh</button>
          <label className="muted">
            Token:{" "}
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              style={{ padding: ".35rem" }}
              placeholder="optional X-Token"
            />
          </label>
        </div>
        <pre style={{ marginTop: ".6rem", maxHeight: "18rem" }}>{statusJson}</pre>
      </section>
    </main>
  );
}
