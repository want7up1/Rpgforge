"use client";

import { useRef, useState } from "react";

export function ChatDock({
  latestReply,
  input,
  disabled,
  onInput,
  onSend
}: {
  latestReply: string;
  input: string;
  disabled: boolean;
  onInput: (value: string) => void;
  onSend: () => void;
}) {
  const [height, setHeight] = useState(150);
  const dragging = useRef(false);

  function onHandleDown(e: React.PointerEvent) {
    dragging.current = true;
    (e.target as Element).setPointerCapture(e.pointerId);
  }
  function onHandleMove(e: React.PointerEvent) {
    if (!dragging.current) return;
    setHeight((h) => Math.min(420, Math.max(100, h - e.movementY)));
  }
  function onHandleUp() {
    dragging.current = false;
  }

  return (
    <div className="sticky bottom-0 z-20 border-t-2 border-[color:var(--border-strong)] bg-[rgba(4,10,6,0.97)]">
      <div
        className="mx-auto mt-1 h-1.5 w-16 cursor-row-resize bg-[color:var(--border-strong)]"
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        onPointerCancel={onHandleUp}
        title="拖动调整高度"
      />
      <div className="px-1 py-2" style={{ height }}>
        {latestReply ? (
          <p className="mb-1.5 line-clamp-2 text-xs text-[color:var(--amber)]">
            ▸ 引导：{latestReply}
          </p>
        ) : null}
        <div className="flex h-[calc(100%-1.6rem)] items-stretch gap-2">
          <div className="flex flex-1 items-start gap-2 border-2 border-[color:var(--border-strong)] bg-[color:var(--input)] px-3 py-2 shadow-[inset_2px_2px_0_0_rgba(0,0,0,0.45)] focus-within:border-[color:var(--phosphor)]">
            <span aria-hidden="true" className="command-prompt mt-0.5">&gt;</span>
            <textarea
              className="command-input flex-1"
              onChange={(e) => onInput(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  if (!disabled && input.trim()) onSend();
                }
              }}
              placeholder="追加要求 / 修正方向…（Enter 发送，Shift+Enter 换行）"
              value={input}
            />
          </div>
          <button
            className="px-btn px-btn-primary self-end"
            type="button"
            disabled={disabled || !input.trim()}
            onClick={onSend}
          >
            发送 ▸
          </button>
        </div>
      </div>
    </div>
  );
}
