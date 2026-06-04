"use client";

import { useState } from "react";

import type { BoardBlock, BoardField } from "@/lib/generatorBoard";

function fieldToText(field: BoardField): string {
  return Array.isArray(field.value) ? field.value.join("\n") : field.value;
}
function textToFieldValue(field: BoardField, text: string): string | string[] {
  return field.type === "stringList"
    ? text.split("\n").map((s) => s.trim()).filter(Boolean)
    : text;
}

export function BlockDetailModal({
  block,
  locked,
  onSave,
  onDelete,
  onUnlock,
  onSaveAsModule,
  onClose
}: {
  block: BoardBlock;
  locked: boolean;
  onSave: (fields: BoardField[]) => void;
  onDelete: () => void;
  onUnlock?: () => void;
  onSaveAsModule?: () => void;
  onClose: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(block.fields.map((f) => [f.key, fieldToText(f)]))
  );

  function handleSave() {
    const next = block.fields.map((f) => ({
      ...f,
      value: textToFieldValue(f, drafts[f.key] ?? fieldToText(f))
    }));
    onSave(next);
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
              <span className="text-sm font-semibold">
                {f.label}
                {f.type === "stringList" ? (
                  <span className="ml-2 text-xs text-[color:var(--muted)]">每行一条</span>
                ) : null}
              </span>
              {f.type === "text" ? (
                <input
                  className="app-input"
                  value={drafts[f.key] ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [f.key]: e.target.value }))}
                />
              ) : (
                <textarea
                  className="app-input min-h-24 resize-y leading-6"
                  value={drafts[f.key] ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [f.key]: e.target.value }))}
                />
              )}
            </label>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
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
