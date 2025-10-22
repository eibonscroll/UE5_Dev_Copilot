// web/pages/index.tsx
import { useAsk } from "../hooks/useAsk";
import PromptForm from "../components/PromptForm";
import ResponseConsole from "../components/ResponseConsole/ResponseConsole";

export default function Home() {
  const ask = useAsk(); // {prompt,setPrompt,ask,loading,error,raw,markdown,logs,marked}

  return (
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
      />

      <ResponseConsole
        markdown={ask.markdown}
        raw={ask.raw}
        logs={ask.logs}
        marked={ask.marked}
      />
    </div>
  );
}
