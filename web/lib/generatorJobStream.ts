import {
  createGeneratorChatJobEventSource,
  createGeneratorFinalizeJobEventSource,
  getGeneratorChatJob,
  getGeneratorFinalizeJob,
  parseGeneratorJobStreamEvent
} from "@/lib/api";
import type { GeneratorChatJobRead, GeneratorFinalizeJobRead } from "@/lib/types";
import { formatLastEvent, sleep, StreamCursor, waitForJobStream, type StreamResult } from "@/lib/jobStream";
export { formatLastEvent } from "@/lib/jobStream";

const chatPollIntervalMs = 1500;
const chatMaxPolls = 80;
const finalizePollIntervalMs = 2000;
const finalizeMaxPolls = 450;

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

export function waitForChatJobWithStream(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorChatJobRead) => void,
  initialJob?: GeneratorChatJobRead,
  signal?: AbortSignal
) {
  return waitForGeneratorJobWithStream({
    jobId, onProgress, onSnapshot, initialJob, signal,
    connect: () => createGeneratorChatJobEventSource(jobId),
    get: () => getGeneratorChatJob(jobId, signal),
    interval: chatPollIntervalMs, maxPolls: chatMaxPolls,
    failure: "冒险设定确认失败。", timeout: "冒险设定确认超时，请稍后重试。"
  });
}

export function waitForFinalizeJobWithStream(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorFinalizeJobRead) => void,
  initialJob?: GeneratorFinalizeJobRead,
  signal?: AbortSignal
) {
  return waitForGeneratorJobWithStream({
    jobId, onProgress, onSnapshot, initialJob, signal,
    connect: () => createGeneratorFinalizeJobEventSource(jobId),
    get: () => getGeneratorFinalizeJob(jobId, signal),
    interval: finalizePollIntervalMs, maxPolls: finalizeMaxPolls,
    failure: "冒险世界生成失败。", timeout: `冒险世界生成已等待 15 分钟，任务仍未完成。任务 ID：${jobId}。请稍后刷新确认任务状态。`
  });
}

function waitForGeneratorJobWithStream<TJob extends StreamableGeneratorJob>(options: {
  jobId: string;
  onProgress: (message: string) => void;
  onSnapshot: (job: TJob) => void;
  initialJob?: TJob;
  signal?: AbortSignal;
  connect: () => EventSource;
  get: () => Promise<TJob>;
  interval: number;
  maxPolls: number;
  failure: string;
  timeout: string;
}): Promise<TJob> {
  const cursor = new StreamCursor();
  const apply = (job: TJob): StreamResult<TJob> => {
    if (job.id !== options.jobId || options.signal?.aborted || !cursor.accept(job)) return;
    options.onSnapshot(job);
    if (job.progress_message) options.onProgress(job.progress_message);
    if (job.status === "completed") return { done: job };
    if (job.status === "failed") return { error: new Error(job.error_message || options.failure) };
  };
  const initial = options.initialJob && apply(options.initialJob);
  if (initial) return "error" in initial ? Promise.reject(initial.error) : Promise.resolve(initial.done);
  return waitForJobStream({
    connect: options.connect,
    eventNames: ["snapshot", "progress", "completed", "failed", "heartbeat"],
    apply: (message) => {
      const event = parseGeneratorJobStreamEvent(message);
      if (event.job_id && event.job_id !== options.jobId) return;
      if (event.job) return apply({ ...event.job, stream_revision: event.stream_revision ?? event.job.stream_revision, event_seq: event.event_seq ?? event.job.event_seq } as unknown as TJob);
    },
    refresh: async () => apply(await options.get()),
    poll: async () => {
      for (let attempt = 0; attempt < options.maxPolls; attempt += 1) {
        await sleep(options.interval, options.signal);
        const job = await options.get();
        const result = apply(job);
        if (result) {
          if ("error" in result) throw result.error;
          return result.done;
        }
        const status = job.status === "running" ? "运行中" : "排队中";
        options.onProgress(`${job.progress_message || "生成任务"}（${status}，已等待 ${Math.round(((attempt + 1) * options.interval) / 1000)} 秒，最近更新：${formatLastEvent(job.last_event_at)}）`);
      }
      throw new Error(options.timeout);
    },
    onFallback: options.onProgress,
    label: "实时生成",
    signal: options.signal
  });
}
