// web/pages/index.tsx
import { useState } from "react";
import { useAsk } from "../hooks/useAsk";
import { useHistory } from "../hooks/useHistory";
import { HistoryItem } from "../lib/history";
import HistorySidebar from "../components/HistorySidebar";
import PromptForm from "../components/PromptForm";
import ResponseConsole from "../components/ResponseConsole/ResponseConsole";

export default function Home() {
  const history = useHistory();
  const ask = useAsk(history.add); // save to history after successful ask
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleSelectHistory = (item: HistoryItem) => {
    // Put prompt back into the form:
    ask.setPrompt(item.prompt);
    // (Optional) Show cached result right away:
    if (item.markdown) {
      // re-hydrate console with cached answer
      // Note: we don't override `raw` logs here; user can hit Ask to refresh.
      (ask as any).setMarkdown?.(item.markdown);
      (ask as any).setError?.(null);
    }
    // If you want to immediately re-run it, call ask.ask() here instead:
    // ask.ask();
  };

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <HistorySidebar
        items={history.items}
        open={sidebarOpen}
        onToggle={() => setSidebarOpen((v) => !v)}
        onSelect={handleSelectHistory}
        onClear={history.clear}
        onRemove={history.remove}
      />

      <div style={{ flex: 1, overflowY: "auto" }}>
        <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
          <h1 style={{ marginBottom: 8 }}>UE5 Dev Copilot</h1>
          <p style={{ color: "#666", marginTop: 0 }}>
            Ask questions about your project/plugins. Mermaid diagrams in markdown are auto-rendered.
          </p>

          <PromptForm
            value={ask.prompt}
            onChange={ask.setPrompt}
            onSubmit={ask.ask}
            loading={ask.loading}
            error={ask.error}
            // If you already added the Download button in PromptForm,
            // it will appear automatically when ask.downloadPath is present.
            downloadPath={ask.downloadPath || undefined}
          />

          <ResponseConsole
            markdown={ask.markdown}
            raw={ask.raw}
            logs={ask.logs}
            marked={ask.marked}
          />
        </div>
      </div>
    </div>
  );
}
