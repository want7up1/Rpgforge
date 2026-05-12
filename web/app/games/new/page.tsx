"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { JsonBlock } from "@/components/JsonBlock";
import {
  createGeneratorChatJob,
  createGeneratorFinalizeJob,
  createGeneratedGame,
  createManualGame,
  getActiveGeneratorChatJob,
  getActiveGeneratorFinalizeJob,
} from "@/lib/api";
import {
  createInitialChatProcess,
  createInitialFinalizeProcess,
  formatLastEvent,
  waitForChatJobWithStream,
  waitForFinalizeJobWithStream,
  type StreamProcessJob
} from "@/lib/generatorJobStream";
import type {
  GeneratedGameConfig,
  GeneratorChatJobRead,
  GeneratorChatResponse,
  GeneratorFinalizeJobRead,
  GeneratorMessage,
} from "@/lib/types";

const sampleIdea = "黑暗武侠，主角是失忆镖师，地点是雁回镇义庄。";
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

  useEffect(() => {
    let cancelled = false;

    async function restoreActiveJobs() {
      try {
        const [activeFinalizeJob, activeChatJob] = await Promise.all([
          getActiveGeneratorFinalizeJob(),
          getActiveGeneratorChatJob()
        ]);
        if (cancelled) {
          return;
        }

        if (activeFinalizeJob) {
          setError(null);
          setPendingAction("finalize");
          setFinalizeProcess(activeFinalizeJob);
          setFinalizeProgress(
            activeFinalizeJob.progress_message || "检测到未完成冒险世界生成，正在恢复实时连接..."
          );
          const completedJob = await waitForFinalizeJobWithStream(
            activeFinalizeJob.id,
            setFinalizeProgress,
            setFinalizeProcess,
            activeFinalizeJob
          );
          if (cancelled) {
            return;
          }
          if (!completedJob.config) {
            throw new Error("恢复的生成任务已完成，但没有返回冒险世界。");
          }
          setGeneratedConfig(completedJob.config);
          setFinalizeProgress(completedJob.progress_message || "冒险世界生成完成。");
          setPendingAction(null);
          return;
        }

        if (activeChatJob) {
          setError(null);
          setPendingAction("chat");
          setChatProcess(activeChatJob);
          setChatProgress(
            activeChatJob.progress_message || "检测到未完成设定确认，正在恢复实时连接..."
          );
          const completedJob = await waitForChatJobWithStream(
            activeChatJob.id,
            setChatProgress,
            setChatProcess,
            activeChatJob
          );
          if (cancelled) {
            return;
          }
          if (!completedJob.response) {
            throw new Error("恢复的设定确认任务已完成，但没有返回内容。");
          }
          setLastReply(completedJob.response);
          setConfirmed(completedJob.response.confirmed_requirements);
          setChatProgress(`设定已确认，模型：${completedJob.response.model_used}`);
          setPendingAction(null);
        }
      } catch (caught) {
        if (cancelled) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "恢复生成任务失败。");
        setPendingAction(null);
      }
    }

    void restoreActiveJobs();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!idea.trim()) {
      return;
    }

    setError(null);
    setChatProgress("已开始确认设定，等待 DeepSeek Pro 返回...");
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
        throw new Error("设定确认任务已完成，但没有返回内容。");
      }
      const response = completedJob.response;
      setLastReply(response);
      setConfirmed(response.confirmed_requirements);
      setHistory((current) => [
        ...current,
        { role: "user", content: idea },
        { role: "assistant", content: response.assistant_reply }
      ]);
      setChatProgress(`设定已确认，模型：${response.model_used}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "冒险设定确认失败。");
      setChatProgress("设定确认失败，已保留收到的过程信息。");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleFinalize() {
    if (!idea.trim()) {
      return;
    }

    setError(null);
    setFinalizeProgress("已开始生成冒险世界，等待 DeepSeek Pro 返回...");
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
        throw new Error("生成任务已完成，但没有返回冒险世界。");
      }
      setGeneratedConfig(completedJob.config);
      setFinalizeProgress(`生成完成，模型：${completedJob.model_used ?? "unknown"}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "冒险世界生成失败。");
      setFinalizeProgress("冒险世界生成失败，已保留收到的过程信息。");
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
      setError(caught instanceof Error ? caught.message : "创建冒险失败。");
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
      <section className="game-page-hero">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <Link className="app-button mb-4 w-fit" href="/games">
              返回存档
            </Link>
            <p className="game-page-eyebrow">Adventure Forge</p>
            <h1 className="game-page-title">创建冒险</h1>
            <p className="mt-3 max-w-4xl text-sm leading-6 text-[color:var(--muted)]">
              先确认冒险方向，再生成世界资料、角色、状态、剧情导演和初始剧情。
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3 lg:min-w-96">
            <StatusStep active={pendingAction === "chat"} complete={history.length > 0} label="确认设定" />
            <StatusStep active={pendingAction === "finalize"} complete={Boolean(generatedConfig)} label="生成世界" />
            <StatusStep active={pendingAction === "create-generated"} complete={false} label="开始冒险" />
          </div>
        </div>
      </section>

      {error ? (
        <section className="app-alert">{error}</section>
      ) : null}

      <div className="generator-shell">
        <section className="generator-console">
          <form className="flex flex-col gap-4" onSubmit={handleChat}>
            <label className="grid gap-2">
              <span className="surface-title">冒险想法</span>
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
                {pendingAction === "chat" ? "确认中..." : "确认冒险设定"}
              </button>
              <button
                className="app-button"
                disabled={pendingAction !== null || !canFinalize}
                onClick={handleFinalize}
                type="button"
              >
                {pendingAction === "finalize" ? "生成世界中..." : "生成冒险世界"}
              </button>
            </div>
            {!canFinalize ? (
              <p className="surface-subtle">
                冒险设定确认后，才能生成完整冒险世界。
              </p>
            ) : null}
          </form>

          <div className="mt-5 border-t border-[color:var(--border)] pt-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="surface-title">设定确认记录</h2>
              <span className="app-pill">{history.length} 条消息</span>
            </div>
            {chatProgress ? (
              <div className="app-status mt-3">
                {chatProgress}
              </div>
            ) : null}
            <StreamProcessPanel
              contentLabel="回复内容"
              job={chatProcess}
              title="设定确认过程"
            />
            <div className="mt-3 grid gap-3">
              {history.length === 0 ? (
                <p className="surface-panel surface-subtle">
                  暂无记录。输入冒险想法后，系统会先确认题材、主角、核心冲突和玩法边界。
                </p>
              ) : (
                history.map((message, index) => (
                  <div
                    className={
                      message.role === "user"
                        ? "archive-card archive-card-green text-sm leading-6"
                        : "archive-card archive-card-accent text-sm leading-6"
                    }
                    key={`${message.role}-${index}`}
                  >
                    <span className="font-semibold">
                      {message.role === "user" ? "你" : "冒险引导"}
                    </span>
                    <p className="mt-1 text-[color:var(--muted)]">{message.content}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        <aside className="surface-grid">
          <section className="surface-panel surface-panel-strong">
            <h2 className="surface-title">生成流程</h2>
            <div className="generator-timeline mt-4">
              <div className="generator-step">
                <div>
                  <strong className="block text-[color:var(--foreground)]">确认冒险方向</strong>
                  <span>确认关键设定，避免后续世界资料偏离最初想法。</span>
                </div>
              </div>
              <div className="generator-step">
                <div>
                  <strong className="block text-[color:var(--foreground)]">生成冒险世界</strong>
                  <span>导演层会拆分任务，生成规则、世界书、角色、状态和剧情初始条件。</span>
                </div>
              </div>
              <div className="generator-step">
                <div>
                  <strong className="block text-[color:var(--foreground)]">开始冒险</strong>
                  <span>确认结果后写入存档，进入概览或直接开始第一回合。</span>
                </div>
              </div>
            </div>
          </section>

          <details className="surface-panel" open={Boolean(lastReply)}>
            <summary className="cursor-pointer surface-title">已确认设定</summary>
            <div className="mt-3">
              <JsonBlock data={confirmed} />
            </div>
            {lastReply ? (
              <div className="archive-card mt-4 text-sm leading-6">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">阶段</span>
                  <span className="app-pill">
                    {lastReply.stage}
                  </span>
                  <span className="text-xs text-[color:var(--muted)]">{lastReply.model_used}</span>
                </div>
                <p className="mt-3 text-[color:var(--muted)]">{lastReply.assistant_reply}</p>
              </div>
            ) : null}
          </details>

          <details
            className="surface-panel"
            open={Boolean(finalizeProcess || finalizeProgress || generatedConfig)}
          >
            <summary className="cursor-pointer surface-title">生成结果</summary>
            {finalizeProgress ? (
              <div className="app-status mt-3">
                {finalizeProgress}
              </div>
            ) : null}
            <StreamProcessPanel
              contentLabel="生成内容"
              job={finalizeProcess}
              title="冒险世界生成过程"
            />
            {generatedConfig ? (
              <div className="mt-3 grid gap-4">
                <div className="archive-card grid gap-2 text-sm">
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
                  {pendingAction === "create-generated" ? "创建中..." : "确认并开始冒险"}
                </button>
              </div>
            ) : (
              <p className="surface-subtle mt-3">
                确认设定后生成冒险世界，确认后写入存档。
              </p>
            )}
          </details>

          <details className="surface-panel">
            <summary className="cursor-pointer surface-title">高级：创建草稿冒险</summary>
            <p className="surface-subtle mt-2">
              这个入口只创建结构化草稿，不伪造 AI 输出。用于验证存档和页面流程。
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
                {pendingAction === "create-manual" ? "创建中..." : "创建草稿冒险"}
              </button>
            </div>
          </details>
        </aside>
      </div>
    </AppShell>
  );
}

function StatusStep({
  active,
  complete,
  label
}: {
  active: boolean;
  complete: boolean;
  label: string;
}) {
  return (
    <div
      className={
        active || complete
          ? "metric-tile border-[color:var(--accent-strong)]"
          : "metric-tile"
      }
    >
      <p className="metric-tile-label">{label}</p>
      <p className="mt-1 text-sm font-semibold">
        {complete ? "完成" : active ? "运行中" : "待开始"}
      </p>
    </div>
  );
}

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
