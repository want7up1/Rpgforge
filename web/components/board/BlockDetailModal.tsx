"use client";

import { useState } from "react";

import { BoardFieldEditor } from "@/components/board/BoardFieldEditor";
import type { BoardBlock, BoardField, BoardFieldValue } from "@/lib/generatorBoard";

export function BlockDetailModal({
  block,
  locked,
  onSave,
  onDelete,
  onUnlock,
  onSaveAsModule,
  onClose,
  aiSuggest
}: {
  block: BoardBlock;
  locked: boolean;
  onSave: (fields: BoardField[]) => void;
  onDelete: () => void;
  onUnlock?: () => void;
  onSaveAsModule?: () => void;
  onClose: () => void;
  aiSuggest?: (draft: Record<string, BoardFieldValue>) => Promise<Record<string, unknown>>;
}) {
  const [drafts, setDrafts] = useState<Record<string, BoardFieldValue>>(() =>
    Object.fromEntries(block.fields.map((f) => [f.key, f.value]))
  );
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);

  function handleSave() {
    onSave(block.fields.map((f) => ({ ...f, value: drafts[f.key] ?? f.value })));
  }

  async function handleSuggest() {
    if (!aiSuggest) return;
    setSuggesting(true);
    setSuggestError(null);
    try {
      const fields = await aiSuggest(drafts);
      setDrafts((d) => {
        const next = { ...d };
        for (const [k, v] of Object.entries(fields)) {
          const cur = next[k];
          const empty = cur == null || cur === "" || (Array.isArray(cur) && cur.length === 0);
          if (empty) next[k] = v as BoardFieldValue; // 用户已填值优先，不覆盖
        }
        return next;
      });
      if (Object.keys(fields).length === 0) setSuggestError("AI 补全失败，请手动填写");
    } catch {
      setSuggestError("AI 补全失败，请手动填写");
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="surface-panel surface-panel-strong max-h-[85vh] w-full max-w-2xl overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="surface-title">
            {block.icon} {block.title}
            {locked ? <span className="app-pill ml-2">✏ 已手动修改</span> : null}
          </h3>
          <button className="app-button" type="button" onClick={onClose}>关闭</button>
        </div>

        <div className="mt-4 grid gap-4">
          {block.fields.map((f) => (
            <label key={f.key} className="grid gap-1">
              <span className="text-sm font-semibold">{f.label}</span>
              <BoardFieldEditor
                field={f}
                value={drafts[f.key] ?? f.value}
                onChange={(v) => setDrafts((d) => ({ ...d, [f.key]: v }))}
              />
            </label>
          ))}
        </div>

        {suggestError ? <p className="mt-3 text-sm text-[#e0533d]">{suggestError}</p> : null}
        <div className="mt-5 flex flex-wrap gap-2">
          {aiSuggest ? (
            <button className="app-button" type="button" onClick={handleSuggest} disabled={suggesting}>
              {suggesting ? "AI 补全中…" : "✨ AI 补全"}
            </button>
          ) : null}
          <button className="app-button app-button-primary" type="button" onClick={handleSave}>保存</button>
          {locked && onUnlock ? (
            <button className="app-button" type="button" onClick={onUnlock} title="恢复 AI 最近一次生成的值并解除锁定">
              🔓 解锁 / 恢复 AI 原值
            </button>
          ) : null}
          {block.deletable ? (
            <button className="app-button" type="button" onClick={onDelete}>🗑 删除</button>
          ) : null}
          {onSaveAsModule ? (
            <button className="app-button" type="button" onClick={onSaveAsModule} title="把这个设定存为可复用模块">
              ⚗ 存为模块
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
