// web/hooks/useAsk.ts
import { useCallback, useRef, useState } from "react";
import { ask as askApi } from "../lib/api";

function toDownloadHref(filePath?: string | null) {
  if (!filePath) return null;
  const base = process.env.NEXT_PUBLIC_API_BASE || "/api"; // e.g. "/api"
  const root = base.replace(/\/api$/, "");                 // -> "" if using rewrites locally
  return `${root}${filePath}`;                             // -> "/download/answer-xxxx.md"
}

export function useAsk() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState<any>(null);
  const [markdown, setMarkdown] = useState("");
  const [logs, setLogs] = useState<string[]>([]);

  // Expose marked function to children that render markdown
  const markedRef = useRef<any>(null);

  // track file + computed download URL
  const [file, setFile] = useState<string | null>(null);
  const downloadPath = toDownloadHref(file);

  const log = (s: string) =>
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${s}`]);

  const ensureMarked = useCallback(async () => {
    if (!markedRef.current) {
      const m = await import("marked");
      markedRef.current = m.marked;
      log("marked loaded");
    }
    return markedRef.current;
  }, []);

  const ask = useCallback(async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    setRaw(null);
    setMarkdown("");
    setLogs([]);

    const t0 = performance.now();
    try {
      await ensureMarked();
      const base = process.env.NEXT_PUBLIC_API_BASE || "/api";

      //Clear file
      setFile(null);

      log(`POST ${base}/ask`);
      const res = await fetch(`${base}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      log(`HTTP ${res.status}`);
      const json = await res.json().catch(() => ({}));
      // set download file if present
      setFile(json?.file ?? null);
      setRaw(json);

      if (!res.ok || json.decision === "NO") {
        const msg = json?.message || `Request failed (${res.status})`;
        setError(msg);
        log(`Backend error: ${msg}`);
      } else {
        setMarkdown(json.markdown || "");
      }
    } catch (e: any) {
      const msg = e?.message || String(e);
      setError(msg);
      log(`Client error: ${msg}`);
    } finally {
      log(`Done in ${(performance.now() - t0).toFixed(0)}ms`);
      setLoading(false);
    }
  }, [prompt, ensureMarked]);

  return {
    prompt,
    setPrompt,
    loading,
    error,
    raw,
    markdown,
    logs,
    marked: markedRef.current,
    ask,
    downloadPath,
  };
}
