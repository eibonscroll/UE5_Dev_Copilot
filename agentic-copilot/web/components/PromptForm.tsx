// web/components/PromptForm.tsx
import { FormEvent } from "react";

type Props = {
  value: string;
  onChange: (s: string) => void;
  onSubmit: () => void;
  loading?: boolean;
  error?: string | null;
};

export default function PromptForm({ value, onChange, onSubmit, loading, error }: Props) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <form onSubmit={submit} style={{ marginBottom: 16 }}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ask something like: Generate a Mermaid diagram of the Zombies plugin"
        rows={4}
        style={{
          width: "100%",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          borderRadius: 6,
          padding: 10,
          border: "1px solid #ccc",
          resize: "vertical",
        }}
      />
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
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
        {error && <span style={{ color: "#b91c1c" }}>{error}</span>}
      </div>
    </form>
  );
}
