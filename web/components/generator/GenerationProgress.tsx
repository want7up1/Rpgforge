"use client";

export type ProgressItem = {
  id: string;
  label: string;
  status: "pending" | "running" | "done";
};

export function GenerationProgress({
  items,
  reasoning,
  content
}: {
  items: ProgressItem[];
  reasoning: string;
  content: string;
}) {
  const done = items.filter((i) => i.status === "done").length;
  const percent = Math.round((done / Math.max(items.length, 1)) * 100);
  return (
    <div className="px-panel px-panel-pad">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="px-label">⚒ 锻造进度</p>
        <p className="text-xs text-[color:var(--muted)]">已生成 {done}/{items.length} 类</p>
      </div>
      <div className="px-progress-track mt-2" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={items.length} aria-label="冒险世界锻造进度">
        <div className="px-progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {items.map((i) => (
          <span
            key={i.id}
            className={
              i.status === "done"
                ? "px-badge px-badge-bright"
                : i.status === "running"
                  ? "px-badge px-badge-amber"
                  : "px-badge"
            }
          >
            {i.status === "done" ? "✓ " : i.status === "running" ? "… " : ""}
            {i.label}
          </span>
        ))}
      </div>
      {reasoning || content ? (
        <details className="px-fold mt-3">
          <summary>AI 内心独白（思考过程）</summary>
          <pre className="px-wrap max-h-64 overflow-auto whitespace-pre-wrap border-t-2 border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
            {reasoning || "（无思考流）"}
            {content ? `\n\n—— 正文 ——\n${content}` : ""}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
