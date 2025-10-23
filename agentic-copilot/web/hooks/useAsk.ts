// web/hooks/useAsk.ts
import { useCallback, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

function toDownloadHref(filePath?: string | null) {
  if (!filePath) return null;
  const base = process.env.NEXT_PUBLIC_API_BASE || "/api"; // e.g. "/api"
  const root = base.replace(/\/api$/, "");                 // -> "" if using rewrites locally
  return `${root}${filePath}`;                             // -> "/download/answer-xxxx.md"
}

export function useAsk(
  onSaved?: (item: {
    id: string;
    ts: number;
    prompt: string;
    markdown?: string;
    raw?: any;
    file?: string | null;
  }) => void
) {
  // Rename to avoid clashing with global window.prompt()
  const [input, setInput] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState<any>(null);
  const [markdown, setMarkdown] = useState<string>("");
  const [logs, setLogs] = useState<string[]>([]);
  const [file, setFile] = useState<string | null>(null);

  const downloadPath = toDownloadHref(file);

  // Expose marked function to children that render markdown
  const markedRef = useRef<any>(null);

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
    if (!input.trim()) return;

    setLoading(true);
    setError(null);
    setRaw(null);
    setMarkdown("");
    setLogs([]);
    setFile(null);

    const t0 = performance.now();
    try {
      await ensureMarked();
      const base = process.env.NEXT_PUBLIC_API_BASE || "/api";

      log(`POST ${base}/ask`);
      const res = await fetch(`${base}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: input }),
      });

      log(`HTTP ${res.status}`);
      const json = await res.json().catch(() => ({}));
      setRaw(json);

      if (!res.ok || json.decision === "NO") {
        const msg = json?.message || `Request failed (${res.status})`;
        setError(msg);
        log(`Backend error: ${msg}`);
      } else {
        const md = json.markdown || "";
        const f = json.file || null;
        setMarkdown(md);
        setFile(f);
        log("Received markdown + file");

        // Save to history (if caller provided a sink)
        onSaved?.({
          id: uuidv4(),
          ts: Date.now(),
          prompt: input,
          markdown: md,
          raw: json,
          file: f,
        });
      }
    } catch (e: any) {
      const msg = e?.message || String(e);
      setError(msg);
      log(`Client error: ${msg}`);
    } finally {
      log(`Done in ${(performance.now() - t0).toFixed(0)}ms`);
      setLoading(false);
    }
  }, [input, ensureMarked, onSaved]);

  return {
    // keep external API names the same:
    prompt: input,
    setPrompt: setInput,

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
