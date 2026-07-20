"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GameSubpageShell } from "@/components/GameMenu";
import { usePixelDialog } from "@/components/PixelDialog";
import { SettingsOverviewCard } from "@/components/settings/SettingsOverviewCard";
import {
  createGameProgressSave,
  deleteGame,
  deleteGameProgressSave,
  getGame,
  getGameProgressSaves,
  getGameScriptExport,
  loadGameProgressSave,
  restartGameProgress
} from "@/lib/api";
import { downloadBlob } from "@/lib/downloads";
import { getStateV2FromGame, type StateV2 } from "@/lib/stateV2";
import type { GameDetail, GameProgressSaveRead } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; saves: GameProgressSaveRead[] }
  | { status: "error"; message: string };

export default function GameCampPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function loadGame() {
      try {
        const [game, saves] = await Promise.all([
          getGame(params.id),
          getGameProgressSaves(params.id)
        ]);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game, saves });
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Unknown error"
          });
        }
      }
    }

    loadGame();

    return () => controller.abort();
  }, [params.id]);

  return (
    <AppShell variant="focus">
      {state.status === "loading" ? (
        <section className="px-panel px-panel-pad text-sm text-[color:var(--muted)]">
          <span className="px-caret" aria-hidden="true" /> 正在读取营地…
        </section>
      ) : state.status === "error" ? (
        <section className="px-alert">{state.message}</section>
      ) : (
        <CampView
          game={state.game}
          onProgressChanged={(game, saves) => setState({ status: "ready", game, saves })}
          saves={state.saves}
        />
      )}
    </AppShell>
  );
}

function CampView({
  game,
  saves,
  onProgressChanged
}: {
  game: GameDetail;
  saves: GameProgressSaveRead[];
  onProgressChanged: (game: GameDetail, saves: GameProgressSaveRead[]) => void;
}) {
  const router = useRouter();
  const dialog = usePixelDialog();
  const longTermSummary = latestSummary(game, "long_term");
  const chapterSummary = latestSummary(game, "chapter");
  const storySettings = asRecord(game.config?.story_settings);
  const stateV2 = getStateV2FromGame(game);
  const hasTurns = (game.state?.current_turn ?? 0) > 0;
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [exportingScript, setExportingScript] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  async function handleScriptExport() {
    setExportingScript(true);
    setExportStatus("正在生成剧本 Markdown...");
    setExportError(null);
    try {
      const { blob, filename } = await getGameScriptExport(game.id);
      downloadBlob(blob, filename);
      setExportStatus("剧本 Markdown 已开始下载。");
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "导出剧本失败。");
      setExportStatus(null);
    } finally {
      setExportingScript(false);
    }
  }

  async function handleDeleteGame() {
    const confirmedTitle = await dialog.prompt(
      `删除后无法恢复。请输入游戏标题确认删除：${game.title}`,
      { confirmLabel: "删除", danger: true }
    );
    if (confirmedTitle === null) {
      return;
    }
    if (confirmedTitle !== game.title) {
      setDeleteError("标题不一致，已取消删除。");
      return;
    }

    setDeleteError(null);
    setDeleting(true);
    try {
      await deleteGame(game.id);
      router.replace("/games");
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "删除游戏失败。");
      setDeleting(false);
    }
  }

  return (
    <GameSubpageShell
      active="camp"
      eyebrow="CAMP · 营地"
      gameId={game.id}
      meta={<span className="px-badge px-badge-bright">{game.status}</span>}
      primaryAction={
        <div className="grid w-full gap-2 sm:flex sm:w-fit sm:flex-wrap sm:justify-end">
          <button
            className="px-btn w-full sm:w-fit"
            disabled={exportingScript}
            onClick={handleScriptExport}
            type="button"
          >
            {exportingScript ? "导出中..." : "⇩ 导出剧本"}
          </button>
          <Link
            className="px-btn px-btn-primary w-full sm:w-fit"
            href={`/games/${game.id}/play`}
          >
            {hasTurns ? "▸ 继续冒险" : "▸ 开始冒险"}
          </Link>
        </div>
      }
      subtitle={
        <>
          {game.genre || "未分类"} · {game.description || "暂无简介"}
        </>
      }
      title={game.title}
    >
      {exportStatus ? <p className="px-status">{exportStatus}</p> : null}
      {exportError ? <p className="px-alert">{exportError}</p> : null}

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        <MetricCard label="回合" value={game.state?.current_turn ?? 0} />
        <MetricCard label="状态" value={stateV2.conditions.length} />
        <MetricCard label="剧本素材" value={asRecords(storySettings.story_material_library).length} />
        <MetricCard label="记忆摘要" value={game.summaries.length} />
      </section>

      <SettingsOverviewCard gameId={game.id} storySettings={storySettings} />

      <StatusSnapshot game={game} stateV2={stateV2} />

      <ProgressSaveSection game={game} onChanged={onProgressChanged} saves={saves} />

      <section className="px-panel px-panel-strong px-panel-pad">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="px-heading text-base">营火日志</h2>
            <span className="px-badge">{game.summaries.length} 条摘要</span>
          </div>
          <Link
            className="px-btn w-full sm:w-fit"
            href={`/games/${game.id}/memory`}
          >
            打开记忆 MEMO ▸
          </Link>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <SummaryPanel
            content={longTermSummary?.content}
            label="长期记忆"
            range={formatSummaryRange(longTermSummary)}
          />
          <SummaryPanel
            content={chapterSummary?.content}
            label="当前章节"
            range={formatSummaryRange(chapterSummary)}
          />
        </div>
      </section>

      <details className="px-fold border-[color:var(--danger-border)]">
        <summary className="text-[color:var(--danger-text)]">危险篝火 · 危险操作</summary>
        <div className="px-fold-body grid gap-3">
          <p className="text-sm leading-6 text-[color:var(--muted)]">
            删除会移除这局游戏的剧情、状态、角色、剧本设定、记忆摘要和已上传立绘。
          </p>
          {deleteError ? <div className="px-alert">{deleteError}</div> : null}
          <button
            className="px-btn px-btn-danger w-full sm:w-fit"
            disabled={deleting}
            onClick={handleDeleteGame}
            type="button"
          >
            {deleting ? "删除中..." : "✕ 删除游戏"}
          </button>
        </div>
      </details>
    </GameSubpageShell>
  );
}

function ProgressSaveSection({
  game,
  saves,
  onChanged
}: {
  game: GameDetail;
  saves: GameProgressSaveRead[];
  onChanged: (game: GameDetail, saves: GameProgressSaveRead[]) => void;
}) {
  const dialog = usePixelDialog();
  const [saveName, setSaveName] = useState(defaultSaveName(game));
  const [saveNote, setSaveNote] = useState("");
  const [operation, setOperation] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshWith(updatedGame: GameDetail) {
    const refreshedSaves = await getGameProgressSaves(game.id);
    onChanged(updatedGame, refreshedSaves);
  }

  async function handleCreateSave() {
    const name = saveName.trim();
    if (!name) {
      setError("存档名称不能为空。");
      return;
    }
    setOperation("create");
    setStatus("正在创建进度存档...");
    setError(null);
    try {
      await createGameProgressSave(game.id, {
        name,
        note: saveNote.trim() || null
      });
      const refreshedSaves = await getGameProgressSaves(game.id);
      onChanged(game, refreshedSaves);
      setSaveName(defaultSaveName(game));
      setSaveNote("");
      setStatus("进度存档已创建。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建存档失败。");
      setStatus(null);
    } finally {
      setOperation(null);
    }
  }

  async function handleLoadSave(progressSave: GameProgressSaveRead) {
    const confirmed = await dialog.confirm(
      `读取「${progressSave.name}」会覆盖当前进度，但不会修改任何游戏设定。确定读取？`,
      { confirmLabel: "读取" }
    );
    if (!confirmed) {
      return;
    }
    setOperation(`load-${progressSave.id}`);
    setStatus("正在读取进度存档...");
    setError(null);
    try {
      const updatedGame = await loadGameProgressSave(game.id, progressSave.id);
      await refreshWith(updatedGame);
      setStatus("进度已恢复，游戏设定未修改。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取存档失败。");
      setStatus(null);
    } finally {
      setOperation(null);
    }
  }

  async function handleDeleteSave(progressSave: GameProgressSaveRead) {
    const confirmed = await dialog.confirm(`删除进度存档「${progressSave.name}」？`, {
      confirmLabel: "删除",
      danger: true
    });
    if (!confirmed) {
      return;
    }
    setOperation(`delete-${progressSave.id}`);
    setStatus("正在删除进度存档...");
    setError(null);
    try {
      await deleteGameProgressSave(game.id, progressSave.id);
      const refreshedSaves = await getGameProgressSaves(game.id);
      onChanged(game, refreshedSaves);
      setStatus("进度存档已删除。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除存档失败。");
      setStatus(null);
    } finally {
      setOperation(null);
    }
  }

  async function handleRestart() {
    const confirmedTitle = await dialog.prompt(
      `重新开始会清空当前回合、状态和摘要，但不会修改设定或删除存档。请输入游戏标题确认：${game.title}`,
      { confirmLabel: "重新开始", danger: true }
    );
    if (confirmedTitle === null) {
      return;
    }
    if (confirmedTitle !== game.title) {
      setError("标题不一致，已取消重新开始。");
      return;
    }
    setOperation("restart");
    setStatus("正在重新开始当前剧本...");
    setError(null);
    try {
      const updatedGame = await restartGameProgress(game.id);
      await refreshWith(updatedGame);
      setSaveName(defaultSaveName(updatedGame));
      setStatus("已重新开始，设定和存档保持不变。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重新开始失败。");
      setStatus(null);
    } finally {
      setOperation(null);
    }
  }

  return (
    <section className="px-panel px-panel-strong px-panel-pad">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="px-heading text-base">存档水晶</h2>
            <span className="px-badge">{saves.length} 个存档</span>
          </div>
          <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
            只保存回合、状态、摘要和状态变更；不会保存或覆盖剧本设定。
          </p>
          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-sm">
              <span className="px-label">存档名称</span>
              <input
                className="px-input"
                disabled={operation !== null}
                onChange={(event) => setSaveName(event.target.value)}
                value={saveName}
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="px-label">备注</span>
              <textarea
                className="px-input min-h-24 resize-y leading-6"
                disabled={operation !== null}
                onChange={(event) => setSaveNote(event.target.value)}
                placeholder="可选"
                value={saveNote}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                className="px-btn px-btn-primary"
                disabled={operation !== null || !saveName.trim()}
                onClick={handleCreateSave}
                type="button"
              >
                {operation === "create" ? "创建中..." : "◈ 创建进度存档"}
              </button>
              <button
                className="px-btn px-btn-amber"
                disabled={operation !== null}
                onClick={handleRestart}
                type="button"
              >
                {operation === "restart" ? "重开中..." : "↺ 重新开始当前剧本"}
              </button>
            </div>
            {status ? <p className="px-status">{status}</p> : null}
            {error ? <p className="px-alert">{error}</p> : null}
          </div>
        </div>
        <div className="grid content-start gap-3">
          {saves.length === 0 ? (
            <p className="px-empty">暂无进度存档。</p>
          ) : (
            saves.map((progressSave, index) => (
              <article className="save-slot" key={progressSave.id}>
                <span className="save-slot-index">SAVE {index + 1}</span>
                <div className="flex flex-col gap-2 pr-12 sm:flex-row sm:items-start sm:justify-between sm:pr-0">
                  <div className="min-w-0">
                    <h3 className="font-bold">{progressSave.name}</h3>
                    <p className="mt-1 text-xs text-[color:var(--muted)]">
                      第 {progressSave.state_current_turn} 回合 · 历史 {progressSave.turn_count} 回 · 摘要{" "}
                      {progressSave.summary_count} 条 · {formatDateTime(progressSave.updated_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="px-btn"
                      disabled={operation !== null}
                      onClick={() => handleLoadSave(progressSave)}
                      type="button"
                    >
                      {operation === `load-${progressSave.id}` ? "读取中..." : "读取"}
                    </button>
                    <button
                      className="px-btn px-btn-danger"
                      disabled={operation !== null}
                      onClick={() => handleDeleteSave(progressSave)}
                      type="button"
                    >
                      {operation === `delete-${progressSave.id}` ? "删除中..." : "删除"}
                    </button>
                  </div>
                </div>
                {progressSave.note ? (
                  <p className="px-wrap whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
                    {progressSave.note}
                  </p>
                ) : null}
              </article>
            ))
          )}
        </div>
      </div>
    </section>
  );
}

function StatusSnapshot({ game, stateV2 }: { game: GameDetail; stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;
  const scene = stateV2.active_scene;
  const progress = stateV2.story_progress;
  // 结局标记：失败结局与通关都在此提示（与 play 页结局视图呼应）。
  const endingLabel = progress.defeat
    ? "失败结局"
    : progress.campaign_complete
      ? "已通关"
      : "";

  return (
    <section className="px-panel px-panel-strong px-panel-pad">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="px-heading text-base">当前局面</h2>
            {endingLabel ? <span className="px-badge px-badge-amber">{endingLabel}</span> : null}
          </div>
          <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
            {protagonist.name || "主角"}
            {protagonist.identity ? ` · ${protagonist.identity}` : ""}
          </p>
          <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
            {scene.location || "未知地点"} · {scene.time || "未知时间"} ·{" "}
            {stateV2.conditions.length > 0 ? `${stateV2.conditions.length} 个持续状态` : "状态稳定"}
          </p>
        </div>
        <Link className="px-btn w-full sm:w-fit" href={`/games/${game.id}/status`}>
          查看状态 STATUS ▸
        </Link>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <SnapshotMetric label="状态" value={stateV2.conditions.length} />
        <SnapshotMetric label="关系" value={stateV2.relationship_tracks.length} />
        <SnapshotMetric label="任务" value={stateV2.quest_log.active.length} />
        <SnapshotMetric label="线索" value={stateV2.open_threads.active.length} />
      </div>
    </section>
  );
}

function SnapshotMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="px-metric">
      <p className="px-metric-label">{label}</p>
      <p className="mt-1 text-lg font-black text-[color:var(--phosphor)]">{value}</p>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <article className="px-metric">
      <h2 className="px-metric-label">{label}</h2>
      <p className="px-metric-value">{value}</p>
    </article>
  );
}

function SummaryPanel({
  label,
  range,
  content
}: {
  label: string;
  range: string;
  content?: string;
}) {
  return (
    <article className="px-card px-card-green">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="font-bold">{label}</h3>
        <span className="text-xs text-[color:var(--muted)]">{range}</span>
      </div>
      <p className="px-wrap mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
        {content || "暂无摘要。进行一回合后，系统会自动写入压缩记忆。"}
      </p>
    </article>
  );
}

function latestSummary(game: GameDetail, type: string) {
  return [...game.summaries]
    .filter((summary) => summary.type === type)
    .sort((a, b) => (b.range_end_turn ?? 0) - (a.range_end_turn ?? 0))[0];
}

function formatSummaryRange(summary: ReturnType<typeof latestSummary>) {
  if (!summary?.range_start_turn || !summary.range_end_turn) {
    return "暂无回合";
  }
  if (summary.range_start_turn === summary.range_end_turn) {
    return `第 ${summary.range_end_turn} 回`;
  }
  return `第 ${summary.range_start_turn}-${summary.range_end_turn} 回`;
}

function defaultSaveName(game: GameDetail) {
  return `第 ${game.state?.current_turn ?? 0} 回合 · ${formatDateTime(new Date().toISOString())}`;
}

function formatDateTime(value: string) {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    : [];
}
