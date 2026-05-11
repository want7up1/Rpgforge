"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { JsonBlock } from "@/components/JsonBlock";
import { deleteGame, getGame } from "@/lib/api";
import { getStateV2FromGame, ratioPercent, type StateV2 } from "@/lib/stateV2";
import type { GameDetail } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail }
  | { status: "error"; message: string };

export default function GameDetailPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function loadGame() {
      try {
        const game = await getGame(params.id);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game });
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
    <AppShell>
      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取游戏...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <GameDetailView game={state.game} />
      )}
    </AppShell>
  );
}

function GameDetailView({ game }: { game: GameDetail }) {
  const router = useRouter();
  const longTermSummary = latestSummary(game, "long_term");
  const chapterSummary = latestSummary(game, "chapter");
  const featuredLore = game.lore_entries.slice(0, 6);
  const stateV2 = getStateV2FromGame(game);
  const hasTurns = (game.state?.current_turn ?? 0) > 0;
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDeleteGame() {
    const confirmedTitle = window.prompt(
      `删除后无法恢复。请输入游戏标题确认删除：${game.title}`
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
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader
        active="overview"
        backFallbackHref="/games"
        eyebrow="游戏概览"
        gameId={game.id}
        meta={<span className="app-pill">{game.status}</span>}
        primaryAction={
          <Link className="app-button app-button-primary w-full sm:w-fit" href={`/games/${game.id}/play`}>
            {hasTurns ? "继续游戏" : "开始游戏"}
          </Link>
        }
        subtitle={
          <>
            {game.genre || "未分类"} · {game.description || "暂无简介"}
          </>
        }
        title={game.title}
      />

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-4">
        <MetricCard label="等级" value={stateV2.protagonist_sheet.level} />
        <MetricCard label="回合" value={game.state?.current_turn ?? 0} />
        <MetricCard label="世界资料" value={game.lore_entries.length} />
        <MetricCard label="记忆摘要" value={game.summaries.length} />
      </section>

      <StatusSnapshot game={game} stateV2={stateV2} />

      <section className="app-card app-card-pad">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">记忆概览</h2>
            <span className="app-pill">{game.summaries.length} 条摘要</span>
          </div>
          <Link
            className="app-button w-full sm:w-fit"
            href={`/games/${game.id}/memory`}
          >
            管理资料
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

      <section className="app-card app-card-pad">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <h2 className="text-lg font-semibold">世界资料</h2>
            <p className="mt-1 text-sm text-[color:var(--muted)]">
              展示前 {featuredLore.length} 条，完整条目可在资料页查看。
            </p>
          </div>
          <Link className="app-button" href={`/games/${game.id}/memory`}>
            查看全部
          </Link>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {featuredLore.length === 0 ? (
            <p className="text-sm text-[color:var(--muted)]">暂无世界资料。</p>
          ) : (
            featuredLore.map((entry) => (
              <article
                className="app-long-card rounded border border-[color:var(--border)] p-4"
                key={entry.id}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <h3 className="font-semibold">{entry.title}</h3>
                  <span className="app-pill">
                    {entry.type || "unknown"} · {entry.priority || "medium"}
                  </span>
                </div>
                <p className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
                  {entry.content}
                </p>
              </article>
            ))
          )}
        </div>
      </section>

      <details className="app-card app-card-pad">
        <summary className="cursor-pointer text-lg font-semibold">高级诊断</summary>
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <DiagnosticsPanel title="世界观" data={game.config?.worldview ?? {}} />
          <section className="rounded border border-[color:var(--border)] p-4">
            <h3 className="font-semibold">模式注入</h3>
            {game.modes.length === 0 ? (
              <p className="mt-3 text-sm text-[color:var(--muted)]">暂无模式。</p>
            ) : (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {game.modes.map((mode) => (
                  <article className="rounded bg-[color:var(--soft-panel)] p-3" key={mode.id}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h4 className="font-semibold">{mode.name}</h4>
                      <span className="app-pill">{mode.enabled ? "启用" : "停用"}</span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-[color:var(--muted)]">
                      {mode.triggers.join("、") || "无触发词"}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </details>

      <details className="app-card app-card-pad border-[color:var(--danger-border)]">
        <summary className="cursor-pointer text-lg font-semibold text-[color:var(--danger-text)]">
          危险操作
        </summary>
        <div className="mt-4 grid gap-3">
          <p className="text-sm leading-6 text-[color:var(--muted)]">
            删除会移除这局游戏的剧情、状态、角色、世界资料、记忆摘要和已上传立绘。
          </p>
          {deleteError ? <div className="app-alert">{deleteError}</div> : null}
          <button
            className="app-button w-full border-[color:var(--danger-border)] text-[color:var(--danger-text)] sm:w-fit"
            disabled={deleting}
            onClick={handleDeleteGame}
            type="button"
          >
            {deleting ? "删除中..." : "删除游戏"}
          </button>
        </div>
      </details>
    </div>
  );
}

function StatusSnapshot({ game, stateV2 }: { game: GameDetail; stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;
  const scene = stateV2.active_scene;
  const xpPercent = ratioPercent(protagonist.xp, protagonist.next_level_xp);

  return (
    <section className="app-card app-card-pad">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">状态概览</h2>
            <span className="app-pill">Lv.{protagonist.level}</span>
          </div>
          <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
            {scene.location || "未知地点"} · {scene.time || "未知时间"} ·{" "}
            {stateV2.conditions.length > 0 ? `${stateV2.conditions.length} 个持续状态` : "状态稳定"}
          </p>
        </div>
        <Link className="app-button w-full sm:w-fit" href={`/games/${game.id}/status`}>
          查看角色状态
        </Link>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">经验进度</span>
            <span className="text-[color:var(--muted)]">
              {protagonist.xp}/{protagonist.next_level_xp}
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-[color:var(--soft-panel)]">
            <div
              className="h-full rounded-full bg-[color:var(--accent)]"
              style={{ width: `${xpPercent}%` }}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <SnapshotMetric label="技能" value={stateV2.skills.length} />
          <SnapshotMetric label="能力" value={stateV2.abilities.length} />
          <SnapshotMetric label="关系" value={stateV2.relationship_tracks.length} />
          <SnapshotMetric label="任务" value={stateV2.quest_log.active.length} />
        </div>
      </div>
    </section>
  );
}

function SnapshotMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <article className="app-card p-3 sm:p-5">
      <h2 className="text-xs font-medium text-[color:var(--muted)] sm:text-base">{label}</h2>
      <p className="mt-1 text-2xl font-semibold sm:text-3xl">{value}</p>
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
    <article className="rounded border border-[color:var(--border)] p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="font-semibold">{label}</h3>
        <span className="text-xs text-[color:var(--muted)]">{range}</span>
      </div>
      <p className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
        {content || "暂无摘要。进行一回合后，系统会自动写入压缩记忆。"}
      </p>
    </article>
  );
}

function DiagnosticsPanel({ title, data }: { title: string; data: unknown }) {
  return (
    <section className="rounded border border-[color:var(--border)] p-4">
      <h3 className="mb-3 font-semibold">{title}</h3>
      <JsonBlock data={data} />
    </section>
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
