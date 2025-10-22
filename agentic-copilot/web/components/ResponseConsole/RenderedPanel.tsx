// web/components/ResponseConsole/RenderedPanel.tsx
import MarkdownRenderer from "../MarkdownRenderer";

export default function RenderedPanel({
  markdown,
  marked,
}: {
  markdown: string;
  marked?: any;
}) {
  return (
    <div>
      {markdown ? (
        <MarkdownRenderer markdown={markdown} marked={marked} />
      ) : (
        <p style={{ color: "#6b7280", fontStyle: "italic" }}>No content yet.</p>
      )}
    </div>
  );
}
