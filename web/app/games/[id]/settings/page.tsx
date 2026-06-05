"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { SettingsBoard } from "@/components/board/SettingsBoard";
import { SettingsAdvanced } from "@/components/settings/SettingsAdvanced";
import { ModuleMergePanel } from "@/components/workshop/ModuleMergePanel";
import { SaveAsModuleDialog } from "@/components/workshop/SaveAsModuleDialog";
import { getGame, getSettingVersions, suggestItem, updateGameConfig } from "@/lib/api";
import {
  appendItem,
  buildBoardModel,
  deleteBlock,
  writeBlockFields,
  type BoardBlock,
  type BoardField,
  type BoardModel
} from "@/lib/generatorBoard";
import { buildModulePayload, isExtractable, moduleTypeFromBlock } from "@/lib/moduleFragment";
import type { GameDetail, GameSettingVersionRead } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; versions: GameSettingVersionRead[] }
  | { status: "error"; message: string };

export default function GameSettingsPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [game, versions] = await Promise.all([getGame(params.id), getSettingVersions(params.id)]);
        if (!controller.signal.aborted) setState({ status: "ready", game, versions });
      } catch (error) {
        if (!controller.signal.aborted)
          setState({ status: "error", message: error instanceof Error ? error.message : "Unknown error" });
      }
    }
    load();
    return () => controller.abort();
  }, [params.id]);

  if (state.status === "loading")
    return (
      <AppShell>
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">正在读取设定...</section>
      </AppShell>
    );
  if (state.status === "error")
    return (
      <AppShell>
        <section className="app-alert">{state.message}</section>
      </AppShell>
    );

  return (
    <AppShell>
      <SettingsView
        game={state.game}
        versions={state.versions}
        onChanged={(game, versions) => setState({ status: "ready", game, versions })}
      />
    </AppShell>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function SettingsView({
  game,
  versions,
  onChanged
}: {
  game: GameDetail;
  versions: GameSettingVersionRead[];
  onChanged: (game: GameDetail, versions: GameSettingVersionRead[]) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [moduleBlock, setModuleBlock] = useState<BoardBlock | null>(null);
  const settings = useMemo(() => asRecord(game.config?.story_settings), [game.config?.story_settings]);
  const model: BoardModel = useMemo(() => buildBoardModel({ source: "settings", settings }), [settings]);

  async function persist(nextSettings: Record<string, unknown>) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateGameConfig(game.id, { story_settings_json: nextSettings });
      const freshVersions = await getSettingVersions(game.id);
      onChanged(updated, freshVersions);
    } catch (caught) {
      // 回合生成中后端返回 409；其余照常报错。
      const msg = caught instanceof Error ? caught.message : "保存失败。";
      setError(/运行中|生成|提取任务|editable|409/i.test(msg) ? "回合生成中，暂时不能修改设定，请稍后再试。" : msg);
    } finally {
      setSaving(false);
    }
  }

  function handleEditBlock(block: BoardBlock, fields: BoardField[]) {
    void persist(writeBlockFields(settings, block.address, fields));
  }
  function handleDeleteBlock(block: BoardBlock) {
    void persist(deleteBlock(settings, block.address));
  }

  async function handleRefresh() {
    const [fresh, freshVersions] = await Promise.all([getGame(game.id), getSettingVersions(game.id)]);
    onChanged(fresh, freshVersions);
  }

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader active="settings" eyebrow="设定" gameId={game.id} title={game.title} subtitle="剧本唯一主设定源" />
      <p className="app-status">
        这里是该剧本「唯一主设定源」。修改只影响后续回合，不改写已发生的剧情/状态；回合生成中不可改。
      </p>
      {error ? <p className="app-alert">{error}</p> : null}
      <SettingsBoard
        model={model}
        loading={saving}
        onEditBlock={handleEditBlock}
        onDeleteBlock={handleDeleteBlock}
        onSaveAsModule={(block) => { if (isExtractable(block)) setModuleBlock(block); }}
        onAddItem={(arrayKey, item) => { void persist(appendItem(settings, arrayKey, item)); }}
        onSuggestItem={(arrayKey, draft) => suggestItem(game.id, arrayKey, draft)}
      />
      <SettingsAdvanced
        key={game.config?.updated_at ?? ""}
        game={game}
        versions={versions}
        onRefresh={handleRefresh}
        disabled={saving}
      />
      <ModuleMergePanel
        targetSettings={settings}
        onApply={async (merged) => { await persist(merged); }}
      />
      {moduleBlock ? (
        <SaveAsModuleDialog
          defaultName={moduleBlock.title}
          moduleType={moduleTypeFromBlock(moduleBlock)}
          payload={buildModulePayload(settings, moduleBlock)}
          sourceGameId={game.id}
          onClose={() => setModuleBlock(null)}
          onSaved={() => setModuleBlock(null)}
        />
      ) : null}
    </div>
  );
}
