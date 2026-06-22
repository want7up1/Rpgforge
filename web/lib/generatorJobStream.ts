import {
  createGeneratorChatJobEventSource,
  createGeneratorFinalizeJobEventSource,
  getGeneratorChatJob,
  getGeneratorFinalizeJob,
  parseGeneratorJobStreamEvent
} from "@/lib/api";
import type { GeneratorChatJobRead, GeneratorFinalizeJobRead } from "@/lib/types";

const chatPollIntervalMs = 1500;
const chatMaxPolls = 80;
const finalizePollIntervalMs = 2000;
const finalizeMaxPolls = 450;
const generatorStreamConnectTimeoutMs = 6000;
const generatorStreamErrorFallbackMs = 4000;

export type StreamProcessJob = Pick<
  GeneratorChatJobRead,
  | "id"
  | "status"
  | "model_used"
  | "error_message"
  | "reasoning_content"
  | "content_buffer"
  | "progress_message"
  | "stream_started_at"
  | "last_event_at"
>;

type StreamableGeneratorJob = GeneratorChatJobRead | GeneratorFinalizeJobRead;

export function createInitialChatProcess(
  id: string,
  status: GeneratorChatJobRead["status"]
): GeneratorChatJobRead {
  return {
    id,
    status,
    response: null,
    model_used: null,
    error_message: null,
    reasoning_content: "",
    content_buffer: "",
    progress_message: "任务已创建，等待 DeepSeek Pro 开始流式返回。",
    stream_started_at: null,
    last_event_at: null
  };
}

export function createInitialFinalizeProcess(
  id: string,
  status: GeneratorFinalizeJobRead["status"]
): GeneratorFinalizeJobRead {
  return {
    id,
    status,
    config: null,
    warnings: [],
    model_used: null,
    error_message: null,
    reasoning_content: "",
    content_buffer: "",
    progress_message: "任务已创建，等待 DeepSeek Pro 开始流式返回。",
    stream_started_at: null,
    last_event_at: null
  };
}

export async function waitForChatJobWithStream(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorChatJobRead) => void,
  initialJob?: GeneratorChatJobRead
) {
  return waitForGeneratorJobWithStream(
    jobId,
    createGeneratorChatJobEventSource,
    () => waitForChatJob(jobId, onProgress, onSnapshot),
    onProgress,
    onSnapshot,
    initialJob
  );
}

export async function waitForFinalizeJobWithStream(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorFinalizeJobRead) => void,
  initialJob?: GeneratorFinalizeJobRead
) {
  return waitForGeneratorJobWithStream(
    jobId,
    createGeneratorFinalizeJobEventSource,
    () => waitForFinalizeJob(jobId, onProgress, onSnapshot),
    onProgress,
    onSnapshot,
    initialJob
  );
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

async function waitForChatJob(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorChatJobRead) => void
) {
  for (let attempt = 0; attempt < chatMaxPolls; attempt += 1) {
    await sleep(chatPollIntervalMs);
    const job = await getGeneratorChatJob(jobId);
    onSnapshot(job);
    if (job.status === "completed") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error_message || "冒险设定确认失败。");
    }
    onProgress(
      buildJobProgressMessage(job, "设定确认任务", (attempt + 1) * chatPollIntervalMs)
    );
  }
  throw new Error("冒险设定确认超时，请稍后重试。");
}

async function waitForFinalizeJob(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorFinalizeJobRead) => void
) {
  for (let attempt = 0; attempt < finalizeMaxPolls; attempt += 1) {
    await sleep(finalizePollIntervalMs);
    const job = await getGeneratorFinalizeJob(jobId);
    onSnapshot(job);
    if (job.status === "completed") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error_message || "冒险世界生成失败。");
    }
    onProgress(
      buildJobProgressMessage(job, "生成任务", (attempt + 1) * finalizePollIntervalMs)
    );
  }
  throw new Error(
    `冒险世界生成已等待 15 分钟，任务仍未完成。任务 ID：${jobId}。请稍后刷新或联系我查看任务状态。`
  );
}

function waitForGeneratorJobWithStream<TJob extends StreamableGeneratorJob>(
  jobId: string,
  createEventSource: (jobId: string) => EventSource,
  pollingFallback: () => Promise<TJob>,
  onProgress: (message: string) => void,
  onSnapshot: (job: TJob) => void,
  initialJob?: TJob
) {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return pollingFallback();
  }

  return new Promise<TJob>((resolve, reject) => {
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

    const resolveOnce = (job: TJob) => {
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
      pollingFallback().then(resolveOnce).catch(rejectOnce);
    };

    const applySnapshot = (job: TJob) => {
      onSnapshot(job);
      if (job.progress_message) {
        onProgress(job.progress_message);
      }
      if (job.status === "completed") {
        resolveOnce(job);
      }
      if (job.status === "failed") {
        rejectOnce(new Error(job.error_message || "生成任务失败。"));
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

      try {
        const streamEvent = parseGeneratorJobStreamEvent(message);
        if (streamEvent.job) {
          applySnapshot(streamEvent.job as TJob);
        }
      } catch {
        startPollingFallback("实时生成事件解析失败，已切换为轮询确认任务状态。");
      }
    };

    try {
      if (initialJob) {
        applySnapshot(initialJob);
        if (settled) {
          return;
        }
      }
      eventSource = createEventSource(jobId);
      for (const eventName of ["snapshot", "progress", "completed", "failed", "heartbeat"]) {
        eventSource.addEventListener(eventName, handleStreamEvent as EventListener);
      }
      eventSource.onerror = () => {
        if (settled || fallbackStarted || errorTimer !== null) {
          return;
        }
        const delay = hasReceivedEvent ? generatorStreamErrorFallbackMs : 1500;
        errorTimer = window.setTimeout(() => {
          startPollingFallback("实时生成连接中断，已切换为轮询确认任务状态。");
        }, delay);
      };
      connectTimer = window.setTimeout(() => {
        startPollingFallback("实时生成连接超时，已切换为轮询确认任务状态。");
      }, generatorStreamConnectTimeoutMs);
    } catch (caught) {
      startPollingFallback(
        caught instanceof Error
          ? `实时生成连接失败，已切换为轮询：${caught.message}`
          : "实时生成连接失败，已切换为轮询确认任务状态。"
      );
    }
  });
}

function buildJobProgressMessage(
  job: StreamProcessJob,
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
