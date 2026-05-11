"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { JsonBlock } from "@/components/JsonBlock";
import {
  createGeneratorChatJobEventSource,
  createGeneratorChatJob,
  createGeneratorFinalizeJobEventSource,
  createGeneratorFinalizeJob,
  createGeneratedGame,
  createManualGame,
  getGeneratorChatJob,
  getGeneratorFinalizeJob,
  parseGeneratorJobStreamEvent,
} from "@/lib/api";
import type {
  GeneratedGameConfig,
  GeneratorChatJobRead,
  GeneratorChatResponse,
  GeneratorFinalizeJobRead,
  GeneratorMessage,
} from "@/lib/types";

const sampleIdea = "黑暗武侠，主角是失忆镖师，地点是雁回镇义庄。";
const chatPollIntervalMs = 1500;
const chatMaxPolls = 80;
const finalizePollIntervalMs = 2000;
const finalizeMaxPolls = 450;
const generatorStreamConnectTimeoutMs = 6000;
const generatorStreamErrorFallbackMs = 4000;

export default function NewGamePage() {
  const router = useRouter();
  const [idea, setIdea] = useState(sampleIdea);
  const [manualTitle, setManualTitle] = useState("雁回镇旧案");
  const [history, setHistory] = useState<GeneratorMessage[]>([]);
  const [confirmed, setConfirmed] = useState<Record<string, unknown>>({});
  const [lastReply, setLastReply] = useState<GeneratorChatResponse | null>(null);
  const [generatedConfig, setGeneratedConfig] = useState<GeneratedGameConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [chatProgress, setChatProgress] = useState<string | null>(null);
  const [finalizeProgress, setFinalizeProgress] = useState<string | null>(null);
  const [chatProcess, setChatProcess] = useState<GeneratorChatJobRead | null>(null);
  const [finalizeProcess, setFinalizeProcess] = useState<GeneratorFinalizeJobRead | null>(null);

  async function handleChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!idea.trim()) {
      return;
    }

    setError(null);
    setChatProgress("已创建访谈任务，等待 DeepSeek Pro 返回...");
    setFinalizeProgress(null);
    setChatProcess(null);
    setGeneratedConfig(null);
    setPendingAction("chat");
    try {
      const job = await createGeneratorChatJob({
        user_input: idea,
        history,
        confirmed_requirements: confirmed
      });
      setChatProcess(createInitialChatProcess(job.id, job.status));
      const completedJob = await waitForChatJobWithStream(
        job.id,
        setChatProgress,
        setChatProcess
      );
      if (!completedJob.response) {
        throw new Error("访谈任务已完成，但没有返回内容。");
      }
      const response = completedJob.response;
      setLastReply(response);
      setConfirmed(response.confirmed_requirements);
      setHistory((current) => [
        ...current,
        { role: "user", content: idea },
        { role: "assistant", content: response.assistant_reply }
      ]);
      setChatProgress(`访谈完成，模型：${response.model_used}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "规则生成器请求失败。");
      setChatProgress("访谈失败，已保留收到的过程信息。");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleFinalize() {
    if (!idea.trim()) {
      return;
    }

    setError(null);
    setFinalizeProgress("已创建生成任务，等待 DeepSeek Pro 返回配置...");
    setFinalizeProcess(null);
    setPendingAction("finalize");
    try {
      const job = await createGeneratorFinalizeJob({
        concept: idea,
        history,
        confirmed_requirements: confirmed
      });
      setFinalizeProcess(createInitialFinalizeProcess(job.id, job.status));
      const completedJob = await waitForFinalizeJobWithStream(
        job.id,
        setFinalizeProgress,
        setFinalizeProcess
      );
      if (!completedJob.config) {
        throw new Error("生成任务已完成，但没有返回配置。");
      }
      setGeneratedConfig(completedJob.config);
      setFinalizeProgress(`生成完成，模型：${completedJob.model_used ?? "unknown"}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "游戏配置生成失败。");
      setFinalizeProgress("完整配置生成失败，已保留收到的过程信息。");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleCreateGenerated() {
    if (!generatedConfig) {
      return;
    }

    setError(null);
    setPendingAction("create-generated");
    try {
      const response = await createGeneratedGame(generatedConfig);
      router.push(`/games/${response.game.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建游戏失败。");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleManualCreate() {
    if (!manualTitle.trim()) {
      return;
    }

    setError(null);
    setPendingAction("create-manual");
    try {
      const game = await createManualGame({
        title: manualTitle,
        genre: "草稿",
        description: idea
      });
      router.push(`/games/${game.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建草稿失败。");
    } finally {
      setPendingAction(null);
    }
  }

  const canFinalize = lastReply?.stage === "ready_to_generate";

  return (
    <AppShell>
      <section className="flex flex-col gap-2">
        <Link className="app-button w-fit" href="/games">
          返回游戏列表
        </Link>
        <h1 className="text-2xl font-semibold sm:text-3xl">规则生成器</h1>
        <p className="max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
          与 DeepSeek V4 讨论游戏需求，生成世界观、剧本骨架、世界资料、模式注入和初始状态。
        </p>
      </section>

      {error ? (
        <section className="app-alert">{error}</section>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="app-card app-card-pad">
          <form className="flex flex-col gap-4" onSubmit={handleChat}>
            <label className="grid gap-2">
              <span className="text-sm font-semibold">游戏想法</span>
              <textarea
                className="app-input min-h-40 resize-y leading-6"
                onChange={(event) => setIdea(event.target.value)}
                value={idea}
              />
            </label>
            <div className="grid gap-2 sm:flex sm:flex-wrap">
              <button
                className="app-button app-button-primary"
                disabled={pendingAction !== null}
                type="submit"
              >
                {pendingAction === "chat" ? "访谈中..." : "发送给规则生成器"}
              </button>
              <button
                className="app-button"
                disabled={pendingAction !== null || !canFinalize}
                onClick={handleFinalize}
                type="button"
              >
                {pendingAction === "finalize" ? "生成任务运行中..." : "生成完整配置"}
              </button>
            </div>
            {!canFinalize ? (
              <p className="text-xs leading-5 text-[color:var(--muted)]">
                规则生成器确认设定后，才能生成完整配置。
              </p>
            ) : null}
          </form>

          <div className="mt-6 border-t border-[color:var(--border)] pt-5">
            <h2 className="text-lg font-semibold">访谈记录</h2>
            {chatProgress ? (
              <div className="app-status mt-3">
                {chatProgress}
              </div>
            ) : null}
            <StreamProcessPanel
              contentLabel="回复内容"
              job={chatProcess}
              title="访谈过程"
            />
            <div className="mt-3 grid gap-3">
              {history.length === 0 ? (
                <p className="text-sm text-[color:var(--muted)]">暂无记录。</p>
              ) : (
                history.map((message, index) => (
                  <div
                    className="rounded border border-[color:var(--border)] p-3 text-sm leading-6"
                    key={`${message.role}-${index}`}
                  >
                    <span className="font-semibold">
                      {message.role === "user" ? "你" : "规则生成器"}
                    </span>
                    <p className="mt-1 text-[color:var(--muted)]">{message.content}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        <aside className="flex flex-col gap-5">
          <details className="app-card app-card-pad" open={Boolean(lastReply)}>
            <summary className="cursor-pointer text-lg font-semibold">已确认设定</summary>
            <div className="mt-3">
              <JsonBlock data={confirmed} />
            </div>
            {lastReply ? (
              <div className="mt-4 rounded border border-[color:var(--border)] p-3 text-sm leading-6">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">阶段</span>
                  <span className="rounded bg-[#edf2eb] px-2 py-1 text-xs font-medium text-[color:var(--accent-strong)]">
                    {lastReply.stage}
                  </span>
                  <span className="text-xs text-[color:var(--muted)]">{lastReply.model_used}</span>
                </div>
                <p className="mt-3 text-[color:var(--muted)]">{lastReply.assistant_reply}</p>
              </div>
            ) : null}
          </details>

          <details
            className="app-card app-card-pad"
            open={Boolean(finalizeProcess || finalizeProgress || generatedConfig)}
          >
            <summary className="cursor-pointer text-lg font-semibold">生成结果</summary>
            {finalizeProgress ? (
              <div className="app-status mt-3">
                {finalizeProgress}
              </div>
            ) : null}
            <StreamProcessPanel
              contentLabel="生成内容"
              job={finalizeProcess}
              title="完整配置生成过程"
            />
            {generatedConfig ? (
              <div className="mt-3 grid gap-4">
                <div className="grid gap-2 text-sm">
                  <div>
                    <span className="font-semibold">{generatedConfig.title}</span>
                    <span className="ml-2 text-[color:var(--muted)]">
                      {generatedConfig.genre || "未分类"}
                    </span>
                  </div>
                  <p className="text-[color:var(--muted)]">
                    世界资料 {generatedConfig.lore_entries.length} 条，模式{" "}
                    {generatedConfig.modes.length} 个
                  </p>
                </div>
                <JsonBlock data={generatedConfig} />
                <button
                  className="app-button app-button-primary"
                  disabled={pendingAction !== null}
                  onClick={handleCreateGenerated}
                  type="button"
                >
                  {pendingAction === "create-generated" ? "创建中..." : "确认并创建游戏"}
                </button>
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
                完成访谈后生成完整配置，确认后写入数据库。
              </p>
            )}
          </details>

          <details className="app-card app-card-pad">
            <summary className="cursor-pointer text-lg font-semibold">高级：创建草稿游戏</summary>
            <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
              这个入口只创建结构化草稿，不伪造 AI 输出。用于验证数据库和页面流程。
            </p>
            <div className="mt-4 flex flex-col gap-3">
              <input
                className="app-input"
                onChange={(event) => setManualTitle(event.target.value)}
                value={manualTitle}
              />
              <button
                className="app-button"
                disabled={pendingAction !== null}
                onClick={handleManualCreate}
                type="button"
              >
                {pendingAction === "create-manual" ? "创建中..." : "创建草稿游戏"}
              </button>
            </div>
          </details>
        </aside>
      </div>
    </AppShell>
  );
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
      throw new Error(job.error_message || "规则生成器访谈失败。");
    }
    onProgress(
      buildJobProgressMessage(job, "访谈任务", (attempt + 1) * chatPollIntervalMs)
    );
  }
  throw new Error("规则生成器访谈超时，请稍后重试。");
}

async function waitForChatJobWithStream(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorChatJobRead) => void
) {
  return waitForGeneratorJobWithStream(
    jobId,
    createGeneratorChatJobEventSource,
    () => waitForChatJob(jobId, onProgress, onSnapshot),
    onProgress,
    onSnapshot
  );
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
      throw new Error(job.error_message || "完整配置生成失败。");
    }
    onProgress(
      buildJobProgressMessage(job, "生成任务", (attempt + 1) * finalizePollIntervalMs)
    );
  }
  throw new Error(
    `完整配置生成已等待 15 分钟，任务仍未完成。任务 ID：${jobId}。请稍后刷新或联系我查看任务状态。`
  );
}

async function waitForFinalizeJobWithStream(
  jobId: string,
  onProgress: (message: string) => void,
  onSnapshot: (job: GeneratorFinalizeJobRead) => void
) {
  return waitForGeneratorJobWithStream(
    jobId,
    createGeneratorFinalizeJobEventSource,
    () => waitForFinalizeJob(jobId, onProgress, onSnapshot),
    onProgress,
    onSnapshot
  );
}

type StreamableGeneratorJob = GeneratorChatJobRead | GeneratorFinalizeJobRead;

function waitForGeneratorJobWithStream<TJob extends StreamableGeneratorJob>(
  jobId: string,
  createEventSource: (jobId: string) => EventSource,
  pollingFallback: () => Promise<TJob>,
  onProgress: (message: string) => void,
  onSnapshot: (job: TJob) => void
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

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

type StreamProcessJob = Pick<
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

function StreamProcessPanel({
  title,
  job,
  contentLabel
}: {
  title: string;
  job: StreamProcessJob | null;
  contentLabel: string;
}) {
  if (!job) {
    return null;
  }

  const reasoning = job.reasoning_content || "";
  const content = job.content_buffer || "";
  const isRunning = job.status === "running";

  return (
    <div className="mt-3 grid gap-3 rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{title}</span>
        <span className="rounded bg-[#edf2eb] px-2 py-1 text-xs font-medium text-[color:var(--accent-strong)]">
          {job.status}
        </span>
        {job.model_used ? (
          <span className="text-xs text-[color:var(--muted)]">{job.model_used}</span>
        ) : null}
      </div>
      <div className="grid gap-1 text-xs leading-5 text-[color:var(--muted)]">
        <span>{job.progress_message || "等待 DeepSeek 返回流式事件。"}</span>
        <span>
          最近更新：{formatLastEvent(job.last_event_at)} · 思考 {reasoning.length} 字 · 内容{" "}
          {content.length} 字
        </span>
        <span className="break-all">任务 ID：{job.id}</span>
      </div>
      <details className="rounded border border-[color:var(--border)]" open={isRunning}>
        <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
          思考过程
        </summary>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
          {reasoning || "尚未收到思考过程。"}
        </pre>
      </details>
      <details
        className="rounded border border-[color:var(--border)]"
        open={isRunning && content.length > 0}
      >
        <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
          {contentLabel}
        </summary>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap border-t border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
          {content || "尚未收到正文内容。"}
        </pre>
      </details>
    </div>
  );
}

function createInitialChatProcess(
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

function createInitialFinalizeProcess(
  id: string,
  status: GeneratorFinalizeJobRead["status"]
): GeneratorFinalizeJobRead {
  return {
    id,
    status,
    config: null,
    model_used: null,
    error_message: null,
    reasoning_content: "",
    content_buffer: "",
    progress_message: "任务已创建，等待 DeepSeek Pro 开始流式返回。",
    stream_started_at: null,
    last_event_at: null
  };
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
