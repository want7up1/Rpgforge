import {
  createTurnJobEventSource,
  getTurnJob,
  parseTurnJobStreamEvent
} from "@/lib/api";
import type { TurnJobRead, TurnJobStreamEvent } from "@/lib/types";

const turnPollIntervalMs = 1500;
const turnMaxPolls = 560;
const turnStreamConnectTimeoutMs = 6000;
const turnStreamErrorFallbackMs = 4000;

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
    stage_total: 8,
    stage_started_at: null,
    stream_started_at: null,
    last_event_at: null
  };
}

export async function waitForTurnJobWithStream(
  gameId: string,
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: TurnJobRead) => void,
  initialJob?: TurnJobRead
) {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return waitForTurnJob(gameId, jobId, onProgress, onSnapshot);
  }

  return new Promise<TurnJobRead>((resolve, reject) => {
    let latestJob = initialJob ?? createInitialTurnProcess(gameId, jobId, "pending");
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
        stage: streamEvent.stage ?? latestJob.stage,
        stage_label: streamEvent.stage_label ?? latestJob.stage_label,
        stage_index: streamEvent.stage_index ?? latestJob.stage_index,
        stage_total: streamEvent.stage_total ?? latestJob.stage_total,
        stage_started_at: streamEvent.stage_started_at ?? latestJob.stage_started_at,
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

export function formatLastEvent(value: string | null): string {
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

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
