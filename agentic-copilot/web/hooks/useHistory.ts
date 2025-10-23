// web/hooks/useHistory.ts
import { useCallback, useEffect, useState } from "react";
import { HistoryItem, loadHistory, saveHistory } from "../lib/history";

export function useHistory() {
  const [items, setItems] = useState<HistoryItem[]>([]);

  useEffect(() => {
    setItems(loadHistory());
  }, []);

  // persist whenever items change
  useEffect(() => {
    saveHistory(items);
  }, [items]);

  const add = useCallback((item: HistoryItem) => {
    setItems((prev) => {
      // prepend newest, cap to, say, 200
      const next = [item, ...prev].slice(0, 200);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((x) => x.id !== id));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  return { items, add, remove, clear };
}
