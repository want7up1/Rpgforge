"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

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
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  // 无障碍：Esc 关闭 + 打开聚焦关闭按钮 + 关闭恢复原焦点（与 CharacterModal 同模式）
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [onClose]);

  // Tab 焦点陷阱：循环停留在弹窗内
  function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

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
          // 仅覆盖用户尚未改动的字段（值仍等于初始值）→ 布尔默认 false 也能被 AI 建议填入，
          // 同时保留用户已填/改过的值不被覆盖。
          const initial = block.fields.find((f) => f.key === k)?.value;
          if (JSON.stringify(next[k]) === JSON.stringify(initial)) {
            next[k] = v as BoardFieldValue;
          }
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
    <div
      aria-modal="true"
      role="dialog"
      aria-label={block.title}
      className="px-modal-overlay"
    >
      <button aria-label="关闭" className="absolute inset-0 cursor-default" type="button" onClick={onClose} />
      <div
        ref={dialogRef}
        onKeyDown={handleDialogKeyDown}
        className="px-modal max-w-2xl"
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="px-heading text-base">
            {block.icon} {block.title}
            {locked ? <span className="px-badge px-badge-bright ml-2">✏ 已手动修改</span> : null}
          </h3>
          <button ref={closeButtonRef} className="px-btn" type="button" onClick={onClose}>关闭</button>
        </div>

        <div className="mt-4 grid gap-4">
          {block.fields.map((f) => (
            <label key={f.key} className="grid gap-1">
              <span className="px-label">{f.label}</span>
              <BoardFieldEditor
                field={f}
                value={drafts[f.key] ?? f.value}
                onChange={(v) => setDrafts((d) => ({ ...d, [f.key]: v }))}
              />
            </label>
          ))}
        </div>

        {suggestError ? <p className="mt-3 text-sm text-[#ff6b5e]">{suggestError}</p> : null}
        <div className="mt-5 flex flex-wrap gap-2">
          {aiSuggest ? (
            <button className="px-btn px-btn-amber" type="button" onClick={handleSuggest} disabled={suggesting}>
              {suggesting ? "AI 补全中…" : "✦ AI 补全"}
            </button>
          ) : null}
          <button className="px-btn px-btn-primary" type="button" onClick={handleSave}>保存</button>
          {locked && onUnlock ? (
            <button className="px-btn" type="button" onClick={onUnlock} title="恢复 AI 最近一次生成的值并解除锁定">
              🔓 解锁 / 恢复 AI 原值
            </button>
          ) : null}
          {block.deletable ? (
            <button className="px-btn px-btn-danger" type="button" onClick={onDelete}>✕ 删除</button>
          ) : null}
          {onSaveAsModule ? (
            <button className="px-btn" type="button" onClick={onSaveAsModule} title="把这个设定存为可复用模块">
              ⚗ 存为模块
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
