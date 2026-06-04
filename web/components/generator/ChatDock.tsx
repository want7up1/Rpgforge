"use client";

import { useRef, useState } from "react";

export function ChatDock({
  latestReply,
  input,
  disabled,
  onInput,
  onSend,
  onToggleHistory
}: {
  latestReply: string;
  input: string;
  disabled: boolean;
  onInput: (value: string) => void;
  onSend: () => void;
  onToggleHistory: () => void;
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
    <div className="sticky bottom-0 z-20 border-t border-[color:var(--border)] bg-[color:var(--background)]">
      <div
        className="mx-auto h-2 w-16 cursor-row-resize rounded-full bg-[color:var(--border)]"
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        onPointerCancel={onHandleUp}
        title="拖动调整高度"
      />
      <div className="px-1 py-2" style={{ height }}>
        {latestReply ? (
          <p className="mb-2 line-clamp-2 text-xs text-[color:var(--muted)]">💬 引导：{latestReply}</p>
        ) : null}
        <div className="flex h-[calc(100%-2rem)] gap-2">
          <textarea
            className="app-input flex-1 resize-none leading-6"
            placeholder="追加要求 / 修正方向…"
            value={input}
            onChange={(e) => onInput(e.target.value)}
          />
          <div className="flex flex-col gap-2">
            <button className="app-button app-button-primary" type="button" disabled={disabled || !input.trim()} onClick={onSend}>发送</button>
            <button className="app-button" type="button" onClick={onToggleHistory}>⌃ 历史</button>
          </div>
        </div>
      </div>
    </div>
  );
}
