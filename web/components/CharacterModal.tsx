"use client";

import { useEffect, useRef, type KeyboardEvent } from "react";

import type { CharacterRuntimeView } from "@/lib/characters";
import type { CharacterRead } from "@/lib/types";

import { CharacterPortrait } from "@/components/CharacterPortrait";

const roleLabels: Record<CharacterRead["role"], string> = {
  protagonist: "主角",
  antagonist: "反派",
  companion: "同伴",
  npc: "NPC",
  other: "角色"
};

type CharacterModalProps = {
  character: CharacterRead | null;
  onClose: () => void;
  runtimeView?: CharacterRuntimeView | null;
};

export function CharacterModal({ character, onClose, runtimeView = null }: CharacterModalProps) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!character) {
      return;
    }
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
  }, [character, onClose]);

  if (!character) {
    return null;
  }

  function handleDialogKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") {
      return;
    }
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) {
      return;
    }
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

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 grid items-end bg-black/45 p-2 sm:place-items-center sm:p-4"
      role="dialog"
    >
      <button
        aria-label="关闭角色档案"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        type="button"
      />
      <article
        className="relative grid max-h-[92vh] w-full max-w-3xl overflow-auto rounded-lg border border-[color:var(--border)] bg-[color:var(--panel)] p-4 shadow-xl sm:grid-cols-[minmax(12rem,0.42fr)_minmax(0,0.58fr)] sm:gap-5 sm:p-5"
        onKeyDown={handleDialogKeyDown}
        ref={dialogRef}
      >
        <button
          aria-label="关闭角色档案"
          className="app-button absolute right-3 top-3 h-9 w-9 px-0"
          onClick={onClose}
          ref={closeButtonRef}
          type="button"
        >
          ×
        </button>
        <div className="mt-8 sm:mt-0">
          <CharacterPortrait character={character} />
        </div>
        <div className="mt-4 min-w-0 sm:mt-0">
          <div className="flex flex-wrap items-center gap-2 pr-12">
            <h2 className="break-words text-xl font-semibold">{character.name}</h2>
            <span className="app-pill">{roleLabels[character.role]}</span>
          </div>

          <InfoBlock label="身份介绍" value={character.identity} />
          <InfoBlock label="公开介绍" value={character.description} />
          <InfoBlock label="外貌描述" value={character.appearance} />
          {runtimeView ? <RuntimeBlock runtimeView={runtimeView} /> : null}
        </div>
      </article>
    </div>
  );
}

function InfoBlock({ label, value }: { label: string; value: string | null }) {
  return (
    <section className="mt-4">
      <h3 className="text-sm font-semibold">{label}</h3>
      <p className="app-wrap-text mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
        {value || "暂无。"}
      </p>
    </section>
  );
}

function RuntimeBlock({ runtimeView }: { runtimeView: CharacterRuntimeView }) {
  const facts = [
    runtimeView.location ? `位置：${runtimeView.location}` : "",
    runtimeView.status ? `状态：${runtimeView.status}` : "",
    runtimeView.relationship ? `关系：${runtimeView.relationship}` : "",
    runtimeView.note ? `补充：${runtimeView.note}` : ""
  ].filter(Boolean);

  if (facts.length === 0) {
    return null;
  }

  return (
    <section className="mt-4">
      <h3 className="text-sm font-semibold">当前关系状态</h3>
      <ul className="app-wrap-text mt-2 grid gap-1 text-sm leading-6 text-[color:var(--muted)]">
        {facts.map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>
    </section>
  );
}
