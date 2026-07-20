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
      className="px-modal-overlay items-end sm:items-center"
      role="dialog"
      aria-label={`角色档案：${character.name}`}
    >
      <button
        aria-label="关闭角色档案"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        type="button"
      />
      <article
        className="px-modal max-w-3xl sm:grid sm:grid-cols-[minmax(11rem,0.4fr)_minmax(0,0.6fr)] sm:gap-5"
        onKeyDown={handleDialogKeyDown}
        ref={dialogRef}
      >
        <button
          aria-label="关闭角色档案"
          className="px-btn absolute right-3 top-3 h-9 w-9 px-0"
          onClick={onClose}
          ref={closeButtonRef}
          type="button"
        >
          ×
        </button>
        <div className="mt-8 sm:mt-0">
          <div className="mx-auto w-32 sm:w-full sm:max-w-none">
            <CharacterPortrait character={character} />
          </div>
        </div>
        <div className="mt-4 min-w-0 sm:mt-0">
          <div className="flex flex-wrap items-center gap-2 pr-12">
            <h2 className="px-heading break-words text-xl">{character.name}</h2>
            <span className="px-badge px-badge-amber">{roleLabels[character.role]}</span>
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
      <h3 className="px-label">{label}</h3>
      <p className="px-wrap mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
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
      <h3 className="px-label">当前关系状态</h3>
      <ul className="px-wrap mt-2 grid gap-1 text-sm leading-6 text-[color:var(--muted)]">
        {facts.map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>
    </section>
  );
}
