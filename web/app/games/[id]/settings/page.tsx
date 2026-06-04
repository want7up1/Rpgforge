"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { SettingsBoard } from "@/components/board/SettingsBoard";
import { SettingsAdvanced } from "@/components/settings/SettingsAdvanced";
import { getGame, getSettingVersions, updateGameConfig } from "@/lib/api";
import {
  buildBoardModel,
  deleteBlock,
  writeBlockFields,
  type BoardBlock,
  type BoardField,
  type BoardModel
} from "@/lib/generatorBoard";
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
      />
      <SettingsAdvanced game={game} versions={versions} onRefresh={handleRefresh} />
    </div>
  );
}
