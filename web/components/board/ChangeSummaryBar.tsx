"use client";

import type { BoardModel, BoardCategoryId, BoardDiff } from "@/lib/generatorBoard";

export function ChangeSummaryBar({
  model,
  diff,
  onJump
}: {
  model: BoardModel;
  diff: BoardDiff;
  onJump: (id: BoardCategoryId) => void;
}) {
  const changed = model.categories.filter((c) => (diff.changedCategories[c.id] ?? 0) > 0);
  if (changed.length === 0) return null;
  return (
    <div className="px-warning mb-3 flex flex-wrap items-center gap-2 !p-2 text-sm">
      <span>⚑ 本次更新了：</span>
      {changed.map((c) => (
        <button key={c.id} type="button" className="px-badge px-badge-amber" onClick={() => onJump(c.id)}>
          {c.label} +{diff.changedCategories[c.id]}
        </button>
      ))}
    </div>
  );
}
