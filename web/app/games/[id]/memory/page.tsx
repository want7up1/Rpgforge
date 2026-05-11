"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChangeEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { JsonBlock } from "@/components/JsonBlock";
import {
  getContextDiagnostic,
  getGameMemory,
  getTurns,
  rebuildGameSummaries,
  reindexGameLore
} from "@/lib/api";
import type {
  ContextDiagnosticRead,
  GameMemoryRead,
  LoreDiagnosticRead,
  LoreEntryMemoryRead,
  SummaryRead,
  TurnRead
} from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | {
      status: "ready";
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
  const [busyAction, setBusyAction] = useState<"summaries" | "lore" | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const [memory, turns] = await Promise.all([getGameMemory(params.id), getTurns(params.id)]);
        const latestTurn = turns[turns.length - 1];
        const diagnostic = latestTurn
          ? await getContextDiagnostic(params.id, latestTurn.id)
          : null;
        if (!controller.signal.aborted) {
          setSelectedTurnId(latestTurn?.id ?? "");
          setState({ status: "ready", memory, turns, diagnostic });
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

  async function refreshMemory() {
    const [memory, turns] = await Promise.all([getGameMemory(params.id), getTurns(params.id)]);
    const turnId = selectedTurnId || turns[turns.length - 1]?.id || "";
    const diagnostic = turnId ? await getContextDiagnostic(params.id, turnId) : null;
    setState({ status: "ready", memory, turns, diagnostic });
    setSelectedTurnId(turnId);
  }

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

  async function handleReindexLore() {
    setBusyAction("lore");
    setActionError(null);
    setActionStatus("正在重建世界书向量...");
    try {
      const result = await reindexGameLore(params.id);
      await refreshMemory();
      setActionStatus(`世界书向量已重建，更新 ${result.updated}/${result.total} 条。`);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "重建世界书向量失败。");
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
          正在读取资料与记忆...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <MemoryView
          actionError={actionError}
          actionStatus={actionStatus}
          busyAction={busyAction}
          diagnostic={state.diagnostic}
          memory={state.memory}
          onRebuildSummaries={handleRebuildSummaries}
          onReindexLore={handleReindexLore}
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
  memory,
  onRebuildSummaries,
  onReindexLore,
  onTurnChange,
  selectedTurnId,
  turns
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | "lore" | null;
  diagnostic: ContextDiagnosticRead | null;
  memory: GameMemoryRead;
  onRebuildSummaries: () => void;
  onReindexLore: () => void;
  onTurnChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  selectedTurnId: string;
  turns: TurnRead[];
}) {
  const summaryBuckets = useMemo(() => bucketSummaries(memory.summaries), [memory.summaries]);
  const embeddedLoreCount = memory.lore_entries.filter((entry) => entry.embedding_configured).length;

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader
        active="memory"
        eyebrow="资料"
        gameId={memory.game.id}
        primaryAction={
          <Link
            className="app-button app-button-primary w-full sm:w-fit"
            href={`/games/${memory.game.id}/play`}
          >
            继续游戏
          </Link>
        }
        subtitle={
          <>
            当前回合 {memory.current_turn} · 历史 {memory.turn_count} 回 · 世界资料{" "}
            {memory.lore_entries.length} 条 · 摘要 {memory.summaries.length} 条
          </>
        }
        title={memory.game.title}
      />

      <section className="grid grid-cols-3 gap-2 sm:gap-3">
        <Metric label="回合" value={memory.current_turn} />
        <Metric label="世界资料" value={memory.lore_entries.length} />
        <Metric label="摘要" value={memory.summaries.length} />
      </section>

      <SummarySection buckets={summaryBuckets} />
      <LoreSection entries={memory.lore_entries} />

      <details className="app-card app-card-pad">
        <summary className="cursor-pointer text-lg font-semibold">高级维护与诊断</summary>
        <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <MaintenancePanel
            actionError={actionError}
            actionStatus={actionStatus}
            busyAction={busyAction}
            embeddedLoreCount={embeddedLoreCount}
            loreCount={memory.lore_entries.length}
            onRebuildSummaries={onRebuildSummaries}
            onReindexLore={onReindexLore}
          />
          <DiagnosticSection
            diagnostic={diagnostic}
            onTurnChange={onTurnChange}
            selectedTurnId={selectedTurnId}
            turns={turns}
          />
        </div>
      </details>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <article className="app-card p-3 sm:p-4">
      <p className="text-xs text-[color:var(--muted)] sm:text-sm">{label}</p>
      <p className="mt-1 break-words text-2xl font-semibold sm:mt-2 sm:text-3xl">{value}</p>
    </article>
  );
}

function MaintenancePanel({
  actionError,
  actionStatus,
  busyAction,
  embeddedLoreCount,
  loreCount,
  onRebuildSummaries,
  onReindexLore
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | "lore" | null;
  embeddedLoreCount: number;
  loreCount: number;
  onRebuildSummaries: () => void;
  onReindexLore: () => void;
}) {
  return (
    <section className="rounded border border-[color:var(--border)] p-4">
      <h2 className="text-lg font-semibold">维护</h2>
      <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
        摘要和向量会影响下一次剧情生成时注入的上下文。正常游戏时不需要频繁操作。
      </p>
      <p className="app-status mt-3">世界资料索引：{embeddedLoreCount}/{loreCount}</p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
        <button
          className="app-button bg-[color:var(--input)]"
          disabled={busyAction !== null}
          onClick={onRebuildSummaries}
          type="button"
        >
          {busyAction === "summaries" ? "重建中..." : "重建摘要"}
        </button>
        <button
          className="app-button app-button-primary"
          disabled={busyAction !== null}
          onClick={onReindexLore}
          type="button"
        >
          {busyAction === "lore" ? "重建中..." : "重建世界资料索引"}
        </button>
      </div>
      {actionStatus ? <p className="app-status mt-3">{actionStatus}</p> : null}
      {actionError ? <p className="app-alert mt-3">{actionError}</p> : null}
    </section>
  );
}

function SummarySection({ buckets }: { buckets: Record<string, SummaryRead[]> }) {
  return (
    <section className="app-card app-card-pad">
      <h2 className="text-lg font-semibold">上下文记忆</h2>
      <div className="mt-4 grid gap-4">
        <SummaryGroup label="长期记忆" summaries={buckets.long_term ?? []} />
        <SummaryGroup label="章节记忆" summaries={buckets.chapter ?? []} />
        <details className="rounded border border-[color:var(--border)]">
          <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
            回合摘要（{buckets.turn?.length ?? 0}）
          </summary>
          <div className="grid gap-3 border-t border-[color:var(--border)] p-3">
            <SummaryCards summaries={buckets.turn ?? []} />
          </div>
        </details>
      </div>
    </section>
  );
}

function SummaryGroup({ label, summaries }: { label: string; summaries: SummaryRead[] }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{label}</h3>
        <span className="text-xs text-[color:var(--muted)]">{summaries.length} 条</span>
      </div>
      <SummaryCards summaries={summaries} />
    </div>
  );
}

function SummaryCards({ summaries }: { summaries: SummaryRead[] }) {
  if (summaries.length === 0) {
    return (
      <p className="rounded border border-dashed border-[color:var(--border)] p-3 text-sm text-[color:var(--muted)]">
        暂无摘要。
      </p>
    );
  }
  return (
    <div className="grid gap-3">
      {summaries.map((summary) => (
        <article className="rounded border border-[color:var(--border)] p-3" key={summary.id}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-medium text-[color:var(--muted)]">
              {formatSummaryRange(summary)}
            </span>
            <span className="rounded bg-[#edf2eb] px-2 py-1 text-xs font-medium text-[color:var(--accent-strong)]">
              {summary.type}
            </span>
          </div>
          <p className="app-scroll-text mt-3 text-sm leading-6">
            {summary.content}
          </p>
          {Object.keys(summary.important_facts ?? {}).length > 0 ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-semibold text-[color:var(--muted)]">
                关键事实
              </summary>
              <div className="mt-2">
                <JsonBlock data={summary.important_facts} />
              </div>
            </details>
          ) : null}
        </article>
      ))}
    </div>
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
    <section className="rounded border border-[color:var(--border)] p-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
        <h2 className="text-lg font-semibold">上下文诊断</h2>
        <select
          className="min-h-11 rounded border border-[color:var(--border)] bg-[color:var(--input)] px-3 py-2 text-sm"
          onChange={onTurnChange}
          value={selectedTurnId}
        >
          <option value="">选择回合</option>
          {turns.map((turn) => (
            <option key={turn.id} value={turn.id}>
              第 {turn.turn_number} 回
            </option>
          ))}
        </select>
      </div>

      {!diagnostic ? (
        <p className="mt-4 rounded border border-dashed border-[color:var(--border)] p-3 text-sm text-[color:var(--muted)]">
          暂无可诊断回合。
        </p>
      ) : (
        <div className="mt-4 grid gap-4">
          <article className="rounded border border-[color:var(--border)] p-3">
            <h3 className="text-sm font-semibold">玩家行动</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
              {diagnostic.player_input}
            </p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded bg-[#edf2eb] px-2 py-1 text-[color:var(--accent-strong)]">
                模式：{diagnostic.selected_mode?.name ?? "未命中"}
              </span>
              <span className="rounded bg-[#edf2eb] px-2 py-1 text-[color:var(--accent-strong)]">
                近期回合：{diagnostic.recent_turn_numbers.join(", ") || "无"}
              </span>
            </div>
          </article>
          <LoreDiagnosticList label="常驻世界书" entries={diagnostic.always_on_lore} />
          <LoreDiagnosticList label="相关世界书" entries={diagnostic.related_lore} />
          <details className="rounded border border-[color:var(--border)]">
            <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
              注入摘要
            </summary>
            <div className="border-t border-[color:var(--border)] p-3">
              <JsonBlock data={diagnostic.memory_summaries} />
            </div>
          </details>
        </div>
      )}
    </section>
  );
}

function LoreDiagnosticList({
  entries,
  label
}: {
  entries: LoreDiagnosticRead[];
  label: string;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{label}</h3>
      {entries.length === 0 ? (
        <p className="mt-2 rounded border border-dashed border-[color:var(--border)] p-3 text-sm text-[color:var(--muted)]">
          无命中。
        </p>
      ) : (
        <div className="mt-2 grid gap-2">
          {entries.map((entry) => (
            <article className="rounded border border-[color:var(--border)] p-3" key={entry.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="font-semibold">{entry.title}</h4>
                <span className="text-xs text-[color:var(--muted)]">
                  {entry.score === null ? "常驻" : `score ${entry.score}`}
                </span>
              </div>
              <p className="mt-2 max-h-20 overflow-auto text-xs leading-5 text-[color:var(--muted)]">
                {entry.type || "unknown"} · {entry.priority || "medium"}
                {entry.matched_terms.length > 0
                  ? ` · 命中：${entry.matched_terms.join("、")}`
                  : ""}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function LoreSection({ entries }: { entries: LoreEntryMemoryRead[] }) {
  return (
    <section className="app-card app-card-pad">
      <h2 className="text-lg font-semibold">世界资料</h2>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {entries.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无世界资料。</p>
        ) : (
          entries.map((entry) => (
            <article
              className="app-long-card rounded border border-[color:var(--border)] p-4"
              key={entry.id}
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-semibold">{entry.title}</h3>
                  <p className="mt-1 text-xs text-[color:var(--muted)]">
                    {entry.type || "unknown"} · {entry.priority || "medium"} ·{" "}
                    {entry.always_on ? "常驻" : "触发"} ·{" "}
                    {entry.embedding_configured ? "已索引" : "未索引"}
                  </p>
                </div>
                <span className="app-pill">
                  {entry.visibility || "mixed"}
                </span>
              </div>
              <p className="mt-3 max-h-44 overflow-auto whitespace-pre-wrap text-sm leading-6">
                {entry.content}
              </p>
              <TagRow label="关键词" values={entry.keywords} />
              <TagRow label="触发词" values={entry.trigger_words} />
              {entry.usage_note ? (
                <p className="mt-3 text-xs leading-5 text-[color:var(--muted)]">
                  {entry.usage_note}
                </p>
              ) : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function TagRow({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-[color:var(--muted)]">{label}</span>
      {values.map((value) => (
        <span
          className="rounded border border-[color:var(--border)] px-2 py-1 text-xs"
          key={value}
        >
          {value}
        </span>
      ))}
    </div>
  );
}

function bucketSummaries(summaries: SummaryRead[]) {
  const buckets: Record<string, SummaryRead[]> = {};
  for (const summary of summaries) {
    buckets[summary.type] = [...(buckets[summary.type] ?? []), summary];
  }
  for (const type of Object.keys(buckets)) {
    buckets[type].sort((a, b) => (b.range_end_turn ?? 0) - (a.range_end_turn ?? 0));
  }
  return buckets;
}

function formatSummaryRange(summary: SummaryRead) {
  if (!summary.range_start_turn || !summary.range_end_turn) {
    return "暂无回合";
  }
  if (summary.range_start_turn === summary.range_end_turn) {
    return `第 ${summary.range_end_turn} 回`;
  }
  return `第 ${summary.range_start_turn}-${summary.range_end_turn} 回`;
}
