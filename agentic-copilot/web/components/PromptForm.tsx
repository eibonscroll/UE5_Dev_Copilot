// web/components/PromptForm.tsx
import { FormEvent, useMemo } from "react";

type Props = {
  value: string;
  onChange: (s: string) => void;
  onSubmit: () => void;
  loading?: boolean;
  error?: string | null;

  /** If provided, shows a Download button. Example: "/download/answer-1234abcd.md" */
  downloadPath?: string | null;
};

export default function PromptForm({
  value,
  onChange,
  onSubmit,
  loading,
  error,
  downloadPath,
}: Props) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  // If backend returns a relative path like "/download/answer-xxx.md",
  // send it through Next.js rewrites by prefixing "/api".
  const downloadHref = useMemo(() => {
    if (!downloadPath) return null;
    if (downloadPath.startsWith("/download")) return `/api${downloadPath}`;
    return downloadPath; // assume absolute URL already
  }, [downloadPath]);

  return (
    <form onSubmit={submit} style={{ marginBottom: 16 }}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ask something like: Generate a Mermaid diagram of the Zombies plugin"
        rows={4}
        style={{
          width: "100%",
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          borderRadius: 6,
          padding: 10,
          border: "1px solid #ccc",
          resize: "vertical",
        }}
      />
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          marginTop: 8,
          flexWrap: "wrap",
        }}
      >
        <button
          type="submit"
          disabled={loading}
          style={{
            background: "#111827",
            color: "#fff",
            border: 0,
            padding: "8px 14px",
            borderRadius: 6,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Thinking…" : "Ask"}
        </button>

        {downloadHref && (
          <a
            href={downloadHref}
            // 'download' hints the browser to save, but still opens in new tab fallback
            download
            target="_blank"
            rel="noopener noreferrer"
            style={{
              background: "#0f766e",
              color: "#fff",
              textDecoration: "none",
              padding: "8px 14px",
              borderRadius: 6,
            }}
            onClick={() =>
                console.log(`[${new Date().toLocaleTimeString()}] Download ${downloadHref}`)
            }
          >
            Download .md
          </a>
        )}

        {error && <span style={{ color: "#b91c1c" }}>{error}</span>}
      </div>
    </form>
  );
}
