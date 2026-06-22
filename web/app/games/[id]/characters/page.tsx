"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { CharacterPortrait } from "@/components/CharacterPortrait";
import { GamePageHeader } from "@/components/GamePageHeader";
import {
  buildCharacterRuntimeView,
  characterRoleLabels,
  normalizeCharacterName,
  normalizeStoryProfile,
  storyProfileLabels,
  type CharacterRuntimeView
} from "@/lib/characters";
import {
  deleteCharacterPortrait,
  getCharacters,
  getGame,
  syncCharacters,
  updateCharacter,
  uploadCharacterPortrait
} from "@/lib/api";
import { getStateV2FromGame } from "@/lib/stateV2";
import type {
  CharacterRead,
  CharacterRole,
  CharacterStoryProfile,
  GameDetail
} from "@/lib/types";

const roleOrder: CharacterRole[] = ["protagonist", "antagonist", "companion", "npc", "other"];
const allowedPortraitTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
const maxPortraitBytes = 8 * 1024 * 1024;

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; characters: CharacterRead[] }
  | { status: "error"; message: string };

type DraftState = {
  name: string;
  aliases: string;
  role: CharacterRole;
  identity: string;
  description: string;
  appearance: string;
  is_visible: boolean;
  story_profile: CharacterStoryProfile;
};

type Filters = {
  query: string;
  role: "all" | CharacterRole;
  visibility: "all" | "visible" | "hidden";
  source: "all" | string;
};

export default function CharactersPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [message, setMessage] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({
    query: "",
    role: "all",
    visibility: "all",
    source: "all"
  });
  const [syncing, setSyncing] = useState(false);

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

  const stateV2 = useMemo(
    () => (state.status === "ready" ? getStateV2FromGame(state.game) : null),
    [state]
  );

  const sources = useMemo(() => {
    if (state.status !== "ready") {
      return [];
    }
    return Array.from(new Set(state.characters.map((character) => character.source))).sort();
  }, [state]);

  const groupedCharacters = useMemo(() => {
    if (state.status !== "ready") {
      return [];
    }
    const filtered = state.characters.filter((character) => characterMatchesFilters(character, filters));
    return roleOrder
      .map((role) => ({
        role,
        characters: filtered.filter((character) => character.role === role)
      }))
      .filter((group) => group.characters.length > 0);
  }, [filters, state]);

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
    if (state.status !== "ready" || syncing) {
      return;
    }
    setSyncing(true);
    setMessage("正在从当前游戏状态同步角色...");
    try {
      const result = await syncCharacters(state.game.id);
      setState({ ...state, characters: result.characters });
      setMessage(`同步完成：新增 ${result.created} 个，更新 ${result.updated} 个。`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "同步失败。");
    } finally {
      setSyncing(false);
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
        <div className="mx-auto grid w-full max-w-6xl gap-4">
          <GamePageHeader
            active="characters"
            eyebrow="角色"
            gameId={params.id}
            primaryAction={
              <button
                className="app-button app-button-primary w-full sm:w-fit"
                disabled={syncing}
                onClick={handleSync}
                type="button"
              >
                {syncing ? "同步中..." : "同步角色"}
              </button>
            }
            subtitle={`角色档案 · ${state.characters.length} 个角色`}
            title={state.game.title}
          />

          <CharacterFilters
            filters={filters}
            onChange={setFilters}
            sources={sources}
          />

          {message ? <div className="app-status text-sm">{message}</div> : null}

          <section className="grid gap-4">
            {state.characters.length === 0 ? (
              <div className="surface-panel text-sm leading-6 text-[color:var(--muted)]">
                暂无角色档案。可以点击“同步角色”从当前游戏状态和剧本设定中建立档案。
              </div>
            ) : groupedCharacters.length === 0 ? (
              <div className="surface-panel text-sm leading-6 text-[color:var(--muted)]">
                没有符合筛选条件的角色。
              </div>
            ) : (
              groupedCharacters.map((group) => (
                <section className="grid gap-3" key={group.role}>
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-lg font-black">{characterRoleLabels[group.role]}</h2>
                    <span className="app-pill">{group.characters.length}</span>
                  </div>
                  {group.characters.map((character) => (
                    <CharacterEditor
                      character={character}
                      gameId={state.game.id}
                      key={`${character.id}-${character.updated_at}-${character.portrait_uploaded_at ?? ""}`}
                      onChange={replaceCharacter}
                      runtimeView={buildCharacterRuntimeView(character, stateV2)}
                    />
                  ))}
                </section>
              ))
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}

function CharacterFilters({
  filters,
  onChange,
  sources
}: {
  filters: Filters;
  onChange: (filters: Filters) => void;
  sources: string[];
}) {
  return (
    <section className="surface-panel grid gap-3 md:grid-cols-[minmax(0,1fr)_10rem_10rem_10rem]">
      <label className="grid gap-1 text-sm">
        <span className="font-semibold">搜索</span>
        <input
          className="app-input"
          onChange={(event) => onChange({ ...filters, query: event.target.value })}
          placeholder="姓名、别名、身份、介绍"
          value={filters.query}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-semibold">类型</span>
        <select
          className="app-input"
          onChange={(event) =>
            onChange({ ...filters, role: event.target.value as Filters["role"] })
          }
          value={filters.role}
        >
          <option value="all">全部</option>
          {roleOrder.map((role) => (
            <option key={role} value={role}>
              {characterRoleLabels[role]}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-semibold">可见性</span>
        <select
          className="app-input"
          onChange={(event) =>
            onChange({ ...filters, visibility: event.target.value as Filters["visibility"] })
          }
          value={filters.visibility}
        >
          <option value="all">全部</option>
          <option value="visible">已公开</option>
          <option value="hidden">隐藏</option>
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-semibold">来源</span>
        <select
          className="app-input"
          onChange={(event) => onChange({ ...filters, source: event.target.value })}
          value={filters.source}
        >
          <option value="all">全部</option>
          {sources.map((source) => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

function CharacterEditor({
  character,
  gameId,
  onChange,
  runtimeView
}: {
  character: CharacterRead;
  gameId: string;
  onChange: (character: CharacterRead) => void;
  runtimeView: CharacterRuntimeView | null;
}) {
  const [draft, setDraft] = useState<DraftState>(() => draftFromCharacter(character));
  const [statusText, setStatusText] = useState<string | null>(null);
  const [operation, setOperation] = useState<"save" | "upload" | "delete" | null>(null);
  const busy = operation !== null;

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) {
      return;
    }
    setOperation("save");
    setStatusText("正在保存...");
    try {
      const updated = await updateCharacter(gameId, character.id, {
        name: draft.name,
        aliases: parseAliases(draft.aliases),
        role: draft.role,
        identity: draft.identity,
        description: draft.description,
        appearance: draft.appearance,
        story_profile: normalizeStoryProfile(draft.story_profile),
        visibility: draft.is_visible ? "visible" : "hidden",
        is_visible: draft.is_visible
      });
      onChange(updated);
      setDraft(draftFromCharacter(updated));
      setStatusText("已保存。");
    } catch (caught) {
      setStatusText(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      setOperation(null);
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file || busy) {
      return;
    }
    if (!allowedPortraitTypes.has(file.type)) {
      setStatusText("只支持 PNG、JPG、WEBP 立绘图片。");
      event.currentTarget.value = "";
      return;
    }
    if (file.size > maxPortraitBytes) {
      setStatusText("立绘图片不能超过 8MB。");
      event.currentTarget.value = "";
      return;
    }
    setOperation("upload");
    setStatusText("正在上传立绘...");
    try {
      const updated = await uploadCharacterPortrait(gameId, character.id, file);
      onChange(updated);
      setStatusText("立绘已上传。");
    } catch (caught) {
      setStatusText(caught instanceof Error ? caught.message : "上传失败。");
    } finally {
      event.currentTarget.value = "";
      setOperation(null);
    }
  }

  async function handleDeletePortrait() {
    if (busy) {
      return;
    }
    setOperation("delete");
    setStatusText("正在移除立绘...");
    try {
      const updated = await deleteCharacterPortrait(gameId, character.id);
      onChange(updated);
      setStatusText("立绘已移除。");
    } catch (caught) {
      setStatusText(caught instanceof Error ? caught.message : "移除失败。");
    } finally {
      setOperation(null);
    }
  }

  return (
    <article className="character-card">
      <div className="character-editor-layout">
        <div className="character-editor-media md:self-start">
          <CharacterPortrait character={character} className="character-editor-portrait" />
          <label className={`app-button cursor-pointer text-center ${busy ? "opacity-60" : ""}`}>
            {operation === "upload" ? "上传中..." : "上传立绘"}
            <input
              accept="image/png,image/jpeg,image/webp"
              className="sr-only"
              disabled={busy}
              onChange={handleUpload}
              type="file"
            />
          </label>
          {character.portrait_url ? (
            <button
              className="app-button"
              disabled={busy}
              onClick={handleDeletePortrait}
              type="button"
            >
              {operation === "delete" ? "移除中..." : "移除立绘"}
            </button>
          ) : null}
          {statusText ? (
            <span className="text-sm leading-5 text-[color:var(--muted)]">{statusText}</span>
          ) : null}
        </div>

        <div className="grid content-start gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-2xl font-black">{character.name}</h2>
            <span className="app-pill">{characterRoleLabels[character.role]}</span>
            <span className="app-pill">{character.is_visible ? "已公开" : "隐藏"}</span>
            <span className="app-pill">{character.source}</span>
          </div>

          <section className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <CharacterReadOnlyBlock label="身份介绍" value={character.identity} />
            <CharacterReadOnlyBlock label="公开介绍" value={character.description} wide />
            <CharacterReadOnlyBlock label="外貌描述" value={character.appearance} wide />
          </section>

          <RuntimeStateBlock runtimeView={runtimeView} />

          <details className="character-edit-details">
            <summary className="cursor-pointer font-semibold">导演字段</summary>
            <StoryProfileGrid storyProfile={character.story_profile} />
          </details>

          <details className="character-edit-details">
            <summary className="cursor-pointer font-semibold">编辑角色档案</summary>
            <form className="character-card-form mt-4" onSubmit={handleSave}>
              <label className="grid gap-1 text-sm">
                <span className="font-semibold">角色名称</span>
                <input
                  className="app-input"
                  disabled={busy}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, name: event.target.value }))
                  }
                  value={draft.name}
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-semibold">别名</span>
                <textarea
                  className="app-input min-h-16 resize-y leading-6"
                  disabled={busy}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, aliases: event.target.value }))
                  }
                  placeholder="每行一个，或用逗号分隔"
                  value={draft.aliases}
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-semibold">角色类型</span>
                <select
                  className="app-input"
                  disabled={busy}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      role: event.target.value as CharacterRole
                    }))
                  }
                  value={draft.role}
                >
                  {roleOrder.map((role) => (
                    <option key={role} value={role}>
                      {characterRoleLabels[role]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-semibold">身份介绍</span>
                <input
                  className="app-input"
                  disabled={busy}
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
                  disabled={busy}
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
                  disabled={busy}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, appearance: event.target.value }))
                  }
                  value={draft.appearance}
                />
              </label>
              <StoryProfileEditor
                disabled={busy}
                onChange={(storyProfile) =>
                  setDraft((current) => ({ ...current, story_profile: storyProfile }))
                }
                storyProfile={draft.story_profile}
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  checked={draft.is_visible}
                  disabled={busy}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, is_visible: event.target.checked }))
                  }
                  type="checkbox"
                />
                <span>在剧情中允许点击查看</span>
              </label>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <button className="app-button app-button-primary" disabled={busy} type="submit">
                  {operation === "save" ? "保存中..." : "保存档案"}
                </button>
                {statusText ? (
                  <span className="text-sm text-[color:var(--muted)]">{statusText}</span>
                ) : null}
              </div>
            </form>
          </details>
        </div>
      </div>
    </article>
  );
}

function CharacterReadOnlyBlock({
  label,
  value,
  wide = false
}: {
  label: string;
  value?: string | null;
  wide?: boolean;
}) {
  return (
    <section className={wide ? "archive-card lg:col-span-2" : "archive-card"}>
      <div className="text-xs font-semibold text-[color:var(--muted)]">{label}</div>
      <p className="app-wrap-text mt-2 whitespace-pre-wrap text-sm leading-6">
        {value?.trim() || "暂无记录。"}
      </p>
    </section>
  );
}

function RuntimeStateBlock({ runtimeView }: { runtimeView: CharacterRuntimeView | null }) {
  const facts = runtimeView
    ? [
        runtimeView.location ? `位置：${runtimeView.location}` : "",
        runtimeView.status ? `状态：${runtimeView.status}` : "",
        runtimeView.relationship ? `关系：${runtimeView.relationship}` : "",
        runtimeView.note ? `补充：${runtimeView.note}` : ""
      ].filter(Boolean)
    : [];

  return (
    <section className="rounded-md border border-[color:var(--border)] p-3">
      <div className="text-xs font-semibold text-[color:var(--muted)]">当前状态</div>
      {facts.length > 0 ? (
        <ul className="app-wrap-text mt-2 grid gap-1 text-sm leading-6">
          {facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">暂无当前状态记录。</p>
      )}
    </section>
  );
}

function StoryProfileGrid({ storyProfile }: { storyProfile: CharacterStoryProfile }) {
  const normalized = normalizeStoryProfile(storyProfile);
  return (
    <div className="mt-3 grid gap-3 md:grid-cols-2">
      {storyProfileEntries(normalized).map(([key, value]) => (
        <section className="rounded-md border border-[color:var(--border)] p-3" key={key}>
          <div className="text-xs font-semibold text-[color:var(--muted)]">
            {storyProfileLabels[key]}
          </div>
          <p className="app-wrap-text mt-2 whitespace-pre-wrap text-sm leading-6">
            {value || "暂无记录。"}
          </p>
        </section>
      ))}
    </div>
  );
}

function StoryProfileEditor({
  disabled,
  onChange,
  storyProfile
}: {
  disabled: boolean;
  onChange: (storyProfile: CharacterStoryProfile) => void;
  storyProfile: CharacterStoryProfile;
}) {
  const normalized = normalizeStoryProfile(storyProfile);
  return (
    <fieldset className="grid gap-3 rounded-md border border-[color:var(--border)] p-3">
      <legend className="px-1 text-sm font-semibold">导演编剧字段</legend>
      {storyProfileEntries(normalized).map(([key, value]) => (
        <label className="grid gap-1 text-sm" key={key}>
          <span className="font-semibold">{storyProfileLabels[key]}</span>
          <textarea
            className="app-input min-h-16 resize-y leading-6"
            disabled={disabled}
            onChange={(event) =>
              onChange({
                ...normalized,
                [key]: event.target.value
              })
            }
            value={value}
          />
        </label>
      ))}
    </fieldset>
  );
}

function draftFromCharacter(character: CharacterRead): DraftState {
  return {
    name: character.name,
    aliases: character.aliases.join("\n"),
    role: character.role,
    identity: character.identity ?? "",
    description: character.description ?? "",
    appearance: character.appearance ?? "",
    is_visible: character.is_visible,
    story_profile: normalizeStoryProfile(character.story_profile)
  };
}

function characterMatchesFilters(character: CharacterRead, filters: Filters) {
  if (filters.role !== "all" && character.role !== filters.role) {
    return false;
  }
  if (filters.visibility !== "all" && character.visibility !== filters.visibility) {
    return false;
  }
  if (filters.source !== "all" && character.source !== filters.source) {
    return false;
  }
  const query = normalizeCharacterName(filters.query);
  if (!query) {
    return true;
  }
  const searchable = [
    character.name,
    ...character.aliases,
    character.identity ?? "",
    character.description ?? "",
    character.appearance ?? "",
    ...Object.values(normalizeStoryProfile(character.story_profile))
  ]
    .join("\n")
    .toLowerCase();
  return searchable.includes(query);
}

function parseAliases(value: string) {
  return value
    .split(/[\n,，、]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function storyProfileEntries(storyProfile: CharacterStoryProfile) {
  return Object.entries(storyProfile) as [keyof CharacterStoryProfile, string][];
}
