// web/components/MarkdownRenderer.tsx
import { useEffect, useMemo } from "react";
import { initMermaidOnce, renderMermaidBlocks } from "../lib/mermaid";

type Props = {
  markdown: string;
  marked?: any; // function reference from dynamic import
};

export default function MarkdownRenderer({ markdown, marked }: Props) {
  const html = useMemo(() => {
    if (!markdown) return "";
    if (!marked) return markdown; // raw fallback until marked loads
    try {
      return marked.parse(markdown);
    } catch {
      return markdown;
    }
  }, [markdown, marked]);

  useEffect(() => {
    // Ensure Mermaid exists, then render any .language-mermaid blocks
    initMermaidOnce();
    renderMermaidBlocks();
  }, [html]);

  return (
    <div
      className="markdown-body"
      dangerouslySetInnerHTML={{
        __html: html || "<p><i>No content.</i></p>",
      }}
    />
  );
}
