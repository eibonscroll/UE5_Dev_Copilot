// web/components/ResponseConsole/LogsPanel.tsx
export default function LogsPanel({ logs }: { logs: string[] }) {
  return (
    <pre
      style={{
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        margin: 0,
        background: "#111827",
        color: "#d1d5db",
        padding: 12,
        borderRadius: 6,
        fontSize: 13,
      }}
    >
      {(logs?.length ? logs : ["// No logs yet"]).join("\n")}
    </pre>
  );
}
