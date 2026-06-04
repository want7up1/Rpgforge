"use client";

import { ARRAY_SPECS, isEmptyBlock, type BoardBlock, type BoardCategoryId } from "@/lib/generatorBoard";

// 各分类可新增的数组键
const CATEGORY_ARRAYS: Partial<Record<BoardCategoryId, string[]>> = {
  characters: ["core_characters"],
  plot: ["act_plan", "main_quest_path"],
  mechanics: ["core_mechanics", "action_style_rules"],
  materials: ["story_material_library"]
};

export function BoardBlockGrid({
  category,
  blocks,
  changedBlockIds,
  lockedIds,
  loading,
  showEmpty,
  onOpen,
  onAdd
}: {
  category: BoardCategoryId;
  blocks: BoardBlock[];
  changedBlockIds: Set<string>;
  lockedIds: string[];
  loading: boolean;
  showEmpty: boolean;
  onOpen: (block: BoardBlock) => void;
  onAdd?: (arrayKey: string) => void;
}) {
  const visible = showEmpty ? blocks : blocks.filter((b) => !isEmptyBlock(b));
  const addArrays = onAdd ? CATEGORY_ARRAYS[category] ?? [] : [];

  if (loading && visible.length === 0 && addArrays.length === 0) {
    return (
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="archive-card h-20 animate-pulse opacity-60" />
        ))}
      </div>
    );
  }

  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {visible.map((block) => {
        const changed = changedBlockIds.has(block.id);
        const locked = lockedIds.includes(block.id);
        const empty = isEmptyBlock(block);
        return (
          <button
            key={block.id}
            type="button"
            onClick={() => onOpen(block)}
            className={[
              "archive-card text-left transition",
              changed ? "ring-2 ring-[#4a9a6f] animate-[pulse_1s_ease-in-out_3]" : "",
              empty ? "opacity-50" : ""
            ].join(" ")}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{block.icon} {block.title}</span>
              <span className="flex gap-1">
                {locked ? <span className="app-pill">✏ 已改</span> : null}
                {changed ? <span className="app-pill">刚更新</span> : null}
              </span>
            </div>
            <p className="mt-1 text-xs text-[color:var(--muted)]">{empty ? "未设置 · 点击填写" : block.summary}</p>
          </button>
        );
      })}
      {addArrays.map((arrayKey) => (
        <button
          key={`add-${arrayKey}`}
          type="button"
          onClick={() => onAdd?.(arrayKey)}
          className="archive-card border-dashed text-left text-[color:var(--accent-strong)]"
        >
          ＋ 新增{ARRAY_SPECS[arrayKey]?.label ?? "项"}
        </button>
      ))}
      {visible.length === 0 && addArrays.length === 0 ? (
        <p className="surface-subtle">这一类暂无设定。{!showEmpty ? "（打开「显示空设定项」可填写空项）" : ""}</p>
      ) : null}
    </div>
  );
}
