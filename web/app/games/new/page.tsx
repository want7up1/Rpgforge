"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ChatDock } from "@/components/generator/ChatDock";
import { ChatHistorySheet } from "@/components/generator/ChatHistorySheet";
import { GenerationProgress, type ProgressItem } from "@/components/generator/GenerationProgress";
import { SettingsBoard } from "@/components/generator/SettingsBoard";
import {
  createGeneratedGame,
  createGeneratorChatJob,
  createGeneratorFinalizeJob,
  getActiveGeneratorChatJob,
  getActiveGeneratorFinalizeJob
} from "@/lib/api";
import {
  BOARD_CATEGORIES,
  buildBoardModel,
  deleteBlock,
  diffBoard,
  lockBlock,
  unlockBlock,
  writeBlockFields,
  type BoardBlock,
  type BoardDiff,
  type BoardField,
  type BoardModel
} from "@/lib/generatorBoard";
import {
  createInitialChatProcess,
  createInitialFinalizeProcess,
  waitForChatJobWithStream,
  waitForFinalizeJobWithStream
} from "@/lib/generatorJobStream";
import type {
  GeneratedGameConfig,
  GeneratorChatJobRead,
  GeneratorFinalizeJobRead,
  GeneratorMessage
} from "@/lib/types";

// confirmed 阶段的 block id 恰为 confirmed_requirements 字段名，用于过滤出可发后端的 locked_fields。
const CONFIRMED_FIELD_IDS = [
  "story_background", "core_premise", "tone_preferences",
  "playstyle_preferences", "must_include", "forbidden_content"
];

const EMPTY_DIFF: BoardDiff = {
  changedCategories: Object.fromEntries(
    BOARD_CATEGORIES.map((c) => [c.id, 0])
  ) as BoardDiff["changedCategories"],
  changedBlockIds: new Set<string>()
};

const sampleIdea =
  "黑暗武侠，故事发生在雁回镇义庄。主角是失忆镖师，必须出现雨夜义庄、红伞女人和失踪镖队。不要变成修仙飞升，也不要太快揭露主角身世。";

export default function NewGamePage() {
  const router = useRouter();
  const [chatInput, setChatInput] = useState(sampleIdea);
  const [history, setHistory] = useState<GeneratorMessage[]>([]);
  const [confirmed, setConfirmed] = useState<Record<string, unknown>>({});
  const [stage, setStage] = useState<string | null>(null);
  const [generatedConfig, setGeneratedConfig] = useState<GeneratedGameConfig | null>(null);
  const [lockedIds, setLockedIds] = useState<string[]>([]);
  const [lastDiff, setLastDiff] = useState<BoardDiff>(EMPTY_DIFF);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [chatProcess, setChatProcess] = useState<GeneratorChatJobRead | null>(null);
  const [finalizeProcess, setFinalizeProcess] = useState<GeneratorFinalizeJobRead | null>(null);

  // 解锁时恢复 AI 原值用：最近一次 AI 产出的快照。
  const aiConfirmedRef = useRef<Record<string, unknown>>({});
  const aiSettingsRef = useRef<Record<string, unknown>>({});
  // 每轮开始前的看板基线，用于 diff。
  const baselineRef = useRef<BoardModel | null>(null);

  const model: BoardModel = useMemo(() => {
    if (generatedConfig) {
      return buildBoardModel({ source: "settings", settings: generatedConfig.story_settings });
    }
    return buildBoardModel({ source: "confirmed", confirmed });
  }, [generatedConfig, confirmed]);

  function currentModel(): BoardModel {
    if (generatedConfig) {
      return buildBoardModel({ source: "settings", settings: generatedConfig.story_settings });
    }
    return buildBoardModel({ source: "confirmed", confirmed });
  }

  // 恢复进行中任务（沿用原逻辑，简化为只接管结果）。
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const [fin, chat] = await Promise.all([
          getActiveGeneratorFinalizeJob(),
          getActiveGeneratorChatJob()
        ]);
        if (cancelled) return;
        if (fin) {
          setPendingAction("finalize");
          setFinalizeProcess(fin);
          const done = await waitForFinalizeJobWithStream(fin.id, () => {}, setFinalizeProcess, fin);
          if (cancelled || !done.config) return;
          aiSettingsRef.current = done.config.story_settings;
          setGeneratedConfig(done.config);
          setPendingAction(null);
          return;
        }
        if (chat) {
          setPendingAction("chat");
          setChatProcess(chat);
          const done = await waitForChatJobWithStream(chat.id, () => {}, setChatProcess, chat);
          if (cancelled || !done.response) return;
          aiConfirmedRef.current = done.response.confirmed_requirements;
          setConfirmed(done.response.confirmed_requirements);
          setStage(done.response.stage);
          setPendingAction(null);
        }
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "恢复生成任务失败。");
        setPendingAction(null);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleChat() {
    if (!chatInput.trim()) return;
    setError(null);
    baselineRef.current = currentModel();
    setPendingAction("chat");
    const lockedConfirmed = lockedIds.filter((id) => CONFIRMED_FIELD_IDS.includes(id));
    try {
      const job = await createGeneratorChatJob({
        user_input: chatInput,
        history,
        confirmed_requirements: confirmed,
        locked_fields: lockedConfirmed
      });
      setChatProcess(createInitialChatProcess(job.id, job.status));
      const done = await waitForChatJobWithStream(job.id, () => {}, setChatProcess);
      if (!done.response) throw new Error("设定确认任务已完成，但没有返回内容。");
      const aiConfirmed = done.response.confirmed_requirements;
      const assistantReply = done.response.assistant_reply;
      aiConfirmedRef.current = aiConfirmed;
      // 客户端兜底强制锁定：把用户锁定字段的旧值覆盖回 AI 结果，防被改回。
      const merged = { ...aiConfirmed };
      for (const id of lockedConfirmed) merged[id] = confirmed[id];
      setConfirmed(merged);
      setStage(done.response.stage);
      setHistory((cur) => [
        ...cur,
        { role: "user", content: chatInput },
        { role: "assistant", content: assistantReply }
      ]);
      setChatInput("");
      const next = buildBoardModel({ source: "confirmed", confirmed: merged });
      setLastDiff(diffBoard(baselineRef.current, next));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "冒险设定确认失败。");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleFinalize() {
    setError(null);
    baselineRef.current = currentModel();
    setPendingAction("finalize");
    try {
      const job = await createGeneratorFinalizeJob({
        concept: confirmed.story_background ? String(confirmed.story_background) : sampleIdea,
        history,
        confirmed_requirements: confirmed
      });
      setFinalizeProcess(createInitialFinalizeProcess(job.id, job.status));
      const done = await waitForFinalizeJobWithStream(job.id, () => {}, setFinalizeProcess);
      if (!done.config) throw new Error("生成任务已完成，但没有返回冒险世界。");
      aiSettingsRef.current = done.config.story_settings;
      setLockedIds([]); // 进入 settings 阶段，confirmed 阶段的锁定 id 不再适用
      setGeneratedConfig(done.config);
      const next = buildBoardModel({ source: "settings", settings: done.config.story_settings });
      setLastDiff(diffBoard(baselineRef.current, next));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "冒险世界生成失败。");
    } finally {
      setPendingAction(null);
    }
  }

  function handleEditBlock(block: BoardBlock, fields: BoardField[]) {
    if (generatedConfig) {
      const settings = writeBlockFields(generatedConfig.story_settings, block.address, fields);
      setGeneratedConfig({ ...generatedConfig, story_settings: settings });
    } else {
      setConfirmed((cur) => writeBlockFields(cur, block.address, fields));
    }
    setLockedIds((ids) => lockBlock(ids, block.id));
  }

  function handleDeleteBlock(block: BoardBlock) {
    if (generatedConfig) {
      const settings = deleteBlock(generatedConfig.story_settings, block.address);
      setGeneratedConfig({ ...generatedConfig, story_settings: settings });
    } else {
      setConfirmed((cur) => deleteBlock(cur, block.address));
    }
    setLockedIds((ids) => unlockBlock(ids, block.id));
  }

  function handleUnlockBlock(block: BoardBlock) {
    // 恢复 AI 原值：从最近 AI 快照里按 address 取该 block 的字段值写回。
    const aiSource = generatedConfig ? aiSettingsRef.current : aiConfirmedRef.current;
    const aiModel = buildBoardModel(
      generatedConfig
        ? { source: "settings", settings: aiSource }
        : { source: "confirmed", confirmed: aiSource }
    );
    const aiBlock = aiModel.categories.flatMap((c) => c.blocks).find((b) => b.id === block.id);
    if (aiBlock) {
      handleEditBlockRaw(block, aiBlock.fields);
    }
    setLockedIds((ids) => unlockBlock(ids, block.id));
  }

  // 与 handleEditBlock 相同的写回，但不加锁（供解锁恢复用）。
  function handleEditBlockRaw(block: BoardBlock, fields: BoardField[]) {
    if (generatedConfig) {
      const settings = writeBlockFields(generatedConfig.story_settings, block.address, fields);
      setGeneratedConfig({ ...generatedConfig, story_settings: settings });
    } else {
      setConfirmed((cur) => writeBlockFields(cur, block.address, fields));
    }
  }

  async function handleCreateGenerated() {
    if (!generatedConfig) return;
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

  const canFinalize = stage === "ready_to_generate" && !generatedConfig;
  const progressItems: ProgressItem[] = BOARD_CATEGORIES.filter((c) => c.id !== "advanced").map(
    (c) => ({
      id: c.id,
      label: c.label,
      status: generatedConfig ? "done" : pendingAction === "finalize" ? "running" : "pending"
    })
  );
  const reasoning = (generatedConfig ? finalizeProcess : chatProcess)?.reasoning_content ?? "";
  const content = (generatedConfig ? finalizeProcess : chatProcess)?.content_buffer ?? "";

  return (
    <AppShell>
      <section className="game-page-hero">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Link className="app-button mb-4 w-fit" href="/games">返回存档</Link>
            <p className="game-page-eyebrow">Adventure Forge</p>
            <h1 className="game-page-title">创建冒险</h1>
          </div>
          <div className="flex gap-2">
            {canFinalize ? (
              <button
                className="app-button app-button-primary"
                disabled={pendingAction !== null}
                onClick={handleFinalize}
                type="button"
              >
                {pendingAction === "finalize" ? "生成世界中..." : "生成冒险世界"}
              </button>
            ) : null}
            {generatedConfig ? (
              <>
                <button
                  className="app-button app-button-primary"
                  disabled={pendingAction !== null}
                  onClick={handleCreateGenerated}
                  type="button"
                >
                  {pendingAction === "create-generated" ? "创建中..." : "确认并开始冒险"}
                </button>
                <button
                  className="app-button"
                  disabled={pendingAction !== null}
                  onClick={handleFinalize}
                  title="复用已确认设定重新生成一个世界"
                  type="button"
                >
                  重新生成
                </button>
              </>
            ) : null}
          </div>
        </div>
      </section>

      {error ? <section className="app-alert">{error}</section> : null}

      {pendingAction === "finalize" || (generatedConfig && content) ? (
        <GenerationProgress items={progressItems} reasoning={reasoning} content={content} />
      ) : null}

      <SettingsBoard
        model={model}
        diff={lastDiff}
        lockedIds={lockedIds}
        loading={pendingAction === "chat" || pendingAction === "finalize"}
        onEditBlock={handleEditBlock}
        onDeleteBlock={handleDeleteBlock}
        onUnlockBlock={handleUnlockBlock}
      />

      <ChatDock
        latestReply={history.length ? history[history.length - 1].content : ""}
        input={chatInput}
        disabled={pendingAction !== null}
        onInput={setChatInput}
        onSend={handleChat}
        onToggleHistory={() => setHistoryOpen((v) => !v)}
      />
      <ChatHistorySheet open={historyOpen} history={history} onClose={() => setHistoryOpen(false)} />
    </AppShell>
  );
}
