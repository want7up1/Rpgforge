"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChangeEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { JsonBlock } from "@/components/JsonBlock";
import {
  getContextDiagnostic,
  getGame,
  getGameMemory,
  getGameScriptExport,
  getTurns,
  rebuildGameSummaries
} from "@/lib/api";
import { downloadBlob } from "@/lib/downloads";
import type {
  ContextDiagnosticRead,
  GameDetail,
  GameMemoryRead,
  SummaryRead,
  TurnRead
} from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | {
      status: "ready";
      game: GameDetail;
      memory: GameMemoryRead;
      turns: TurnRead[];
      diagnostic: ContextDiagnosticRead | null;
    }
  | { status: "error"; message: string };

export default function GameMemoryPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedTurnId, setSelectedTurnId] = useState<string>("");
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"summaries" | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const [memory, turns, game] = await Promise.all([
          getGameMemory(params.id),
          getTurns(params.id),
          getGame(params.id)
        ]);
        const latestTurn = turns[turns.length - 1];
        const diagnostic = latestTurn
          ? await getContextDiagnostic(params.id, latestTurn.id)
          : null;
        if (!controller.signal.aborted) {
          setSelectedTurnId(latestTurn?.id ?? "");
          setState({ status: "ready", game, memory, turns, diagnostic });
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

  async function handleRebuildSummaries() {
    setBusyAction("summaries");
    setActionError(null);
    setActionStatus("正在重建上下文摘要...");
    try {
      const result = await rebuildGameSummaries(params.id);
      setState((current) =>
        current.status === "ready"
          ? {
              ...current,
              memory: { ...current.memory, summaries: result.summaries }
            }
          : current
      );
      setActionStatus(`上下文摘要已重建，共 ${result.total} 条。`);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "重建摘要失败。");
      setActionStatus(null);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleTurnChange(event: ChangeEvent<HTMLSelectElement>) {
    const turnId = event.target.value;
    setSelectedTurnId(turnId);
    if (!turnId) {
      setState((current) =>
        current.status === "ready" ? { ...current, diagnostic: null } : current
      );
      return;
    }
    try {
      const diagnostic = await getContextDiagnostic(params.id, turnId);
      setState((current) =>
        current.status === "ready" ? { ...current, diagnostic } : current
      );
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "读取上下文诊断失败。");
    }
  }

  return (
    <AppShell>
      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取剧本资料...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <MemoryView
          actionError={actionError}
          actionStatus={actionStatus}
          busyAction={busyAction}
          diagnostic={state.diagnostic}
          game={state.game}
          memory={state.memory}
          onRebuildSummaries={handleRebuildSummaries}
          onTurnChange={handleTurnChange}
          selectedTurnId={selectedTurnId}
          turns={state.turns}
        />
      )}
    </AppShell>
  );
}

function MemoryView({
  actionError,
  actionStatus,
  busyAction,
  diagnostic,
  game,
  memory,
  onRebuildSummaries,
  onTurnChange,
  selectedTurnId,
  turns
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | null;
  diagnostic: ContextDiagnosticRead | null;
  game: GameDetail;
  memory: GameMemoryRead;
  onRebuildSummaries: () => void;
  onTurnChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  selectedTurnId: string;
  turns: TurnRead[];
}) {
  const [exportingScript, setExportingScript] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const storySettings = storySettingsFromGame(game);
  const summaryBuckets = useMemo(() => bucketSummaries(memory.summaries), [memory.summaries]);
  const materialCount = recordArray(storySettings.story_material_library).length;

  async function handleScriptExport() {
    setExportingScript(true);
    setExportStatus("正在生成剧本 Markdown...");
    setExportError(null);
    try {
      const { blob, filename } = await getGameScriptExport(memory.game.id);
      downloadBlob(blob, filename);
      setExportStatus("剧本 Markdown 已开始下载。");
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "导出剧本失败。");
      setExportStatus(null);
    } finally {
      setExportingScript(false);
    }
  }

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader
        active="memory"
        eyebrow="资料"
        gameId={memory.game.id}
        primaryAction={
          <div className="grid w-full gap-2 sm:flex sm:w-fit sm:flex-wrap sm:justify-end">
            <button
              className="app-button w-full sm:w-fit"
              disabled={exportingScript}
              onClick={handleScriptExport}
              type="button"
            >
              {exportingScript ? "导出中..." : "导出剧本"}
            </button>
            <Link
              className="app-button app-button-primary w-full sm:w-fit"
              href={`/games/${memory.game.id}/play`}
            >
              继续冒险
            </Link>
          </div>
        }
        subtitle={
          <>
            当前回合 {memory.current_turn} · 历史 {memory.turn_count} 回 · 剧本素材{" "}
            {materialCount} 条 · 摘要 {memory.summaries.length} 条
          </>
        }
        title={memory.game.title}
      />
      {exportStatus ? <p className="app-status">{exportStatus}</p> : null}
      {exportError ? <p className="app-alert">{exportError}</p> : null}

      <section className="grid grid-cols-3 gap-2 sm:gap-3">
        <Metric label="回合" value={memory.current_turn} />
        <Metric label="剧本素材" value={materialCount} />
        <Metric label="摘要" value={memory.summaries.length} />
      </section>

      <details className="surface-panel">
        <summary className="cursor-pointer surface-title">维护与运行诊断</summary>
        <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <MaintenancePanel
            actionError={actionError}
            actionStatus={actionStatus}
            busyAction={busyAction}
            onRebuildSummaries={onRebuildSummaries}
          />
          <DiagnosticSection
            diagnostic={diagnostic}
            onTurnChange={onTurnChange}
            selectedTurnId={selectedTurnId}
            turns={turns}
          />
        </div>
      </details>

      <SummarySection buckets={summaryBuckets} />
    </div>
  );
}

function MaintenancePanel({
  actionError,
  actionStatus,
  busyAction,
  onRebuildSummaries
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | null;
  onRebuildSummaries: () => void;
}) {
  return (
    <section className="grid gap-3">
      <SectionHeader
        title="维护"
        subtitle="这里处理上下文摘要等运行辅助数据，不会修改 story_settings。"
      />
      <button
        className="app-button w-fit"
        disabled={busyAction === "summaries"}
        onClick={onRebuildSummaries}
        type="button"
      >
        {busyAction === "summaries" ? "重建中..." : "重建上下文摘要"}
      </button>
      {actionStatus ? <p className="app-status">{actionStatus}</p> : null}
      {actionError ? <p className="app-alert">{actionError}</p> : null}
    </section>
  );
}

function DiagnosticSection({
  diagnostic,
  onTurnChange,
  selectedTurnId,
  turns
}: {
  diagnostic: ContextDiagnosticRead | null;
  onTurnChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  selectedTurnId: string;
  turns: TurnRead[];
}) {
  return (
    <section className="grid gap-4">
      <SectionHeader
        title="运行诊断"
        subtitle="查看某一回合实际注入 GM 的 story_settings 派生视图。"
      />
      <label className="grid gap-1 text-sm font-medium">
        <SettingLabel
          help="选择一个历史回合后，可以查看当时 GM 收到的当前幕、行动风格、召回素材和摘要。"
          label="诊断回合"
        />
        <select className="app-input" onChange={onTurnChange} value={selectedTurnId}>
          <option value="">选择回合</option>
          {turns.map((turn) => (
            <option key={turn.id} value={turn.id}>
              #{turn.turn_number} · {turn.player_input.slice(0, 36)}
            </option>
          ))}
        </select>
      </label>
      {diagnostic ? (
        <div className="grid gap-3">
          <InfoBlock
            help="本回合根据玩家输入匹配到的行动风格规则，会影响判定方式和叙事侧重点。"
            title="选中的行动风格"
            value={diagnostic.selected_action_style ?? {}}
          />
          <InfoBlock
            help="GM 实际读取的当前剧本运行视图，包含当前幕、未完成锚点、下一幕、主线轨迹、人物、规则和生成参数。"
            title="runtime_story"
            value={diagnostic.runtime_story}
          />
          <InfoBlock
            help="根据玩家输入、当前位置、最近回合和关键词召回的剧本素材。"
            title="相关剧本素材"
            value={diagnostic.related_story_materials}
          />
          <InfoBlock
            help="进入上下文的摘要片段，用来避免越玩上下文越长。"
            title="记忆摘要"
            value={diagnostic.memory_summaries}
          />
        </div>
      ) : (
        <p className="text-sm text-[color:var(--muted)]">暂无可诊断回合。</p>
      )}
    </section>
  );
}

function SummarySection({ buckets }: { buckets: Record<string, SummaryRead[]> }) {
  return (
    <section className="surface-panel">
      <SectionHeader
        title="记忆摘要"
        subtitle="摘要是运行缓存，不属于剧本设定源；它用于压缩上下文和降低 token 消耗。"
      />
      <div className="mt-4 grid gap-3">
        {Object.entries(buckets).length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无摘要。</p>
        ) : (
          Object.entries(buckets).map(([type, summaries]) => (
            <details className="rounded border border-[color:var(--border)] p-3" key={type}>
              <summary className="cursor-pointer text-sm font-semibold">
                {type} · {summaries.length} 条
              </summary>
              <div className="mt-3 grid gap-2">
                {summaries.map((summary) => (
                  <article
                    className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3 text-sm"
                    key={summary.id}
                  >
                    <p className="whitespace-pre-wrap text-[color:var(--foreground)]">
                      {summary.content}
                    </p>
                    {Object.keys(summary.important_facts).length > 0 ? (
                      <div className="mt-2 max-h-64 overflow-auto rounded border border-[color:var(--border)]">
                        <JsonBlock data={summary.important_facts} />
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            </details>
          ))
        )}
      </div>
    </section>
  );
}

function InfoBlock({
  help,
  title,
  value
}: {
  help: string;
  title: string;
  value: unknown;
}) {
  return (
    <article className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <HelpMark text={help} />
      </div>
      <div className="mt-2 max-h-96 overflow-auto rounded border border-[color:var(--border)]">
        <JsonBlock data={value} />
      </div>
    </article>
  );
}

function SectionHeader({
  subtitle,
  title
}: {
  subtitle?: ReactNode;
  title: ReactNode;
}) {
  return (
    <header>
      <h2 className="surface-title">{title}</h2>
      {subtitle ? <p className="mt-1 text-sm text-[color:var(--muted)]">{subtitle}</p> : null}
    </header>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="app-card app-card-pad">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function SettingLabel({ help, label }: { help: string; label: string }) {
  return (
    <span className="flex items-center gap-2">
      <span>{label}</span>
      <HelpMark text={help} />
    </span>
  );
}

function HelpMark({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        aria-label={text}
        className="flex h-5 w-5 items-center justify-center rounded-full border border-[color:var(--border)] text-xs font-semibold text-[color:var(--muted)] outline-none transition focus:border-[color:var(--accent)] focus:text-[color:var(--accent)] group-hover:border-[color:var(--accent)] group-hover:text-[color:var(--accent)]"
        type="button"
      >
        !
      </button>
      <span className="pointer-events-none absolute left-1/2 top-7 z-20 hidden w-72 -translate-x-1/2 rounded border border-[color:var(--border)] bg-[color:var(--panel)] p-3 text-left text-xs font-normal leading-5 text-[color:var(--foreground)] shadow-xl group-focus-within:block group-hover:block">
        {text}
      </span>
    </span>
  );
}

function bucketSummaries(summaries: SummaryRead[]): Record<string, SummaryRead[]> {
  return summaries.reduce<Record<string, SummaryRead[]>>((accumulator, summary) => {
    const key = summary.type || "summary";
    accumulator[key] = [...(accumulator[key] ?? []), summary];
    return accumulator;
  }, {});
}

function storySettingsFromGame(game: GameDetail): Record<string, unknown> {
  return asRecord(game.config?.story_settings);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => {
        return !!item && typeof item === "object" && !Array.isArray(item);
      })
    : [];
}
