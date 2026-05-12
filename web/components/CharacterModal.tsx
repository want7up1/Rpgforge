"use client";

import type { CharacterRead } from "@/lib/types";

import { CharacterPortrait } from "@/components/CharacterPortrait";

const roleLabels: Record<CharacterRead["role"], string> = {
  protagonist: "主角",
  companion: "同伴",
  npc: "NPC",
  other: "角色"
};

type CharacterModalProps = {
  character: CharacterRead | null;
  onClose: () => void;
};

export function CharacterModal({ character, onClose }: CharacterModalProps) {
  if (!character) {
    return null;
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
      <article className="relative grid max-h-[92vh] w-full max-w-3xl overflow-auto rounded-lg border border-[color:var(--border)] bg-[color:var(--panel)] p-4 shadow-xl sm:grid-cols-[minmax(12rem,0.42fr)_minmax(0,0.58fr)] sm:gap-5 sm:p-5">
        <button
          className="app-button absolute right-3 top-3 h-9 w-9 px-0"
          onClick={onClose}
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
          <p className="mt-1 text-sm text-[color:var(--muted)]">
            {character.identity || "身份未公开"}
          </p>

          <InfoBlock label="身份介绍" value={character.identity} />
          <InfoBlock label="公开介绍" value={character.description} />
          <InfoBlock label="外貌描述" value={character.appearance} />
        </div>
      </article>
    </div>
  );
}

function InfoBlock({ label, value }: { label: string; value: string | null }) {
  return (
    <section className="mt-4">
      <h3 className="text-sm font-semibold">{label}</h3>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
        {value || "暂无。"}
      </p>
    </section>
  );
}
