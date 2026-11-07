import {
  createTurnJobEventSource,
  getTurnJob,
  parseTurnJobStreamEvent
} from "@/lib/api";
import type { TurnJobRead, TurnJobStreamEvent } from "@/lib/types";
import { abortError, formatLastEvent, sleep, StreamCursor, waitForJobStream, type StreamResult } from "@/lib/jobStream";
export { formatLastEvent } from "@/lib/jobStream";

const turnPollIntervalMs = 1500;
const turnMaxPolls = 560;
const turnMaintenanceMaxPolls = 120;

export type StoryProcessJob = Pick<
  TurnJobRead,
  | "id"
  | "status"
  | "model_used"
  | "error_message"
  | "reasoning_content"
  | "narrative_buffer"
  | "progress_message"
  | "stage"
  | "stage_label"
  | "stage_index"
  | "stage_total"
  | "stage_started_at"
  | "maintenance_status"
  | "maintenance_stage"
  | "maintenance_message"
  | "maintenance_error"
  | "maintenance_started_at"
  | "maintenance_completed_at"
  | "stream_started_at"
  | "last_event_at"
>;

export function createInitialTurnProcess(
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
    stage: "prepare_context",
    stage_label: "准备上下文",
    stage_index: 1,
    stage_total: 6,
    stage_started_at: null,
    maintenance_status: "pending",
    maintenance_stage: "state_extract",
    maintenance_message: "等待回合生成完成后执行状态维护。",
    maintenance_error: null,
    maintenance_started_at: null,
    maintenance_completed_at: null,
    stream_started_at: null,
    last_event_at: null
  };
}

export async function waitForTurnJobWithStream(
  gameId: string,
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: TurnJobRead) => void,
  initialJob?: TurnJobRead,
  signal?: AbortSignal
): Promise<TurnJobRead> {
  let latest = initialJob ?? createInitialTurnProcess(gameId, jobId, "pending");
  const cursor = new StreamCursor();
  let reasoningLength = Array.from(latest.reasoning_content).length;
  let contentLength = Array.from(latest.content_buffer).length;
  const applySnapshot = (incoming: TurnJobRead, authoritative = false): StreamResult<TurnJobRead> => {
    if (incoming.id !== jobId || incoming.game_id !== gameId || signal?.aborted) return;
    const terminal = incoming.status === "completed" || incoming.status === "failed";
    // 进程可能在帧已发出、seq节流落盘前崩溃。只有直接GET的权威终态可以结束
    // 这个不可复用的job；迟到的SSE快照仍严格按游标拒绝，旧时间线也不能穿过。
    const terminalRecovery = authoritative && terminal
      && (incoming.timeline_generation ?? latest.timeline_generation ?? 0) >= (latest.timeline_generation ?? 0);
    if (!cursor.accept(incoming) && !terminalRecovery) return;
    latest = mergeTurnJobSnapshot(latest, incoming);
    reasoningLength = Array.from(latest.reasoning_content).length;
    contentLength = Array.from(latest.content_buffer).length;
    onSnapshot(latest);
    if (latest.progress_message) onProgress(latest.progress_message);
    if (latest.status === "completed") return { done: latest };
    if (latest.status === "failed") return { error: new Error(latest.error_message || "回合生成失败。") };
  };
  const initial = initialJob && applySnapshot(initialJob);
  if (initial) {
    if ("error" in initial) throw initial.error;
    return initial.done;
  }
  return waitForJobStream({
    connect: () => createTurnJobEventSource(gameId, jobId),
    eventNames: ["snapshot", "delta", "progress", "completed", "failed", "heartbeat"],
    apply: (message) => {
      const event = parseTurnJobStreamEvent(message);
      if (event.job_id && event.job_id !== jobId) return;
      if (event.job) return applySnapshot({ ...event.job, ...streamMetadata(event) });
      if (event.type !== "delta" && event.type !== "progress") return;
      if (!cursor.accept(event)) return;
      const reset = event.reset_buffers || (event.stream_revision ?? 0) > (latest.stream_revision ?? 0)
        || (event.timeline_generation ?? 0) > (latest.timeline_generation ?? 0);
      const nextReasoningLength = (reset ? 0 : reasoningLength) + Array.from(event.reasoning_delta ?? "").length;
      const nextContentLength = (reset ? 0 : contentLength) + Array.from(event.content_delta ?? "").length;
      if ((event.reasoning_length !== undefined && event.reasoning_length !== nextReasoningLength)
        || (event.content_length !== undefined && event.content_length !== nextContentLength)) {
        throw new Error("流分片缺失，需要完整快照。");
      }
      reasoningLength = nextReasoningLength;
      contentLength = nextContentLength;
      latest = {
        ...latest,
        ...streamMetadata(event),
        status: event.status ?? latest.status,
        model_used: event.model_used ?? latest.model_used,
        reasoning_content: (reset ? "" : latest.reasoning_content) + (event.reasoning_delta ?? ""),
        content_buffer: (reset ? "" : latest.content_buffer) + (event.content_delta ?? ""),
        narrative_buffer: event.narrative_buffer ?? (reset ? "" : latest.narrative_buffer),
        progress_message: event.progress_message ?? latest.progress_message,
        stage: event.stage ?? latest.stage,
        stage_label: event.stage_label ?? latest.stage_label,
        stage_index: event.stage_index ?? latest.stage_index,
        stage_total: event.stage_total ?? latest.stage_total,
        stage_started_at: event.stage_started_at ?? latest.stage_started_at,
        last_event_at: event.last_event_at ?? event.sent_at ?? latest.last_event_at
      };
      onSnapshot(latest);
      if (event.progress_message) onProgress(event.progress_message);
    },
    refresh: async () => applySnapshot(await getTurnJob(gameId, jobId, signal), true),
    poll: () => waitForTurnJob(gameId, jobId, onProgress, job => applySnapshot(job, true), signal),
    onFallback: onProgress,
    label: "实时剧情",
    signal
  });
}

function streamMetadata(event: TurnJobStreamEvent) {
  return Object.fromEntries(Object.entries({
    stream_revision: event.stream_revision, event_seq: event.event_seq,
    timeline_generation: event.timeline_generation, game_revision: event.game_revision
  }).filter(([, value]) => value !== undefined));
}

export function isTurnMaintenanceActive(job: StoryProcessJob | TurnJobRead | null): boolean {
  return (
    job?.status === "completed" &&
    (job.maintenance_status === "pending" || job.maintenance_status === "running") &&
    job.maintenance_stage === "state_extract"
  );
}

export function isTurnBackgroundMaintenanceActive(
  job: StoryProcessJob | TurnJobRead | null
): boolean {
  return (
    job?.status === "completed" &&
    job.maintenance_status === "running" &&
    job.maintenance_stage === "memory_summary"
  );
}

export async function waitForTurnMaintenance(
  gameId: string,
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: TurnJobRead) => void,
  signal?: AbortSignal
) {
  for (let attempt = 0; attempt < turnMaintenanceMaxPolls; attempt += 1) {
    await sleep(turnPollIntervalMs, signal);
    const job = await getTurnJob(gameId, jobId, signal);
    onSnapshot(job);
    if (!isTurnMaintenanceActive(job)) {
      return job;
    }
    onProgress(buildMaintenanceProgressMessage(job, (attempt + 1) * turnPollIntervalMs));
  }
  throw new Error(
    `状态提取已等待 14 分钟，任务仍未完成。任务 ID：${jobId}。请稍后刷新或联系我查看任务状态。`
  );
}

async function waitForTurnJob(
  gameId: string,
  jobId: string,
  onProgress: (message: string) => void,
  apply: (job: TurnJobRead) => StreamResult<TurnJobRead>,
  signal?: AbortSignal
) {
  for (let attempt = 0; attempt < turnMaxPolls; attempt += 1) {
    await sleep(turnPollIntervalMs, signal);
    const job = await getTurnJob(gameId, jobId, signal);
    if (signal?.aborted) throw abortError();
    const result = apply(job);
    if (result) {
      if ("error" in result) throw result.error;
      return result.done;
    }
    onProgress(buildJobProgressMessage(job, "回合任务", (attempt + 1) * turnPollIntervalMs));
  }
  throw new Error(`回合生成已等待 14 分钟，任务仍未完成。任务 ID：${jobId}。请稍后刷新确认任务状态。`);
}

export function mergeTurnJobSnapshot(current: TurnJobRead, incoming: TurnJobRead): TurnJobRead {
  if ((incoming.stream_revision ?? 0) > (current.stream_revision ?? 0)
    || (incoming.timeline_generation ?? 0) > (current.timeline_generation ?? 0)
    || incoming.status === "completed" || incoming.status === "failed") {
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

function buildMaintenanceProgressMessage(job: StoryProcessJob, elapsedMs: number): string {
  const seconds = Math.round(elapsedMs / 1000);
  const stageLabel = formatMaintenanceStage(job.maintenance_stage);
  const base = job.maintenance_message || `正在进行${stageLabel}`;
  return `${base}（${stageLabel}，已等待 ${seconds} 秒，最近更新：${formatLastEvent(
    job.last_event_at
  )}）`;
}

export function formatMaintenanceStage(stage: string | null): string {
  if (stage === "state_extract") {
    return "状态提取";
  }
  if (stage === "memory_summary") {
    return "记忆摘要";
  }
  if (stage === "completed") {
    return "维护完成";
  }
  return "状态维护";
}
