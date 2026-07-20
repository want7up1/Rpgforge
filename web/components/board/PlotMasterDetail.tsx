"use client";

import { useState } from "react";

import { BlockDetailModal } from "@/components/board/BlockDetailModal";
import { newItemBlock, generateItemId, itemIdsOf } from "@/lib/generatorBoard";
import type { BoardBlock, BoardField, BoardModel } from "@/lib/generatorBoard";
import { actKeyOf, derivePlotView } from "@/lib/plotView";

type Adding = "act" | "node" | null;

export function PlotMasterDetail({
  model,
  lockedIds = [],
  changedBlockIds,
  onEditBlock,
  onDeleteBlock,
  onAddItem,
  onUnlockBlock,
  onSuggestItem
}: {
  model: BoardModel;
  lockedIds?: string[];
  changedBlockIds?: Set<string>;
  onEditBlock: (block: BoardBlock, fields: BoardField[]) => void;
  onDeleteBlock: (block: BoardBlock) => void;
  onAddItem?: (arrayKey: string, item: Record<string, unknown>) => void;
  onUnlockBlock?: (block: BoardBlock) => void;
  onSuggestItem?: (arrayKey: string, draft: Record<string, unknown>) => Promise<Record<string, unknown>>;
}) {
  const { overview, acts, unassignedNodes } = derivePlotView(model);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [openBlock, setOpenBlock] = useState<BoardBlock | null>(null);
  const [adding, setAdding] = useState<Adding>(null);

  const selectedAct = acts.find((a) => actKeyOf(a.actBlock) === selectedKey) ?? acts[0] ?? null;
  const changed = (id: string) => changedBlockIds?.has(id) ?? false;

  function preview(block: BoardBlock, key: string): string {
    const f = block.fields.find((x) => x.key === key);
    return typeof f?.value === "string" ? f.value : "";
  }

  // 新增弹窗用的合成块：新增节点时把 act_id 预填为当前选中幕。
  const addingBlock: BoardBlock | null =
    adding === "act"
      ? newItemBlock("act_plan")
      : adding === "node"
        ? (() => {
            const base = newItemBlock("main_quest_path");
            const actId = selectedAct ? actKeyOf(selectedAct.actBlock) : "";
            // act_id 字段已在完整规格里，预填为当前选中幕
            return {
              ...base,
              fields: base.fields.map((f) => (f.key === "act_id" ? { ...f, value: actId } : f))
            };
          })()
        : null;

  return (
    <div className="mt-3">
      {/* 顶部：剧情纲领总览 */}
      <section className="px-panel px-panel-pad mb-4">
        <h4 className="px-heading text-sm mb-2">🎯 剧情纲领总览</h4>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {overview.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => setOpenBlock(b)}
              className={[
                "border-2 p-3 text-left transition hover:border-[color:var(--phosphor)]",
                changed(b.id) ? "border-[#ff6b5e]" : "border-[color:var(--border)]"
              ].join(" ")}
            >
              <div className="px-label">{b.title}</div>
              <div className="mt-1 text-sm">
                {preview(b, b.fields[0]?.key ?? "") || <span className="opacity-40">（空，点击填写）</span>}
              </div>
            </button>
          ))}
        </div>
      </section>

      <div className="flex flex-col gap-4 md:flex-row md:items-start">
        {/* 左：幕大纲 */}
        <div className="md:w-1/3">
          <div className="px-label mb-2">幕大纲</div>
          <div className="grid gap-2">
            {acts.map((a) => {
              const key = actKeyOf(a.actBlock);
              const isSel = selectedAct ? actKeyOf(selectedAct.actBlock) === key : false;
              return (
                <button
                  key={a.actBlock.id}
                  type="button"
                  onClick={() => setSelectedKey(key)}
                  className={[
                    "border-2 p-3 text-left transition",
                    isSel ? "border-[color:var(--amber)] bg-[rgba(255,179,71,0.08)]" : "border-[color:var(--border)]",
                    changed(a.actBlock.id) ? "ring-2 ring-[#ff6b5e]" : ""
                  ].join(" ")}
                >
                  <div className="font-bold">{a.actBlock.title}</div>
                  <div className="mt-1 text-xs opacity-60">{a.nodes.length} 节点</div>
                </button>
              );
            })}
            {acts.length === 0 ? <p className="text-sm opacity-60">还没有幕，点下方新增。</p> : null}
            {onAddItem ? (
              <button
                type="button"
                onClick={() => setAdding("act")}
                className="border-2 border-dashed border-[color:var(--border)] p-2 text-sm text-[color:var(--phosphor)] opacity-80 hover:opacity-100"
              >
                ＋ 新增幕
              </button>
            ) : null}
          </div>
        </div>

        {/* 右：选中幕详情 */}
        <div className="flex-1">
          {selectedAct ? (
            <div className="px-panel px-panel-pad">
              <div className="flex items-center justify-between gap-2">
                <h4 className="px-heading text-sm">{selectedAct.actBlock.title}</h4>
                <button className="px-btn" type="button" onClick={() => setOpenBlock(selectedAct.actBlock)}>
                  编辑此幕
                </button>
              </div>
              <p className="mt-1 text-sm text-[color:var(--muted)]">
                {preview(selectedAct.actBlock, "objective") || "（未填目标）"}
              </p>

              <div className="px-label mb-2 mt-4">主线节点（{selectedAct.nodes.length}）</div>
              <div className="grid gap-2">
                {selectedAct.nodes.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => setOpenBlock(n)}
                    className={[
                      "border-2 p-3 text-left transition hover:border-[color:var(--phosphor)]",
                      changed(n.id) ? "border-[#ff6b5e]" : "border-[color:var(--border)]"
                    ].join(" ")}
                  >
                    <div className="font-bold">{n.title}</div>
                    <div className="mt-1 text-xs opacity-60">{preview(n, "objective")}</div>
                  </button>
                ))}
                {selectedAct.nodes.length === 0 ? (
                  <p className="text-sm opacity-60">这一幕还没有主线节点。</p>
                ) : null}
                {onAddItem ? (
                  <button
                    type="button"
                    onClick={() => setAdding("node")}
                    className="border-2 border-dashed border-[color:var(--border)] p-2 text-sm text-[color:var(--phosphor)] opacity-80 hover:opacity-100"
                  >
                    ＋ 新增主线节点
                  </button>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-sm opacity-60">左侧选择或新增一幕开始编辑。</p>
          )}

          {/* 未分配节点 */}
          {unassignedNodes.length > 0 ? (
            <div className="px-panel px-panel-pad mt-4 border-[#8a6420]">
              <div className="px-label mb-2 text-[color:var(--amber)]">⚠ 未分配节点（act_id 无对应幕）</div>
              <div className="grid gap-2">
                {unassignedNodes.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => setOpenBlock(n)}
                    className="border-2 border-[color:var(--border)] p-3 text-left"
                  >
                    <div className="font-bold">{n.title}</div>
                    <div className="mt-1 text-xs opacity-60">act_id: {preview(n, "act_id") || "（空）"}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* 编辑现有块 */}
      {openBlock ? (
        <BlockDetailModal
          block={openBlock}
          locked={lockedIds.includes(openBlock.id)}
          onSave={(fields) => {
            onEditBlock(openBlock, fields);
            setOpenBlock(null);
          }}
          onDelete={() => {
            onDeleteBlock(openBlock);
            setOpenBlock(null);
          }}
          onUnlock={onUnlockBlock ? () => { onUnlockBlock(openBlock); setOpenBlock(null); } : undefined}
          onClose={() => setOpenBlock(null)}
        />
      ) : null}

      {/* 新增幕 / 节点 */}
      {adding && addingBlock && onAddItem ? (
        <BlockDetailModal
          block={addingBlock}
          locked={false}
          onSave={(fields) => {
            const arrayKey = adding === "node" ? "main_quest_path" : "act_plan";
            const item = Object.fromEntries(fields.map((f) => [f.key, f.value]));
            // 自动生成唯一 id（不再让用户手填）
            if (!String(item.id ?? "").trim()) {
              item.id = generateItemId(arrayKey, itemIdsOf(model, arrayKey));
            }
            onAddItem(arrayKey, item);
            setAdding(null);
          }}
          onDelete={() => setAdding(null)}
          aiSuggest={
            onSuggestItem
              ? (draft) => onSuggestItem(adding === "node" ? "main_quest_path" : "act_plan", draft)
              : undefined
          }
          onClose={() => setAdding(null)}
        />
      ) : null}
    </div>
  );
}
