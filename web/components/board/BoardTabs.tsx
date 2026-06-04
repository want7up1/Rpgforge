"use client";

import type { BoardCategory, BoardCategoryId } from "@/lib/generatorBoard";

export function BoardTabs({
  categories,
  activeTab,
  changedCategories,
  onSelect
}: {
  categories: BoardCategory[];
  activeTab: BoardCategoryId;
  changedCategories: Record<BoardCategoryId, number>;
  onSelect: (id: BoardCategoryId) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 border-b border-[color:var(--border)] pb-3">
      {categories.map((cat) => {
        const changed = changedCategories[cat.id] ?? 0;
        const isActive = cat.id === activeTab;
        const danger = cat.tone === "danger";
        return (
          <button
            key={cat.id}
            type="button"
            onClick={() => onSelect(cat.id)}
            className={[
              "relative rounded-full border px-3 py-1 text-sm transition",
              isActive
                ? "bg-[color:var(--foreground)] text-[color:var(--background)] border-transparent"
                : danger
                  ? "border-[#e0a23d] text-[#b5701f]"
                  : "border-[color:var(--border)]"
            ].join(" ")}
          >
            <span className="mr-1">{cat.icon}</span>
            {cat.label}
            <span className="ml-1 opacity-60">{cat.blocks.length}</span>
            {changed > 0 ? (
              <span className="absolute -right-2 -top-2 animate-pulse rounded-full bg-[#e0533d] px-1.5 py-0.5 text-[10px] font-semibold text-white">
                +{changed}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
