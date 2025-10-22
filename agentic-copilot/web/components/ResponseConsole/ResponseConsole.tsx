// web/components/ResponseConsole/ResponseConsole.tsx
import { useState } from "react";
import RenderedPanel from "./RenderedPanel";
import RawPanel from "./RawPanel";
import LogsPanel from "./LogsPanel";

type Props = {
  markdown: string;
  raw: any;
  logs: string[];
  marked?: any;
};

const tabStyle = (active: boolean) => ({
  padding: "8px 12px",
  borderBottom: active ? "2px solid #111827" : "2px solid transparent",
  background: "transparent",
  cursor: "pointer",
});

export default function ResponseConsole({ markdown, raw, logs, marked }: Props) {
  const [tab, setTab] = useState<"rendered" | "raw" | "logs">("rendered");

  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        overflow: "hidden",
        background: "#fff",
      }}
    >
      <nav
        style={{
          display: "flex",
          gap: 8,
          padding: "8px 12px",
          borderBottom: "1px solid #e5e7eb",
          background: "#f9fafb",
        }}
      >
        <button style={tabStyle(tab === "rendered")} onClick={() => setTab("rendered")}>
          Markdown / Rendered
        </button>
        <button style={tabStyle(tab === "raw")} onClick={() => setTab("raw")}>
          Raw JSON
        </button>
        <button style={tabStyle(tab === "logs")} onClick={() => setTab("logs")}>
          Logs
        </button>
      </nav>

      <div style={{ padding: 16 }}>
        {tab === "rendered" && <RenderedPanel markdown={markdown} marked={marked} />}
        {tab === "raw" && <RawPanel raw={raw} />}
        {tab === "logs" && <LogsPanel logs={logs} />}
      </div>
    </section>
  );
}
