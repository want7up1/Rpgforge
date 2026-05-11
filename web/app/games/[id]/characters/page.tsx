"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { CharacterPortrait } from "@/components/CharacterPortrait";
import { GamePageHeader } from "@/components/GamePageHeader";
import {
  deleteCharacterPortrait,
  getCharacters,
  getGame,
  syncCharacters,
  updateCharacter,
  uploadCharacterPortrait
} from "@/lib/api";
import type { CharacterRead, CharacterRole, GameDetail } from "@/lib/types";

const roleLabels: Record<CharacterRole, string> = {
  protagonist: "主角",
  companion: "同伴",
  npc: "NPC",
  other: "其他"
};

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; characters: CharacterRead[] }
  | { status: "error"; message: string };

type DraftState = {
  aliases: string;
  role: CharacterRole;
  identity: string;
  description: string;
  appearance: string;
  portrait_prompt: string;
  is_visible: boolean;
};

export default function CharactersPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const [game, characters] = await Promise.all([
          getGame(params.id),
          getCharacters(params.id)
        ]);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game, characters });
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setState({
            status: "error",
            message: caught instanceof Error ? caught.message : "Unknown error"
          });
        }
      }
    }

    load();

    return () => controller.abort();
  }, [params.id]);

  function replaceCharacter(updated: CharacterRead) {
    setState((current) =>
      current.status === "ready"
        ? {
            ...current,
            characters: current.characters.map((item) =>
              item.id === updated.id ? updated : item
            )
          }
        : current
    );
  }

  async function handleSync() {
    if (state.status !== "ready") {
      return;
    }
    setMessage("正在从当前游戏状态同步角色...");
    try {
      const result = await syncCharacters(state.game.id);
      setState({ ...state, characters: result.characters });
      setMessage(`同步完成：新增 ${result.created} 个，更新 ${result.updated} 个。`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "同步失败。");
    }
  }

  return (
    <AppShell variant="focus">
      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取角色档案...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <div className="mx-auto grid w-full max-w-4xl gap-4">
          <GamePageHeader
            active="characters"
            eyebrow="角色"
            gameId={params.id}
            primaryAction={
              <button
                className="app-button app-button-primary w-full sm:w-fit"
                onClick={handleSync}
                type="button"
              >
                同步角色
              </button>
            }
            subtitle={`角色档案 · ${state.characters.length} 个角色`}
            title={state.game.title}
          />

          {message ? <div className="app-status text-sm">{message}</div> : null}

          <section className="grid gap-3">
            {state.characters.length === 0 ? (
              <div className="app-card app-card-pad text-sm leading-6 text-[color:var(--muted)]">
                暂无角色档案。可以点击“同步角色”从当前游戏状态和世界书中建立档案。
              </div>
            ) : (
              state.characters.map((character) => (
                <CharacterEditor
                  character={character}
                  gameId={state.game.id}
                  key={`${character.id}-${character.updated_at}-${character.portrait_uploaded_at ?? ""}`}
                  onChange={replaceCharacter}
                />
              ))
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}

function CharacterEditor({
  character,
  gameId,
  onChange
}: {
  character: CharacterRead;
  gameId: string;
  onChange: (character: CharacterRead) => void;
}) {
  const [draft, setDraft] = useState<DraftState>(() => draftFromCharacter(character));
  const [statusText, setStatusText] = useState<string | null>(null);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusText("正在保存...");
    try {
      const updated = await updateCharacter(gameId, character.id, {
        aliases: parseAliases(draft.aliases),
        role: draft.role,
        identity: draft.identity,
        description: draft.description,
        appearance: draft.appearance,
        portrait_prompt: draft.portrait_prompt,
        is_visible: draft.is_visible,
        visibility: draft.is_visible ? "visible" : "hidden"
      });
      onChange(updated);
      setStatusText("已保存。");
    } catch (caught) {
      setStatusText(caught instanceof Error ? caught.message : "保存失败。");
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file) {
      return;
    }
    setStatusText("正在上传立绘...");
    try {
      const updated = await uploadCharacterPortrait(gameId, character.id, file);
      onChange(updated);
      setStatusText("立绘已上传。");
    } catch (caught) {
      setStatusText(caught instanceof Error ? caught.message : "上传失败。");
    } finally {
      event.currentTarget.value = "";
    }
  }

  async function handleDeletePortrait() {
    setStatusText("正在移除立绘...");
    try {
      const updated = await deleteCharacterPortrait(gameId, character.id);
      onChange(updated);
      setStatusText("立绘已移除。");
    } catch (caught) {
      setStatusText(caught instanceof Error ? caught.message : "移除失败。");
    }
  }

  return (
    <article className="app-card app-card-pad">
      <div className="grid gap-4 md:grid-cols-[12rem_minmax(0,1fr)]">
        <div className="grid content-start gap-3 md:self-start">
          <CharacterPortrait character={character} />
          <label className="app-button cursor-pointer text-center">
            上传立绘
            <input
              accept="image/png,image/jpeg,image/webp"
              className="sr-only"
              onChange={handleUpload}
              type="file"
            />
          </label>
          {character.portrait_url ? (
            <button className="app-button" onClick={handleDeletePortrait} type="button">
              移除立绘
            </button>
          ) : null}
        </div>
        <form className="grid gap-3" onSubmit={handleSave}>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-lg font-semibold">{character.name}</h2>
            <span className="app-pill">{roleLabels[character.role]}</span>
            <span className="app-pill">{character.is_visible ? "已公开" : "隐藏"}</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm">
              <span className="font-semibold">角色类型</span>
              <select
                className="app-input"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    role: event.target.value as CharacterRole
                  }))
                }
                value={draft.role}
              >
                <option value="protagonist">主角</option>
                <option value="companion">同伴</option>
                <option value="npc">NPC</option>
                <option value="other">其他</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold">别名</span>
              <input
                className="app-input"
                onChange={(event) =>
                  setDraft((current) => ({ ...current, aliases: event.target.value }))
                }
                placeholder="用逗号分隔"
                value={draft.aliases}
              />
            </label>
          </div>
          <label className="grid gap-1 text-sm">
            <span className="font-semibold">身份</span>
            <input
              className="app-input"
              onChange={(event) =>
                setDraft((current) => ({ ...current, identity: event.target.value }))
              }
              value={draft.identity}
            />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="font-semibold">公开介绍</span>
            <textarea
              className="app-input min-h-20 resize-y leading-6"
              onChange={(event) =>
                setDraft((current) => ({ ...current, description: event.target.value }))
              }
              value={draft.description}
            />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="font-semibold">外貌描述</span>
            <textarea
              className="app-input min-h-20 resize-y leading-6"
              onChange={(event) =>
                setDraft((current) => ({ ...current, appearance: event.target.value }))
              }
              value={draft.appearance}
            />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="font-semibold">立绘参考词</span>
            <textarea
              className="app-input min-h-24 resize-y leading-6"
              onChange={(event) =>
                setDraft((current) => ({ ...current, portrait_prompt: event.target.value }))
              }
              value={draft.portrait_prompt}
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              checked={draft.is_visible}
              onChange={(event) =>
                setDraft((current) => ({ ...current, is_visible: event.target.checked }))
              }
              type="checkbox"
            />
            <span>在剧情中允许点击查看</span>
          </label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <button className="app-button app-button-primary" type="submit">
              保存档案
            </button>
            {statusText ? (
              <span className="text-sm text-[color:var(--muted)]">{statusText}</span>
            ) : null}
          </div>
        </form>
      </div>
    </article>
  );
}

function draftFromCharacter(character: CharacterRead): DraftState {
  return {
    aliases: character.aliases.join("，"),
    role: character.role,
    identity: character.identity ?? "",
    description: character.description ?? "",
    appearance: character.appearance ?? "",
    portrait_prompt: character.portrait_prompt ?? "",
    is_visible: character.is_visible
  };
}

function parseAliases(value: string): string[] {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
