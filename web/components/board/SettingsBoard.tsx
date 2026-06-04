"use client";

import { useState } from "react";

import { BoardTabs } from "@/components/board/BoardTabs";
import { BoardBlockGrid } from "@/components/board/BoardBlockGrid";
import { BlockDetailModal } from "@/components/board/BlockDetailModal";
import { ChangeSummaryBar } from "@/components/board/ChangeSummaryBar";
import { ARRAY_SPECS, EMPTY_DIFF, newItemBlock } from "@/lib/generatorBoard";
import type {
  BoardBlock,
  BoardCategoryId,
  BoardDiff,
  BoardField,
  BoardModel
} from "@/lib/generatorBoard";

export function SettingsBoard({
  model,
  diff = EMPTY_DIFF,
  lockedIds = [],
  loading,
  onEditBlock,
  onDeleteBlock,
  onUnlockBlock,
  onSaveAsModule,
  onAddItem
}: {
  model: BoardModel;
  diff?: BoardDiff;
  lockedIds?: string[];
  loading: boolean;
  onEditBlock: (block: BoardBlock, fields: BoardField[]) => void;
  onDeleteBlock: (block: BoardBlock) => void;
  onUnlockBlock?: (block: BoardBlock) => void;
  onSaveAsModule?: (block: BoardBlock) => void;
  onAddItem?: (arrayKey: string, item: Record<string, unknown>) => void;
}) {
  const [activeTab, setActiveTab] = useState<BoardCategoryId>("world");
  const [openBlock, setOpenBlock] = useState<BoardBlock | null>(null);
  const [showEmpty, setShowEmpty] = useState(false);
  const [addingArray, setAddingArray] = useState<string | null>(null);

  const current = model.categories.find((c) => c.id === activeTab) ?? model.categories[0];

  return (
    <section className="surface-panel surface-panel-strong">
      <ChangeSummaryBar model={model} diff={diff} onJump={setActiveTab} />
      <BoardTabs
        categories={model.categories}
        activeTab={activeTab}
        changedCategories={diff.changedCategories}
        onSelect={setActiveTab}
      />
      <label className="mt-3 flex w-fit items-center gap-2 text-xs text-[color:var(--muted)]">
        <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} />
        显示空设定项
      </label>
      <BoardBlockGrid
        category={activeTab}
        blocks={current.blocks}
        changedBlockIds={diff.changedBlockIds}
        lockedIds={lockedIds}
        loading={loading}
        showEmpty={showEmpty}
        onOpen={setOpenBlock}
        onAdd={onAddItem ? (arrayKey) => setAddingArray(arrayKey) : undefined}
      />
      {openBlock ? (
        <BlockDetailModal
          block={openBlock}
          locked={lockedIds.includes(openBlock.id)}
          onSave={(fields) => { onEditBlock(openBlock, fields); setOpenBlock(null); }}
          onDelete={() => { onDeleteBlock(openBlock); setOpenBlock(null); }}
          onUnlock={
            onUnlockBlock
              ? () => { onUnlockBlock(openBlock); setOpenBlock(null); }
              : undefined
          }
          onSaveAsModule={
            onSaveAsModule ? () => { onSaveAsModule(openBlock); setOpenBlock(null); } : undefined
          }
          onClose={() => setOpenBlock(null)}
        />
      ) : null}
      {addingArray ? (
        <BlockDetailModal
          block={newItemBlock(addingArray)}
          locked={false}
          onSave={(fields) => {
            const spec = ARRAY_SPECS[addingArray];
            const item = Object.fromEntries(fields.map((f) => [f.key, f.value]));
            const idKey = spec?.idKey ?? "id";
            if (!String(item[idKey] ?? "").trim()) return; // 身份必填（重名/合法性由后端 validate 兜底）
            onAddItem?.(addingArray, item);
            setAddingArray(null);
          }}
          onDelete={() => setAddingArray(null)}
          onClose={() => setAddingArray(null)}
        />
      ) : null}
    </section>
  );
}
