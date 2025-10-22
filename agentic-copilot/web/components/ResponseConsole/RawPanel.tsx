// web/components/ResponseConsole/RawPanel.tsx
export default function RawPanel({ raw }: { raw: any }) {
  return (
    <pre
      style={{
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        margin: 0,
        background: "#0b1020",
        color: "#e5e7eb",
        padding: 12,
        borderRadius: 6,
        fontSize: 13,
      }}
    >
      {raw ? JSON.stringify(raw, null, 2) : "// No response"}
    </pre>
  );
}
