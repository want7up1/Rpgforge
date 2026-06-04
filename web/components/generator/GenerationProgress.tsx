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
  return (
    <div className="surface-panel">
      <div className="flex flex-wrap items-center gap-2">
        {items.map((i) => (
          <span
            key={i.id}
            className={[
              "rounded-full border px-2 py-1 text-xs",
              i.status === "done"
                ? "border-[#4a9a6f] text-[#2b7a4b]"
                : i.status === "running"
                  ? "border-[#e0a23d] bg-[#fff7e8]"
                  : "border-[color:var(--border)] text-[color:var(--muted)]"
            ].join(" ")}
          >
            {i.status === "done" ? "✓ " : i.status === "running" ? "⏳ " : ""}
            {i.label}
          </span>
        ))}
      </div>
      <p className="mt-2 text-xs text-[color:var(--muted)]">已生成 {done}/{items.length} 类</p>
      {reasoning || content ? (
        <details className="mt-2 rounded border border-[color:var(--border)]">
          <summary className="cursor-pointer px-3 py-2 text-xs text-[color:var(--muted)]">
            🧠 查看 AI 思考过程
          </summary>
          <pre className="app-wrap-text max-h-64 overflow-auto whitespace-pre-wrap border-t border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
            {reasoning || "（无思考流）"}
            {content ? `\n\n—— 正文 ——\n${content}` : ""}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
