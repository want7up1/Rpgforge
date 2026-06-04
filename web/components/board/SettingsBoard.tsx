"use client";

import { useState } from "react";

import { BoardTabs } from "@/components/board/BoardTabs";
import { BoardBlockGrid } from "@/components/board/BoardBlockGrid";
import { BlockDetailModal } from "@/components/board/BlockDetailModal";
import { ChangeSummaryBar } from "@/components/board/ChangeSummaryBar";
import { EMPTY_DIFF } from "@/lib/generatorBoard";
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
  onSaveAsModule
}: {
  model: BoardModel;
  diff?: BoardDiff;
  lockedIds?: string[];
  loading: boolean;
  onEditBlock: (block: BoardBlock, fields: BoardField[]) => void;
  onDeleteBlock: (block: BoardBlock) => void;
  onUnlockBlock?: (block: BoardBlock) => void;
  onSaveAsModule?: (block: BoardBlock) => void;
}) {
  const [activeTab, setActiveTab] = useState<BoardCategoryId>("world");
  const [openBlock, setOpenBlock] = useState<BoardBlock | null>(null);

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
      <BoardBlockGrid
        blocks={current.blocks}
        changedBlockIds={diff.changedBlockIds}
        lockedIds={lockedIds}
        loading={loading}
        onOpen={setOpenBlock}
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
    </section>
  );
}
