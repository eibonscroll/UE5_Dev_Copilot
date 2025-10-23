// web/components/HistorySidebar.tsx
import { HistoryItem } from "../lib/history";

type Props = {
  items: HistoryItem[];
  open: boolean;
  onToggle: () => void;
  onSelect: (item: HistoryItem) => void;
  onClear: () => void;
  onRemove: (id: string) => void;
};

export default function HistorySidebar({
  items, open, onToggle, onSelect, onClear, onRemove,
}: Props) {
  return (
    <div style={{
      display: "flex",
      height: "100%",
      borderRight: "1px solid #eee",
      width: open ? 300 : 42,
      transition: "width 0.2s ease",
      overflow: "hidden",
      background: "#fafafa",
    }}>
      <div style={{ padding: 8 }}>
        <button onClick={onToggle} title={open ? "Collapse" : "Expand"}>
          {open ? "⟨" : "⟩"}
        </button>
      </div>
      {open && (
        <div style={{ flex: 1, overflowY: "auto", padding: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <strong>History</strong>
            <button onClick={onClear} style={{ fontSize: 12 }}>Clear</button>
          </div>
          {items.length === 0 && <div style={{ color: "#888" }}>No history yet.</div>}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((it) => (
              <li key={it.id} style={{
                padding: "8px 6px",
                border: "1px solid #eaeaea",
                borderRadius: 6,
                marginBottom: 6,
                background: "#fff",
              }}>
                <div style={{ fontSize: 12, color: "#666" }}>
                  {new Date(it.ts).toLocaleString()}
                </div>
                <div
                  onClick={() => onSelect(it)}
                  style={{ cursor: "pointer", margin: "6px 0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                  title={it.prompt}
                >
                  {it.prompt}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => onSelect(it)} style={{ fontSize: 12 }}>
                    Load
                  </button>
                  <button onClick={() => onRemove(it.id)} style={{ fontSize: 12 }}>
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
