"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { CharacterModal } from "@/components/CharacterModal";
import { GamePageHeader } from "@/components/GamePageHeader";
import { StoryMarkdown } from "@/components/StoryMarkdown";
import {
  createTurnJob,
  createTurnJobEventSource,
  getCharacters,
  getGame,
  getTurnJob,
  getTurns,
  parseTurnJobStreamEvent
} from "@/lib/api";
import { getStateV2FromGame, ratioPercent, type StateV2 } from "@/lib/stateV2";
import type {
  ActionOption,
  CharacterRead,
  GameDetail,
  TurnJobRead,
  TurnJobStreamEvent,
  TurnRead
} from "@/lib/types";

const turnPollIntervalMs = 1500;
const turnMaxPolls = 560;
const turnStreamConnectTimeoutMs = 6000;
const turnStreamErrorFallbackMs = 4000;

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; turns: TurnRead[]; characters: CharacterRead[] }
  | { status: "error"; message: string };

export default function PlayPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [turnProgress, setTurnProgress] = useState<string | null>(null);
  const [turnProcess, setTurnProcess] = useState<TurnJobRead | null>(null);
  const [freeActionOpen, setFreeActionOpen] = useState(false);
  const [selectedCharacter, setSelectedCharacter] = useState<CharacterRead | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const [game, turns, characters] = await Promise.all([
          getGame(params.id),
          getTurns(params.id),
          getCharacters(params.id)
        ]);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game, turns, characters });
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

  const latestTurn = useMemo(() => {
    if (state.status !== "ready" || state.turns.length === 0) {
      return null;
    }
    return state.turns[state.turns.length - 1];
  }, [state]);

  const stateV2 = useMemo(
    () => (state.status === "ready" ? getStateV2FromGame(state.game) : null),
    [state]
  );

  async function submitTurn(payload: Parameters<typeof createTurnJob>[1]) {
    if (state.status !== "ready" || pending) {
      return;
    }

    setError(null);
    setTurnProgress("已创建回合任务，等待 DeepSeek Pro 开始书写剧情...");
    setTurnProcess(null);
    setPending(true);
    try {
      const job = await createTurnJob(state.game.id, payload);
      setTurnProcess(createInitialTurnProcess(state.game.id, job.id, job.status));
      const completedJob = await waitForTurnJobWithStream(
        state.game.id,
        job.id,
        setTurnProgress,
        setTurnProcess
      );
      const turn = completedJob.turn;
      if (!turn) {
        throw new Error("回合任务已完成，但没有返回回合内容。");
      }
      let refreshedGame = state.game;
      try {
        refreshedGame = await getGame(state.game.id);
      } catch {
        // The new turn is still usable even if the status refresh misses once.
      }
      setState((current) =>
        current.status === "ready"
          ? { ...current, game: refreshedGame, turns: [...current.turns, turn] }
          : current
      );
      setInput("");
      setFreeActionOpen(false);
      setTurnProgress("剧情生成完成，状态变更正在后台写入。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交回合失败。");
      setTurnProgress("回合生成失败，已保留收到的过程信息。");
    } finally {
      setPending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }
    submitTurn({ player_input: trimmed });
  }

  return (
    <AppShell variant="focus">
      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取游戏...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <>
          <div className="mx-auto grid w-full max-w-3xl gap-3 pb-36 sm:gap-4 sm:pb-32">
            <section className="flex min-w-0 flex-col gap-3 sm:gap-4">
              <GamePageHeader
                active="play"
                eyebrow="剧情"
                gameId={params.id}
                subtitle={`当前回合 ${latestTurn?.turn_number ?? 0}`}
                title={state.game.title}
              />

              {error ? (
                <div className="app-alert">{error}</div>
              ) : null}

              {stateV2 ? <PlayStateStrip gameId={params.id} stateV2={stateV2} /> : null}

              <StoryPanel
                latestTurn={latestTurn}
                characters={state.characters}
                onCharacterClick={setSelectedCharacter}
                pending={pending}
                progress={turnProgress}
                process={turnProcess}
              />
            </section>
          </div>
          <CharacterModal
            character={selectedCharacter}
            onClose={() => setSelectedCharacter(null)}
          />

          <FloatingActionBar
            disabled={pending}
            input={input}
            onInputChange={setInput}
            onOpenChange={setFreeActionOpen}
            onSelect={(option) => submitTurn({ selected_option: option })}
            onSubmit={handleSubmit}
            open={freeActionOpen}
            options={latestTurn?.action_options_json ?? []}
            pending={pending}
          />
        </>
      )}
    </AppShell>
  );
}

function PlayStateStrip({ gameId, stateV2 }: { gameId: string; stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;
  const scene = stateV2.active_scene;
  const xpPercent = ratioPercent(protagonist.xp, protagonist.next_level_xp);
  const conditionLabel =
    stateV2.conditions.length > 0 ? `${stateV2.conditions.length} 个状态` : "状态稳定";

  return (
    <section className="rounded border border-[color:var(--border)] bg-[color:var(--panel)] p-3">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold">Lv.{protagonist.level}</span>
            <span className="text-[color:var(--muted)]">
              {scene.location || "未知地点"} · {conditionLabel}
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[color:var(--soft-panel)]">
            <div
              className="h-full rounded-full bg-[color:var(--accent)]"
              style={{ width: `${xpPercent}%` }}
            />
          </div>
        </div>
        <Link className="app-button w-full sm:w-fit" href={`/games/${gameId}/status`}>
          查看状态
        </Link>
      </div>
    </section>
  );
}

function FloatingActionBar({
  disabled,
  input,
  onInputChange,
  onOpenChange,
  onSelect,
  onSubmit,
  open,
  options,
  pending
}: {
  disabled: boolean;
  input: string;
  onInputChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  onSelect: (option: ActionOption) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  open: boolean;
  options: ActionOption[];
  pending: boolean;
}) {
  const hasOptions = options.length > 0;

  return (
    <div className="pointer-events-none fixed inset-x-2 bottom-2 z-40 sm:inset-x-4">
      <div className="pointer-events-auto mx-auto grid w-full max-w-3xl gap-2 rounded-lg border border-[color:var(--border)] bg-[color:var(--panel)]/95 px-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_24px_rgba(32,38,30,0.12)] backdrop-blur">
        {open ? (
          <form className="grid gap-2" onSubmit={onSubmit}>
            <label className="sr-only" htmlFor="free-action-input">
              自由行动
            </label>
            <textarea
              className="min-h-20 resize-y rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3 text-base leading-6 outline-none focus:border-[color:var(--accent)] sm:min-h-20 sm:text-sm"
              disabled={disabled}
              id="free-action-input"
              onChange={(event) => onInputChange(event.target.value)}
              placeholder="输入你的具体行动..."
              value={input}
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                className="app-button"
                disabled={disabled}
                onClick={() => onOpenChange(false)}
                type="button"
              >
                收起
              </button>
              <button
                className="app-button app-button-primary"
                disabled={disabled || !input.trim()}
                type="submit"
              >
                {pending ? "生成中..." : "提交"}
              </button>
            </div>
          </form>
        ) : null}

        {open ? null : (
          <div
            className={
              hasOptions
                ? "grid grid-cols-4 gap-2 sm:grid-cols-[repeat(4,minmax(0,1fr))_minmax(7rem,1.1fr)]"
                : "grid gap-2 sm:justify-end"
            }
          >
            {hasOptions
              ? options.map((option) => (
                  <button
                    aria-label={`选择建议行动 ${option.key}`}
                    className="app-button bg-[color:var(--input)] text-base font-semibold transition hover:border-[color:var(--accent)]"
                    disabled={disabled}
                    key={option.key}
                    onClick={() => onSelect(option)}
                    type="button"
                  >
                    {option.key}
                  </button>
                ))
              : null}
            <button
              aria-expanded={open}
              className={
                hasOptions
                  ? "app-button app-button-primary col-span-4 sm:col-span-1"
                  : "app-button app-button-primary sm:min-w-32"
              }
              disabled={disabled}
              onClick={() => onOpenChange(true)}
              type="button"
            >
              自由行动
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

async function waitForTurnJob(
  gameId: string,
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: TurnJobRead) => void
) {
  for (let attempt = 0; attempt < turnMaxPolls; attempt += 1) {
    await sleep(turnPollIntervalMs);
    const job = await getTurnJob(gameId, jobId);
    onSnapshot(job);
    if (job.status === "completed") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error_message || "回合生成失败。");
    }
    onProgress(
      buildJobProgressMessage(job, "回合任务", (attempt + 1) * turnPollIntervalMs)
    );
  }
  throw new Error(
    `回合生成已等待 14 分钟，任务仍未完成。任务 ID：${jobId}。请稍后刷新或联系我查看任务状态。`
  );
}

async function waitForTurnJobWithStream(
  gameId: string,
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: TurnJobRead) => void
) {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return waitForTurnJob(gameId, jobId, onProgress, onSnapshot);
  }

  return new Promise<TurnJobRead>((resolve, reject) => {
    let latestJob = createInitialTurnProcess(gameId, jobId, "pending");
    let eventSource: EventSource | null = null;
    let connectTimer: number | null = null;
    let errorTimer: number | null = null;
    let settled = false;
    let fallbackStarted = false;
    let hasReceivedEvent = false;

    const cleanup = () => {
      settled = true;
      if (connectTimer !== null) {
        window.clearTimeout(connectTimer);
      }
      if (errorTimer !== null) {
        window.clearTimeout(errorTimer);
      }
      if (eventSource) {
        eventSource.close();
      }
    };

    const resolveOnce = (job: TurnJobRead) => {
      if (settled) {
        return;
      }
      cleanup();
      resolve(job);
    };

    const rejectOnce = (error: unknown) => {
      if (settled) {
        return;
      }
      cleanup();
      reject(error);
    };

    const startPollingFallback = (message: string) => {
      if (settled || fallbackStarted) {
        return;
      }
      fallbackStarted = true;
      if (connectTimer !== null) {
        window.clearTimeout(connectTimer);
      }
      if (errorTimer !== null) {
        window.clearTimeout(errorTimer);
      }
      if (eventSource) {
        eventSource.close();
      }
      onProgress(message);
      waitForTurnJob(gameId, jobId, onProgress, (job) => {
        latestJob = mergeTurnJobSnapshot(latestJob, job);
        onSnapshot(latestJob);
      })
        .then(resolveOnce)
        .catch(rejectOnce);
    };

    const applySnapshot = (job: TurnJobRead) => {
      latestJob = mergeTurnJobSnapshot(latestJob, job);
      onSnapshot(latestJob);
      if (latestJob.progress_message) {
        onProgress(latestJob.progress_message);
      }
      if (latestJob.status === "completed") {
        resolveOnce(latestJob);
      }
      if (latestJob.status === "failed") {
        rejectOnce(new Error(latestJob.error_message || "回合生成失败。"));
      }
    };

    const applyDelta = (streamEvent: TurnJobStreamEvent) => {
      const reasoningContent = streamEvent.reset_buffers
        ? streamEvent.reasoning_delta ?? ""
        : latestJob.reasoning_content + (streamEvent.reasoning_delta ?? "");
      const contentBuffer = streamEvent.reset_buffers
        ? streamEvent.content_delta ?? ""
        : latestJob.content_buffer + (streamEvent.content_delta ?? "");
      latestJob = {
        ...latestJob,
        status: streamEvent.status ?? latestJob.status,
        model_used: streamEvent.model_used ?? latestJob.model_used,
        reasoning_content: reasoningContent,
        content_buffer: contentBuffer,
        narrative_buffer: streamEvent.narrative_buffer ?? latestJob.narrative_buffer,
        progress_message: streamEvent.progress_message ?? latestJob.progress_message,
        last_event_at:
          streamEvent.last_event_at ?? streamEvent.sent_at ?? latestJob.last_event_at
      };
      onSnapshot(latestJob);
      if (streamEvent.progress_message) {
        onProgress(streamEvent.progress_message);
      }
    };

    const handleStreamEvent = (message: MessageEvent) => {
      if (settled || fallbackStarted) {
        return;
      }
      hasReceivedEvent = true;
      if (connectTimer !== null) {
        window.clearTimeout(connectTimer);
        connectTimer = null;
      }
      if (errorTimer !== null) {
        window.clearTimeout(errorTimer);
        errorTimer = null;
      }

      let streamEvent: TurnJobStreamEvent;
      try {
        streamEvent = parseTurnJobStreamEvent(message);
      } catch {
        startPollingFallback("实时剧情事件解析失败，已切换为轮询确认任务状态。");
        return;
      }

      if (streamEvent.job) {
        applySnapshot(streamEvent.job);
        return;
      }
      if (streamEvent.type === "delta" || streamEvent.type === "progress") {
        applyDelta(streamEvent);
      }
    };

    const streamEventNames: TurnJobStreamEvent["type"][] = [
      "snapshot",
      "delta",
      "progress",
      "completed",
      "failed",
      "heartbeat"
    ];

    try {
      eventSource = createTurnJobEventSource(gameId, jobId);
      for (const eventName of streamEventNames) {
        eventSource.addEventListener(eventName, handleStreamEvent as EventListener);
      }
      eventSource.onerror = () => {
        if (settled || fallbackStarted || errorTimer !== null) {
          return;
        }
        const delay = hasReceivedEvent ? turnStreamErrorFallbackMs : 1500;
        errorTimer = window.setTimeout(() => {
          startPollingFallback("实时剧情连接中断，已切换为轮询确认任务状态。");
        }, delay);
      };
      connectTimer = window.setTimeout(() => {
        startPollingFallback("实时剧情连接超时，已切换为轮询确认任务状态。");
      }, turnStreamConnectTimeoutMs);
    } catch (caught) {
      startPollingFallback(
        caught instanceof Error
          ? `实时剧情连接失败，已切换为轮询：${caught.message}`
          : "实时剧情连接失败，已切换为轮询确认任务状态。"
      );
    }
  });
}

function mergeTurnJobSnapshot(current: TurnJobRead, incoming: TurnJobRead): TurnJobRead {
  if (incoming.status === "completed" || incoming.status === "failed") {
    return incoming;
  }

  return {
    ...incoming,
    reasoning_content:
      incoming.reasoning_content.length >= current.reasoning_content.length
        ? incoming.reasoning_content
        : current.reasoning_content,
    content_buffer:
      incoming.content_buffer.length >= current.content_buffer.length
        ? incoming.content_buffer
        : current.content_buffer,
    narrative_buffer:
      incoming.narrative_buffer.length >= current.narrative_buffer.length
        ? incoming.narrative_buffer
        : current.narrative_buffer
  };
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

type StoryProcessJob = Pick<
  TurnJobRead,
  | "id"
  | "status"
  | "model_used"
  | "error_message"
  | "reasoning_content"
  | "narrative_buffer"
  | "progress_message"
  | "stream_started_at"
  | "last_event_at"
>;

function StoryPanel({
  characters,
  latestTurn,
  onCharacterClick,
  pending,
  process,
  progress
}: {
  characters: CharacterRead[];
  latestTurn: TurnRead | null;
  onCharacterClick: (character: CharacterRead) => void;
  pending: boolean;
  process: StoryProcessJob | null;
  progress: string | null;
}) {
  const reasoning = process?.reasoning_content || "";
  const liveNarrative = process?.narrative_buffer || "";
  const displayedNarrative = pending ? liveNarrative : liveNarrative || latestTurn?.gm_output;
  const hasLiveProcess = process !== null;
  const actionOptions = pending ? [] : latestTurn?.action_options_json ?? [];

  return (
    <article className="min-h-72 bg-[color:var(--panel)] px-1 py-2 sm:min-h-[28rem] sm:px-2 sm:py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">剧情</h2>
        {hasLiveProcess ? (
          <span className="rounded bg-[#edf2eb] px-2 py-1 text-xs font-medium text-[color:var(--accent-strong)]">
            {process.status}
          </span>
        ) : null}
      </div>

      {hasLiveProcess ? (
        <div className="mt-3 grid gap-3">
          <div className="app-status text-xs">
            <div>{progress || process.progress_message || "等待 DeepSeek 返回剧情。"}</div>
            <div className="mt-1">
              最近更新：{formatLastEvent(process.last_event_at)} · 思考 {reasoning.length} 字 ·
              剧情 {liveNarrative.length} 字
              {process.model_used ? ` · ${process.model_used}` : ""}
            </div>
          </div>
          <details className="rounded border border-[color:var(--border)] bg-[color:var(--input)]">
            <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
              思考过程
            </summary>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap border-t border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
              {reasoning || "尚未收到思考过程。"}
            </pre>
          </details>
        </div>
      ) : null}

      {displayedNarrative ? (
        <StoryMarkdown
          characters={characters}
          className="mt-5"
          content={displayedNarrative}
          onCharacterClick={onCharacterClick}
          showCaret={pending && Boolean(liveNarrative)}
        />
      ) : (
        <p className="mt-4 text-sm leading-6 text-[color:var(--muted)]">
          {pending ? "正在等待剧情正文..." : "还没有回合。输入自由行动开始第一回合。"}
        </p>
      )}

      {actionOptions.length > 0 ? (
        <section className="mt-5 border-t border-[color:var(--border)] pt-4">
          <h3 className="text-sm font-semibold">建议行动</h3>
          <div className="mt-3 grid gap-2">
            {actionOptions.map((option) => (
              <p className="text-sm leading-6" key={option.key}>
                <span className="font-semibold">{option.key}. </span>
                {option.label}
              </p>
            ))}
          </div>
        </section>
      ) : null}
    </article>
  );
}

function createInitialTurnProcess(
  gameId: string,
  id: string,
  status: TurnJobRead["status"]
): TurnJobRead {
  return {
    id,
    game_id: gameId,
    status,
    turn: null,
    turn_id: null,
    model_used: null,
    error_message: null,
    reasoning_content: "",
    content_buffer: "",
    narrative_buffer: "",
    progress_message: "任务已创建，等待 DeepSeek Pro 开始书写剧情。",
    stream_started_at: null,
    last_event_at: null
  };
}

function buildJobProgressMessage(
  job: StoryProcessJob,
  label: string,
  elapsedMs: number
): string {
  const statusText = job.status === "running" ? "运行中" : "排队中";
  const seconds = Math.round(elapsedMs / 1000);
  const base = job.progress_message || `${label}${statusText}`;
  return `${base}（${statusText}，已等待 ${seconds} 秒，最近更新：${formatLastEvent(
    job.last_event_at
  )}）`;
}

function formatLastEvent(value: string | null): string {
  if (!value) {
    return "暂无";
  }
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "未知";
  }
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 2) {
    return "刚刚";
  }
  if (seconds < 60) {
    return `${seconds} 秒前`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分钟前`;
}
