"use client";

import type { GeneratorMessage } from "@/lib/types";

export function ChatHistorySheet({
  open,
  history,
  onClose
}: {
  open: boolean;
  history: GeneratorMessage[];
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/30" onClick={onClose}>
      <div className="surface-panel max-h-[60vh] w-full overflow-auto rounded-b-none" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="surface-title">对话历史</h3>
          <button className="app-button" type="button" onClick={onClose}>收起</button>
        </div>
        <div className="mt-3 grid gap-2">
          {history.length === 0 ? (
            <p className="surface-subtle">暂无对话。</p>
          ) : (
            history.map((m, i) => (
              <div
                key={`${m.role}-${i}`}
                className={
                  m.role === "user"
                    ? "archive-card archive-card-green text-sm leading-6"
                    : "archive-card archive-card-accent text-sm leading-6"
                }
              >
                <span className="font-semibold">{m.role === "user" ? "你" : "冒险引导"}</span>
                <p className="mt-1 text-[color:var(--muted)]">{m.content}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
