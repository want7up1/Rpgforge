"use client";

import type { BoardBlock } from "@/lib/generatorBoard";

export function BoardBlockGrid({
  blocks,
  changedBlockIds,
  lockedIds,
  loading,
  onOpen
}: {
  blocks: BoardBlock[];
  changedBlockIds: Set<string>;
  lockedIds: string[];
  loading: boolean;
  onOpen: (block: BoardBlock) => void;
}) {
  if (loading && blocks.length === 0) {
    return (
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="archive-card h-20 animate-pulse opacity-60" />
        ))}
      </div>
    );
  }
  if (blocks.length === 0) {
    return (
      <p className="surface-panel surface-subtle mt-4">
        这一类还没有设定，确认方向 / 生成世界后会自动补全。
      </p>
    );
  }
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {blocks.map((block) => {
        const changed = changedBlockIds.has(block.id);
        const locked = lockedIds.includes(block.id);
        return (
          <button
            key={block.id}
            type="button"
            onClick={() => onOpen(block)}
            className={[
              "archive-card text-left transition",
              changed ? "ring-2 ring-[#4a9a6f] animate-[pulse_1s_ease-in-out_3]" : ""
            ].join(" ")}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{block.icon} {block.title}</span>
              <span className="flex gap-1">
                {locked ? <span className="app-pill">✏ 已改</span> : null}
                {changed ? <span className="app-pill">刚更新</span> : null}
              </span>
            </div>
            {block.summary ? (
              <p className="mt-1 text-xs text-[color:var(--muted)]">{block.summary}</p>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
