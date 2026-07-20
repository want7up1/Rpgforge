"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  FormEvent,
  type SyntheticEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import { AppShell } from "@/components/AppShell";
import { CharacterModal } from "@/components/CharacterModal";
import { CharacterPortrait } from "@/components/CharacterPortrait";
import { StoryMarkdown } from "@/components/StoryMarkdown";
import {
  buildCharacterRuntimeView,
  findCharacterByName,
  inferPresentCharacterNames,
  normalizeCharacterName,
  uniqueCharacterNames
} from "@/lib/characters";
import { buildTurnSettlement, type TurnSettlementView } from "@/lib/gameExperience";
import {
  createTurnJob,
  fetchTurnInsights,
  getActiveTurnJob,
  getCharacters,
  getGame,
  getTurns,
  rewindTurns,
  type TurnInsights
} from "@/lib/api";
import { getStateV2FromGame, type StateV2 } from "@/lib/stateV2";
import {
  createInitialTurnProcess,
  formatMaintenanceStage,
  formatLastEvent,
  isTurnBackgroundMaintenanceActive,
  isTurnMaintenanceActive,
  waitForTurnMaintenance,
  waitForTurnJobWithStream,
  type StoryProcessJob
} from "@/lib/turnJobStream";
import type {
  ActionOption,
  CharacterRead,
  GameDetail,
  TurnJobRead,
  TurnRead
} from "@/lib/types";

type ActionMode = "action" | "say" | "story" | "continue";

const ONBOARDING_KEY = "rpgforge.onboarding.play.v1";

// 四种输入模式的说明，引导卡与模式按钮 tooltip 共用，保证文案一致。
const MODE_GUIDE: { key: ActionMode; label: string; hint: string }[] = [
  { key: "action", label: "行动", hint: "做一件事。例：我撬开抽屉翻找钥匙。" },
  { key: "say", label: "对话", hint: "说一句话。例：我问她，出口在哪？" },
  { key: "story", label: "叙述", hint: "推动镜头/旁白方向。例：镜头转向门外的脚步声。" },
  { key: "continue", label: "继续", hint: "留空直接发送，让 GM 顺势推进剧情。" }
];

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
  const [actionMode, setActionMode] = useState<ActionMode>("action");
  const [customActionOpen, setCustomActionOpen] = useState(false);
  const [selectedCharacter, setSelectedCharacter] = useState<CharacterRead | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [journalOpen, setJournalOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  // C3 首次引导卡：仅首次进 play 页弹一次，localStorage 记忆后不再打扰。
  useEffect(() => {
    try {
      if (!window.localStorage.getItem(ONBOARDING_KEY)) {
        setShowOnboarding(true);
      }
    } catch {
      // localStorage 不可用（隐私模式等）时静默跳过，不阻断游戏。
    }
  }, []);

  const dismissOnboarding = useCallback(() => {
    setShowOnboarding(false);
    try {
      window.localStorage.setItem(ONBOARDING_KEY, "1");
    } catch {
      // 写入失败可接受，最多下次再弹一次。
    }
  }, []);

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
  const maintenanceActive = isTurnMaintenanceActive(turnProcess);
  const backgroundMaintenanceActive = isTurnBackgroundMaintenanceActive(turnProcess);
  // B1 结局闭环 + A3 失败出口：completed=通关、defeated=危机归零败局，均切结局视图并停用输入框。
  const gameStatus = state.status === "ready" ? state.game.status : "";
  const isCompleted = gameStatus === "completed";
  const isDefeated = gameStatus === "defeated";
  const isEnded = isCompleted || isDefeated;

  // C6 后悔药：回退到指定回合（删除其后回合并重建状态），刷新游戏与回合列表。
  const handleRewind = useCallback(
    async (toTurn: number) => {
      if (pending || maintenanceActive) {
        return;
      }
      if (!window.confirm(`确定回退到第 ${toTurn} 回合？其后的剧情将被删除，无法恢复。`)) {
        return;
      }
      setError(null);
      setPending(true);
      try {
        await rewindTurns(params.id, toTurn);
        const [refreshedGame, refreshedTurns] = await Promise.all([
          getGame(params.id),
          getTurns(params.id)
        ]);
        setState((current) =>
          current.status === "ready"
            ? { ...current, game: refreshedGame, turns: refreshedTurns }
            : current
        );
        setTurnProcess(null);
        setTurnProgress(null);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "回退失败。");
      } finally {
        setPending(false);
      }
    },
    [params.id, pending, maintenanceActive]
  );

  useEffect(() => {
    document.documentElement.classList.add("gameplay-scroll-lock");
    document.body.classList.add("gameplay-scroll-lock");
    window.scrollTo(0, 0);

    return () => {
      document.documentElement.classList.remove("gameplay-scroll-lock");
      document.body.classList.remove("gameplay-scroll-lock");
    };
  }, []);

  const refreshAfterTurnJob = useCallback(async (gameId: string, completedJob: TurnJobRead) => {
    const turn = completedJob.turn;
    if (!turn) {
      throw new Error("回合任务已完成，但没有返回回合内容。");
    }

    try {
      const [refreshedGame, refreshedTurns] = await Promise.all([
        getGame(gameId),
        getTurns(gameId)
      ]);
      setState((current) =>
        current.status === "ready"
          ? { ...current, game: refreshedGame, turns: refreshedTurns }
          : current
      );
    } catch {
      setState((current) => {
        if (current.status !== "ready") {
          return current;
        }
        const exists = current.turns.some((item) => item.id === turn.id);
        return {
          ...current,
          turns: exists ? current.turns : [...current.turns, turn]
        };
      });
    }
  }, []);

  const monitorTurnMaintenance = useCallback(async (job: TurnJobRead) => {
    setTurnProcess(job);
    setTurnProgress(job.maintenance_message || "上一回合状态维护中，请稍候...");
    try {
      const settledJob = await waitForTurnMaintenance(
        params.id,
        job.id,
        setTurnProgress,
        setTurnProcess
      );
      await refreshAfterTurnJob(params.id, settledJob);
      setTurnProgress(settledJob.maintenance_message || "状态维护已完成。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "状态维护恢复失败。");
      setTurnProgress("状态维护恢复失败，请刷新页面确认任务状态。");
      setTurnProcess((current) =>
        current?.id === job.id
          ? {
              ...current,
              maintenance_status: "failed",
              maintenance_message: "状态提取等待超时，已解除操作锁。",
              maintenance_error: caught instanceof Error ? caught.message : "状态维护恢复失败。"
            }
          : current
      );
    }
  }, [params.id, refreshAfterTurnJob]);

  const restoreActiveTurnJob = useCallback(async (activeJob: TurnJobRead) => {
    setError(null);
    if (isTurnMaintenanceActive(activeJob)) {
      void monitorTurnMaintenance(activeJob);
      return;
    }
    setPending(true);
    setTurnProcess(activeJob);
    setTurnProgress(activeJob.progress_message || "检测到未完成回合任务，正在恢复实时连接...");
    try {
      const completedJob = await waitForTurnJobWithStream(
        params.id,
        activeJob.id,
        setTurnProgress,
        setTurnProcess,
        activeJob
      );
      await refreshAfterTurnJob(params.id, completedJob);
      setTurnProgress(completedJob.progress_message || "剧情生成完成。");
      if (isTurnMaintenanceActive(completedJob)) {
        void monitorTurnMaintenance(completedJob);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复回合任务失败。");
      setTurnProgress("回合恢复失败，已保留收到的过程信息。");
    } finally {
      setPending(false);
    }
  }, [monitorTurnMaintenance, params.id, refreshAfterTurnJob]);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const [game, turns, characters, activeJob] = await Promise.all([
          getGame(params.id),
          getTurns(params.id),
          getCharacters(params.id, "public"),
          getActiveTurnJob(params.id)
        ]);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game, turns, characters });
          if (activeJob) {
            void restoreActiveTurnJob(activeJob);
          }
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
  }, [params.id, restoreActiveTurnJob]);

  async function submitTurn(
    payload: Parameters<typeof createTurnJob>[1],
    options: { reopenComposerOnError?: boolean } = {}
  ) {
    if (state.status !== "ready" || pending || maintenanceActive) {
      return;
    }

    setCustomActionOpen(false);
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
      await refreshAfterTurnJob(state.game.id, completedJob);
      setInput("");
      setTurnProgress(completedJob.progress_message || "剧情生成完成。");
      if (isTurnMaintenanceActive(completedJob)) {
        void monitorTurnMaintenance(completedJob);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交回合失败。");
      setTurnProgress("回合生成失败，已保留收到的过程信息。");
      if (options.reopenComposerOnError) {
        setCustomActionOpen(true);
      }
    } finally {
      setPending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    const fallbackInput =
      actionMode === "continue" ? "继续推进当前剧情。" : "";
    const playerInput = trimmed || fallbackInput;
    if (!playerInput) {
      return;
    }
    void submitTurn(
      { player_input: playerInput },
      { reopenComposerOnError: true }
    );
  }

  return (
    <AppShell variant="gameplay">
      {state.status === "loading" ? (
        <section className="px-panel px-panel-pad m-4 text-sm text-[color:var(--muted)]">
          <span className="px-caret" aria-hidden="true" /> 正在进入冒险…
        </section>
      ) : state.status === "error" ? (
        <section className="px-alert m-4">{state.message}</section>
      ) : (
        <>
          <div className="game-screen">
            <div>
              <div className="px-topbar border-x-0 border-t-0">
                <Link href="/" className="px-brand px-font text-[0.55rem]" title="返回标题画面">
                  <span aria-hidden="true" className="text-[color:var(--amber)]">▓▓</span>
                  RPGFORGE
                </Link>
                <div className="min-w-0">
                  <h1 className="truncate text-sm font-bold">{state.game.title}</h1>
                  <p className="truncate text-xs text-[color:var(--muted)]">
                    第 {latestTurn?.turn_number ?? 0} 回合
                    {stateV2?.active_scene.location
                      ? ` · ${stateV2.active_scene.location}`
                      : ""}
                    {stateV2?.active_scene.time ? ` · ${stateV2.active_scene.time}` : ""}
                  </p>
                </div>
                <div className="ml-auto flex items-center gap-1.5">
                  {latestTurn && latestTurn.turn_number > 0 ? (
                    <button
                      className="px-btn min-h-8 px-2 py-1 text-xs"
                      disabled={pending || maintenanceActive}
                      onClick={() => handleRewind(latestTurn.turn_number - 1)}
                      title="删除最新一回合，回到上一回合重新选择"
                      type="button"
                    >
                      ↩ 撤销
                    </button>
                  ) : null}
                  <button
                    aria-expanded={journalOpen}
                    className="px-btn min-h-8 px-2 py-1 text-xs"
                    onClick={() => { setJournalOpen((v) => !v); setMenuOpen(false); }}
                    type="button"
                  >
                    ▤ 手账
                  </button>
                  <button
                    aria-expanded={menuOpen}
                    className="px-btn min-h-8 px-2 py-1 text-xs"
                    onClick={() => { setMenuOpen((v) => !v); setJournalOpen(false); }}
                    type="button"
                  >
                    ▦ 菜单
                  </button>
                </div>
              </div>
              {menuOpen ? (
                <div className="border-b-2 border-[color:var(--border)] bg-[rgba(5,12,7,0.96)] px-2 py-2">
                  <GameMenuInline gameId={params.id} />
                </div>
              ) : null}
            </div>

            <section className="game-scroll">
              <div className="game-scroll-column">
                {error ? <div className="px-alert mb-4">{error}</div> : null}
                {isEnded && stateV2 ? (
                  <CampaignEndingCard
                    gameId={params.id}
                    outcome={isDefeated ? "defeat" : "victory"}
                    stateV2={stateV2}
                  />
                ) : null}
                {!isEnded && stateV2 ? <ObjectiveBanner stateV2={stateV2} /> : null}
                {stateV2 ? (
                  <PresentCharactersStrip
                    characters={state.characters}
                    latestTurn={latestTurn}
                    onCharacterClick={setSelectedCharacter}
                    stateV2={stateV2}
                  />
                ) : null}
                <StoryPanel
                  characters={state.characters}
                  latestTurn={latestTurn}
                  onCharacterClick={setSelectedCharacter}
                  onSelectAction={(option) => submitTurn({ selected_option: option })}
                  pending={pending}
                  process={turnProcess}
                  progress={turnProgress}
                  maintenanceActive={maintenanceActive}
                  backgroundMaintenanceActive={backgroundMaintenanceActive}
                />
              </div>
            </section>

            {isEnded ? (
              <footer className="command-bar">
                <p className="mx-auto w-full max-w-[840px] text-sm text-[color:var(--muted)]">
                  {isDefeated
                    ? "主角已倒下，这段旅程到此终结。可在上方开启新的冒险。"
                    : "本场冒险已抵达结局，旅程到此圆满。可在上方开启新的冒险。"}
                </p>
              </footer>
            ) : (
              <AdventureComposer
                actionMode={actionMode}
                disabled={pending || maintenanceActive}
                expanded={customActionOpen}
                input={input}
                maintenanceActive={maintenanceActive}
                onInputChange={setInput}
                onModeChange={setActionMode}
                onExpandedChange={setCustomActionOpen}
                onSubmit={handleSubmit}
                pending={pending}
              />
            )}
          </div>

          {journalOpen ? (
            <>
              <button
                aria-label="关闭冒险手账"
                className="journal-overlay"
                onClick={() => setJournalOpen(false)}
                type="button"
              />
              <JournalDrawer
                characters={state.characters}
                game={state.game}
                onClose={() => setJournalOpen(false)}
                stateV2={stateV2}
              />
            </>
          ) : null}

          <CharacterModal
            character={selectedCharacter}
            onClose={() => setSelectedCharacter(null)}
            runtimeView={
              selectedCharacter ? buildCharacterRuntimeView(selectedCharacter, stateV2) : null
            }
          />
          {showOnboarding ? <OnboardingCard onDismiss={dismissOnboarding} /> : null}
        </>
      )}
    </AppShell>
  );
}

function GameMenuInline({ gameId }: { gameId: string }) {
  const items = [
    { label: "状态", en: "STATUS", href: `/games/${gameId}/status` },
    { label: "角色", en: "PARTY", href: `/games/${gameId}/characters` },
    { label: "旅程", en: "LOG", href: `/games/${gameId}/history` },
    { label: "记忆", en: "MEMO", href: `/games/${gameId}/memory` },
    { label: "设定", en: "SCRIPT", href: `/games/${gameId}/settings` },
    { label: "营地", en: "CAMP", href: `/games/${gameId}/camp` },
    { label: "离开", en: "EXIT", href: "/games" }
  ];
  return (
    <nav aria-label="游戏菜单" className="px-menu justify-center">
      {items.map((item) => (
        <Link className="px-menu-link" href={item.href} key={item.en}>
          <span>{item.label}</span>
          <span className="px-menu-en">{item.en}</span>
        </Link>
      ))}
    </nav>
  );
}

function JournalDrawer({
  characters,
  game,
  onClose,
  stateV2
}: {
  characters: CharacterRead[];
  game: GameDetail;
  onClose: () => void;
  stateV2: StateV2 | null;
}) {
  const visibleCharacters = characters.filter((character) => character.is_visible).slice(0, 3);

  return (
    <aside aria-label="冒险手账" className="journal-drawer">
      <div className="flex items-center justify-between gap-2 border-b-2 border-[color:var(--border)] px-3 py-2.5">
        <h2 className="px-heading text-sm">冒险手账</h2>
        <button aria-label="关闭冒险手账" className="px-btn h-8 w-8 px-0" onClick={onClose} type="button">
          ×
        </button>
      </div>
      <div className="journal-body grid content-start gap-3">
        {stateV2 ? <PlayStateStrip gameId={game.id} stateV2={stateV2} /> : null}

        <section className="px-card">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="px-label">角色</h3>
            <Link className="text-xs text-[color:var(--phosphor)]" href={`/games/${game.id}/characters`}>
              全部 ▸
            </Link>
          </div>
          <div className="grid gap-3">
            {visibleCharacters.length > 0 ? (
              visibleCharacters.map((character) => (
                <div className="grid grid-cols-[3rem_minmax(0,1fr)] items-center gap-3" key={character.id}>
                  <CharacterPortrait character={character} />
                  <div className="min-w-0">
                    <strong className="block truncate">{character.name}</strong>
                    <p className="truncate text-xs text-[color:var(--muted)]">
                      {character.identity || character.description || "角色档案"}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-[color:var(--muted)]">暂无可见角色。</p>
            )}
          </div>
        </section>

        <section className="px-card">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="px-label">剧本素材</h3>
            <Link className="text-xs text-[color:var(--phosphor)]" href={`/games/${game.id}/memory`}>
              记忆 ▸
            </Link>
          </div>
          <div className="flex flex-wrap gap-2">
            {storyMaterialTitles(game).map((title) => (
              <span className="px-badge" key={title}>
                {title}
              </span>
            ))}
          </div>
        </section>

        <section className="px-card">
          <h3 className="px-label">旅程记忆</h3>
          <p className="px-wrap mt-2 line-clamp-5 text-sm leading-6 text-[color:var(--muted)]">
            {game.summaries[0]?.content || game.description || "暂无记忆摘要。"}
          </p>
        </section>
      </div>
    </aside>
  );
}

function PlayStateStrip({ gameId, stateV2 }: { gameId: string; stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;
  const scene = stateV2.active_scene;
  const conditionLabel =
    stateV2.conditions.length > 0 ? `${stateV2.conditions.length} 个状态` : "状态稳定";

  return (
    <section className="px-card px-card-green">
      <div className="grid gap-2">
        <div className="min-w-0">
          <div className="font-bold text-[color:var(--phosphor)]">
            {protagonist.name || "主角"}
          </div>
          {protagonist.identity ? (
            <p className="mt-1 text-xs leading-5 text-[color:var(--muted)]">
              {protagonist.identity}
            </p>
          ) : null}
          <p className="mt-1.5 text-xs text-[color:var(--muted)]">
            {scene.location || "未知地点"} · {conditionLabel}
          </p>
        </div>
        <Link className="px-btn w-full" href={`/games/${gameId}/status`}>
          查看状态 STATUS ▸
        </Link>
      </div>
    </section>
  );
}

// B1 结局闭环 + A3 失败出口：抵达结局后展示卡片——结局正文 + 旅程回顾 + 开新档入口。
function CampaignEndingCard({
  gameId,
  outcome,
  stateV2
}: {
  gameId: string;
  outcome: "victory" | "defeat";
  stateV2: StateV2;
}) {
  const epilogue = stateV2.story_progress.epilogue;
  const completedActs = stateV2.story_progress.completed_acts.length;
  const isDefeat = outcome === "defeat";
  const badge = isDefeat ? "GAME OVER" : "THE END";
  const summary = isDefeat
    ? "你的旅程在此折戟"
    : `你走完了这段冒险${completedActs > 0 ? ` · 共 ${completedActs} 幕` : ""}`;
  const fallbackText = isDefeat
    ? "主角终究没能撑到最后。这段旅程以失败收场。"
    : "故事在此落幕。你的抉择把这段旅程带到了终点。";

  return (
    <section
      className={`ending-screen mb-5${isDefeat ? " ending-screen-defeat" : ""}`}
      aria-label={isDefeat ? "败局" : "剧终"}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="ending-badge">{badge}</span>
        <span className="text-sm text-[color:var(--muted)]">{summary}</span>
      </div>
      {epilogue ? (
        <div className="mt-4">
          <StoryMarkdown content={epilogue} />
        </div>
      ) : (
        <p className="mt-3 text-sm leading-7 text-[color:var(--muted)]">{fallbackText}</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link className="px-btn px-btn-primary" href="/games/new">
          ▸ 开启新冒险
        </Link>
        <Link className="px-btn" href={`/games/${gameId}/history`}>
          回顾旅程
        </Link>
        <Link className="px-btn" href="/games">
          所有存档
        </Link>
      </div>
    </section>
  );
}

// C3 首次引导卡：一次性解释四种输入模式 +「你可以尝试任何行动」，降低上手门槛。
function OnboardingCard({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="px-modal-overlay" role="dialog" aria-modal="true" aria-label="新手引导">
      <div className="px-modal max-w-md">
        <p className="px-eyebrow">HOW TO PLAY</p>
        <h2 className="px-heading mt-2 text-xl">开始你的冒险</h2>
        <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
          这是一场由 AI 主持的文字 RPG。<strong className="text-[color:var(--foreground)]">你可以尝试任何行动</strong>
          ——直接在命令行里写下你想做的事，GM 会据此推进剧情。下方四种输入模式只是帮你表达意图：
        </p>
        <ul className="mt-3 grid gap-2">
          {MODE_GUIDE.map((mode) => (
            <li className="grid grid-cols-[3.2rem_minmax(0,1fr)] items-baseline gap-2 text-sm leading-6" key={mode.key}>
              <span className="font-bold text-[color:var(--amber)]">{mode.label}</span>
              <span className="px-wrap text-[color:var(--muted)]">{mode.hint}</span>
            </li>
          ))}
        </ul>
        <button className="px-btn px-btn-primary mt-4 w-full" onClick={onDismiss} type="button">
          ▸ 知道了，开始冒险
        </button>
      </div>
    </div>
  );
}

// C2 目标横幅：游玩主界面固定展示「当前幕目标 + 本幕进度 + 进行中任务/未解线索」，
// 数据全部取自 stateV2（current_act_objective 由后端 story_progress 派生）。
function ObjectiveBanner({ stateV2 }: { stateV2: StateV2 }) {
  const progress = stateV2.story_progress;
  const objective = progress.current_act_objective;
  const actTitle = progress.current_act_title;
  const anchor = progress.current_act_anchor_progress;
  const activeQuests = stateV2.quest_log.active.slice(0, 2);
  const openThread = stateV2.open_threads.active[0];

  // 目标/任务/线索全空时不渲染（如开局第 0 回合尚未生成幕信息），避免空卡片。
  if (!objective && !actTitle && activeQuests.length === 0 && !openThread) {
    return null;
  }

  return (
    <section className="quest-banner" aria-label="当前目标">
      <div className="flex flex-wrap items-center gap-2">
        <span className="story-label">⚑ 当前目标</span>
        {actTitle ? <span className="px-badge px-badge-amber">{actTitle}</span> : null}
        {anchor.total > 0 ? (
          <span className="ml-auto text-xs text-[color:var(--muted)]">
            本幕 {anchor.done}/{anchor.total}
          </span>
        ) : null}
      </div>
      {objective ? (
        <p className="px-wrap mt-1.5 text-[0.95rem] font-semibold leading-7">{objective}</p>
      ) : null}
      {activeQuests.length > 0 || openThread ? (
        <ul className="mt-2 grid gap-1 text-sm text-[color:var(--muted)]">
          {activeQuests.map((quest) => (
            <li className="flex items-baseline gap-2" key={quest.name}>
              <span className="flex-none text-xs font-bold text-[color:var(--amber)]">任务</span>
              <span className="px-wrap">{quest.objective || quest.name}</span>
            </li>
          ))}
          {openThread ? (
            <li className="flex items-baseline gap-2" key={openThread.title}>
              <span className="flex-none text-xs font-bold text-[color:var(--phosphor)]">线索</span>
              <span className="px-wrap">{openThread.title}</span>
            </li>
          ) : null}
        </ul>
      ) : null}
    </section>
  );
}

function PresentCharactersStrip({
  characters,
  latestTurn,
  onCharacterClick,
  stateV2
}: {
  characters: CharacterRead[];
  latestTurn: TurnRead | null;
  onCharacterClick: (character: CharacterRead) => void;
  stateV2: StateV2;
}) {
  const narrative = [latestTurn?.player_input, latestTurn?.gm_output].filter(Boolean).join("\n");
  const sourceNames = uniqueCharacterNames([
    ...stateV2.active_scene.present_npcs,
    ...inferPresentCharacterNames(characters, stateV2, narrative)
  ]);
  const present = sourceNames
    .map((name) => {
      const character = findCharacterByName(characters, name);
      const npcState = stateV2.npc_registry.find(
        (npc) => normalizeCharacterName(npc.name) === normalizeCharacterName(name)
      );
      return {
        character,
        identity: character?.identity || npcState?.identity || character?.description || "在场角色",
        name: character?.name || npcState?.name || name,
        status: npcState?.status || npcState?.relationship || npcState?.attitude || ""
      };
    })
    .filter((entry, index, list) =>
      Boolean(entry.name) &&
      list.findIndex(
        (item) => normalizeCharacterName(item.name) === normalizeCharacterName(entry.name)
      ) === index
    );

  if (present.length === 0) {
    return null;
  }

  return (
    <section className="mb-4 border-2 border-[#8a6420] bg-[color:var(--panel)] p-3" aria-label="当前在场角色">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="story-label">在场者</span>
        <span className="px-badge">{present.length}</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {present.map((entry) => (
          <button
            className="present-chip"
            disabled={!entry.character}
            key={entry.name}
            onClick={() => {
              if (entry.character) {
                onCharacterClick(entry.character);
              }
            }}
            type="button"
          >
            {entry.character ? (
              <CharacterPortrait character={entry.character} />
            ) : (
              <span className="grid h-10 w-10 place-items-center border-2 border-[#8a6420] bg-[rgba(255,179,71,0.1)] font-black text-[color:var(--amber)]">
                {entry.name.slice(0, 1)}
              </span>
            )}
            <span className="min-w-0">
              <strong className="block truncate text-sm">{entry.name}</strong>
              <span className="block truncate text-xs text-[color:var(--muted)]">
                {[entry.identity, entry.status].filter(Boolean).join(" · ")}
              </span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function AdventureComposer({
  actionMode,
  disabled,
  expanded,
  input,
  maintenanceActive,
  onExpandedChange,
  onInputChange,
  onModeChange,
  onSubmit,
  pending
}: {
  actionMode: ActionMode;
  disabled: boolean;
  expanded: boolean;
  input: string;
  maintenanceActive: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onInputChange: (value: string) => void;
  onModeChange: (mode: ActionMode) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pending: boolean;
}) {
  const modeOptions = MODE_GUIDE;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  let submitLabel = "发送";
  if (pending) {
    submitLabel = "发送中...";
  } else if (maintenanceActive) {
    submitLabel = "整理中...";
  } else if (actionMode === "continue") {
    submitLabel = "继续";
  }

  useEffect(() => {
    if (!expanded) {
      return;
    }
    const frame = window.requestAnimationFrame(() => textareaRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [expanded]);

  if (!expanded) {
    return (
      <footer className="command-bar">
        <div className="mx-auto flex w-full max-w-[840px] justify-end">
          <button
            aria-expanded="false"
            className="px-btn px-btn-primary min-h-9"
            disabled={disabled}
            onClick={() => onExpandedChange(true)}
            type="button"
          >
            ＋ 自定义行动
          </button>
        </div>
      </footer>
    );
  }

  return (
    <footer className="command-bar">
      <form className="mx-auto grid w-full max-w-[840px] gap-2" onSubmit={onSubmit}>
        <div className="flex flex-wrap items-center gap-2">
          <div className="mode-switch" aria-label="输入模式">
            {modeOptions.map((mode) => (
              <button
                className={actionMode === mode.key ? "mode-active" : undefined}
                key={mode.key}
                onClick={() => onModeChange(mode.key)}
                title={mode.hint}
                type="button"
              >
                {mode.label}
              </button>
            ))}
          </div>
          <span className="hidden text-xs text-[color:var(--faint)] sm:inline">
            {modeOptions.find((m) => m.key === actionMode)?.hint}
          </span>
          <button
            aria-expanded="true"
            className="px-btn ml-auto min-h-8 px-2 py-1 text-xs"
            onClick={() => onExpandedChange(false)}
            type="button"
          >
            − 收起
          </button>
        </div>

        <div className="flex items-start gap-2 border-2 border-[color:var(--border-strong)] bg-[color:var(--input)] px-3 py-2 shadow-[inset_2px_2px_0_0_rgba(0,0,0,0.45)] focus-within:border-[color:var(--phosphor)]">
          <span aria-hidden="true" className="command-prompt mt-0.5">&gt;</span>
          <label className="sr-only" htmlFor="free-action-input">
            自由行动
          </label>
          <textarea
            className="command-input"
            disabled={disabled}
            id="free-action-input"
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={placeholderForMode(actionMode)}
            ref={textareaRef}
            rows={2}
            value={input}
          />
          <button
            className="px-btn px-btn-primary min-h-9 self-end"
            disabled={disabled || (actionMode !== "continue" && !input.trim())}
            type="submit"
          >
            {submitLabel} ▸
          </button>
        </div>
      </form>
    </footer>
  );
}

function placeholderForMode(mode: ActionMode): string {
  if (mode === "say") {
    return "输入角色说的话。例：我对角色F说，跟紧我。";
  }
  if (mode === "story") {
    return "输入你希望推动的叙述方向。例：镜头转向地下冷库门后。";
  }
  if (mode === "continue") {
    return "留空发送，直接让 GM 继续推进当前剧情。";
  }
  return "输入你的行动。例：我带角色F从污物电梯井潜入药房。";
}

function StoryPanel({
  backgroundMaintenanceActive,
  characters,
  latestTurn,
  maintenanceActive,
  onCharacterClick,
  onSelectAction,
  pending,
  process,
  progress
}: {
  backgroundMaintenanceActive: boolean;
  characters: CharacterRead[];
  latestTurn: TurnRead | null;
  maintenanceActive: boolean;
  onCharacterClick: (character: CharacterRead) => void;
  onSelectAction: (option: ActionOption) => void;
  pending: boolean;
  process: StoryProcessJob | null;
  progress: string | null;
}) {
  const reasoning = process?.reasoning_content || "";
  const liveNarrative = process?.narrative_buffer || "";
  const displayedNarrative = pending ? liveNarrative : liveNarrative || latestTurn?.gm_output;
  const hasLiveProcess =
    process !== null && (pending || maintenanceActive || process.status === "failed");
  const actionOptions = pending ? [] : latestTurn?.action_options_json ?? [];
  const settlement = useMemo(
    () => (latestTurn ? buildTurnSettlement(latestTurn) : null),
    [latestTurn]
  );

  return (
    <div className="grid gap-4">
      {latestTurn && !pending && latestTurn.turn_number > 0 ? (
        <article className="scroll-block scroll-block-player">
          <div className="story-label">你 · 第 {latestTurn.turn_number} 回合</div>
          <p className="px-wrap mt-1 whitespace-pre-wrap text-base leading-8">&gt; {latestTurn.player_input}</p>
        </article>
      ) : null}

      {hasLiveProcess ? (
        <article className="scroll-block">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="story-label">
              {maintenanceActive ? "后台维护 · 状态提取" : "DeepSeek Pro · 剧情生成"}
            </div>
            <span className="px-badge px-badge-bright">{process.status}</span>
          </div>
          <div className="px-status text-xs">
            {maintenanceActive ? (
              <MaintenanceStageProgress process={process} />
            ) : (
              <TurnStageProgress process={process} />
            )}
            <div className="mt-2">{progress || process.progress_message || "等待 DeepSeek 返回剧情。"}</div>
            <div className="mt-1">
              最近更新：{formatLastEvent(process.last_event_at)} · 思考 {reasoning.length} 字 ·
              剧情 {liveNarrative.length} 字
              {process.model_used ? ` · ${process.model_used}` : ""}
            </div>
          </div>
          <GenerationDetails
            maintenanceActive={maintenanceActive}
            narrativeLength={liveNarrative.length}
            process={process}
            reasoningLength={reasoning.length}
          />
          <details className="px-fold mt-3">
            <summary>思考过程</summary>
            <pre className="px-wrap max-h-56 overflow-auto whitespace-pre-wrap border-t-2 border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
              {reasoning || "尚未收到思考过程。"}
            </pre>
          </details>
        </article>
      ) : null}

      <article className="scroll-block">
        <div className="story-label">
          GM ·{" "}
          {pending
            ? "实时书写"
            : latestTurn
              ? latestTurn.turn_number > 0
                ? `第 ${latestTurn.turn_number} 回合`
                : "序章"
              : "等待开始"}
        </div>
        {displayedNarrative ? (
          <StoryMarkdown
            characters={characters}
            className="mt-3"
            content={displayedNarrative}
            onCharacterClick={onCharacterClick}
            showCaret={pending && Boolean(liveNarrative)}
          />
        ) : (
          <p className="mt-4 text-sm leading-6 text-[color:var(--muted)]">
            {pending ? "正在等待剧情正文..." : "还没有回合。输入行动开始第一回合。"}
          </p>
        )}
      </article>

      {!pending && settlement && latestTurn && latestTurn.turn_number > 0 ? (
        <TurnSettlementCard settlement={settlement} />
      ) : null}

      {!pending && latestTurn && latestTurn.turn_number > 0 ? (
        <TurnInsightsPanel gameId={latestTurn.game_id} turnId={latestTurn.id} />
      ) : null}

      {maintenanceActive ? (
        <section className="px-status">
          <strong className="block text-[color:var(--foreground)]">上一回合状态提取中</strong>
          <span className="mt-1 block">
            {process?.maintenance_message || "正在整理状态变更，完成后才能继续下一回合。"}
          </span>
        </section>
      ) : null}

      {backgroundMaintenanceActive ? (
        <section className="px-status">
          <strong className="block text-[color:var(--foreground)]">记忆摘要后台维护中</strong>
          <span className="mt-1 block">
            {process?.maintenance_message || "正在更新长期记忆，不影响继续行动。"}
          </span>
        </section>
      ) : null}

      {actionOptions.length > 0 ? (
        <section className="scroll-block">
          <div className="story-label">抉择</div>
          <div className="choice-grid">
            {actionOptions.map((option) => (
              <button
                aria-label={`选择建议行动 ${option.key}：${option.label}`}
                className="choice-card"
                disabled={pending || maintenanceActive}
                key={option.key}
                onClick={() => onSelectAction(option)}
                type="button"
              >
                <span className="choice-key">{option.key}</span>
                <span className="choice-copy">{option.label}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function TurnSettlementCard({ settlement }: { settlement: TurnSettlementView }) {
  return (
    <article className="px-card px-card-green">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="story-label">战报 · 本回合变化</div>
          <h3 className="mt-1 font-black">结算摘要</h3>
        </div>
        <span className="px-badge">
          {settlement.hasChanges ? `${settlement.sections.length} 类变化` : "暂无结构化结算"}
        </span>
      </div>

      <ul className="mt-3 grid gap-1.5 pl-4 text-sm leading-6">
        {(settlement.summary.length > 0
          ? settlement.summary
          : ["本回合暂无可结构化结算。"]).map((item) => (
          <li className="px-wrap list-disc" key={item}>{item}</li>
        ))}
      </ul>

      {settlement.hasChanges ? (
        <details className="px-fold mt-3">
          <summary>查看详细变更</summary>
          <div className="grid gap-2 border-t-2 border-[color:var(--border)] pt-3 sm:grid-cols-2">
            {settlement.sections.map((section) => (
              <section className="px-card" key={section.key}>
                <h4 className="text-sm font-bold text-[color:var(--amber)]">{section.label}</h4>
                <ul className="mt-2 grid gap-1 pl-4 text-xs leading-5 text-[color:var(--muted)]">
                  {section.items.map((item) => (
                    <li className="px-wrap list-disc" key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}

function TurnInsightsPanel({ gameId, turnId }: { gameId: string; turnId: string }) {
  const [data, setData] = useState<TurnInsights | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // 折叠面板展开时才按需拉取，避免每回合都请求。
  const handleToggle = useCallback(
    (event: SyntheticEvent<HTMLDetailsElement>) => {
      if (!event.currentTarget.open || loaded || loading) return;
      setLoading(true);
      setError(null);
      fetchTurnInsights(gameId, turnId)
        .then((result) => {
          setData(result);
          setLoaded(true);
        })
        .catch(() => setError("加载本回合详情失败。"))
        .finally(() => setLoading(false));
    },
    [gameId, turnId, loaded, loading]
  );

  const obs = data?.observation as
    | { generation?: Record<string, number | boolean>; flags?: string[];
        canon?: { used?: number; total?: number } }
    | undefined;
  const gen = obs?.generation;
  const flags = obs?.flags ?? [];
  const hitRate =
    data?.cache_hit_rate != null ? `${Math.round(data.cache_hit_rate * 100)}%` : "—";

  return (
    <details className="px-fold" onToggle={handleToggle}>
      <summary>本回合详情 · 成本与质量</summary>
      <div className="px-fold-body">
        {loading ? (
          <p className="text-sm text-[color:var(--muted)]">加载中…</p>
        ) : error ? (
          <p className="text-sm text-[color:var(--muted)]">{error}</p>
        ) : data ? (
          <dl className="detail-grid">
            <div>
              <dt>本回合 token</dt>
              <dd>
                输入 {data.total_tokens_input} · 输出 {data.total_tokens_output}
              </dd>
            </div>
            <div>
              <dt>缓存命中率</dt>
              <dd>
                {hitRate}（命中 {data.total_cache_hit_tokens} / 未命中{" "}
                {data.total_cache_miss_tokens}）
              </dd>
            </div>
            {gen ? (
              <div>
                <dt>篇幅</dt>
                <dd>
                  {gen.narrative_chars} 字 · {gen.paragraph_count} 段
                </dd>
              </div>
            ) : null}
            {obs?.canon ? (
              <div>
                <dt>canon 使用</dt>
                <dd>
                  {obs.canon.used ?? 0}/{obs.canon.total ?? 0} 个专名
                </dd>
              </div>
            ) : null}
            <div>
              <dt>各 agent token</dt>
              <dd>
                {data.agents.length === 0
                  ? "—"
                  : data.agents
                      .map((a) => `${a.agent} ${a.tokens_input ?? "?"}`)
                      .join(" · ")}
              </dd>
            </div>
            <div>
              <dt>质量观测</dt>
              <dd>{flags.length === 0 ? "无异常" : flags.join("；")}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-[color:var(--muted)]">展开加载本回合 token / 缓存 / 质量观测。</p>
        )}
      </div>
    </details>
  );
}

function GenerationDetails({
  maintenanceActive,
  narrativeLength,
  process,
  reasoningLength
}: {
  maintenanceActive: boolean;
  narrativeLength: number;
  process: StoryProcessJob;
  reasoningLength: number;
}) {
  return (
    <details className="px-fold mt-3">
      <summary>生成详情</summary>
      <dl className="detail-grid border-t-2 border-[color:var(--border)] pt-3">
        <div>
          <dt>当前阶段</dt>
          <dd>
            {process.stage_label || process.stage || "准备中"} · {process.stage_index || 1}/
            {process.stage_total || 1}
          </dd>
        </div>
        <div>
          <dt>阶段开始</dt>
          <dd>{formatDateTime(process.stage_started_at)}</dd>
        </div>
        <div>
          <dt>最近更新</dt>
          <dd>{formatDateTime(process.last_event_at)}</dd>
        </div>
        <div>
          <dt>当前模型</dt>
          <dd>{process.model_used || "等待模型返回"}</dd>
        </div>
        <div>
          <dt>SSE 状态</dt>
          <dd>{formatStreamStatus(process)}</dd>
        </div>
        <div>
          <dt>已接收</dt>
          <dd>
            思考 {reasoningLength} 字 · 剧情 {narrativeLength} 字
          </dd>
        </div>
        <div>
          <dt>状态维护</dt>
          <dd>
            {formatMaintenanceStage(process.maintenance_stage)} ·{" "}
            {formatMaintenanceStatus(process)}
            {maintenanceActive ? " · 阻止下一回合" : ""}
          </dd>
        </div>
        <div>
          <dt>维护信息</dt>
          <dd>{process.maintenance_message || process.maintenance_error || "暂无"}</dd>
        </div>
      </dl>
    </details>
  );
}

function TurnStageProgress({ process }: { process: StoryProcessJob }) {
  const [now, setNow] = useState(() => Date.now());
  const stageTotal = Math.max(process.stage_total || 6, 1);
  const stageIndex = Math.min(Math.max(process.stage_index || 1, 1), stageTotal);
  const stagePercent = Math.min(100, Math.max(6, (stageIndex / stageTotal) * 100));
  const stageLabel = process.stage_label || "准备上下文";
  const isActive = process.status === "pending" || process.status === "running";

  useEffect(() => {
    if (!isActive) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isActive, process.stage_started_at]);

  return (
    <div className="px-progress">
      <div className="flex flex-wrap justify-between gap-2 text-xs font-bold text-[color:var(--foreground)]">
        <span>
          {stageIndex}/{stageTotal} · {stageLabel}
        </span>
        <span>{formatStageElapsed(process.stage_started_at, now)}</span>
      </div>
      <div
        aria-label={`回合生成进度：${stageLabel}`}
        aria-valuemax={stageTotal}
        aria-valuemin={1}
        aria-valuenow={stageIndex}
        className="px-progress-track"
        role="progressbar"
      >
        <div
          className="px-progress-fill"
          style={{ width: `${stagePercent}%` }}
        />
      </div>
    </div>
  );
}

function MaintenanceStageProgress({ process }: { process: StoryProcessJob }) {
  const [now, setNow] = useState(() => Date.now());
  const stageLabel = formatMaintenanceStage(process.maintenance_stage);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [process.maintenance_started_at]);

  return (
    <div className="px-progress">
      <div className="flex flex-wrap justify-between gap-2 text-xs font-bold text-[color:var(--foreground)]">
        <span>{stageLabel}</span>
        <span>{formatStageElapsed(process.maintenance_started_at, now)}</span>
      </div>
      <div
        aria-label={`后台维护进度：${stageLabel}`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={65}
        className="px-progress-track"
        role="progressbar"
      >
        <div className="px-progress-fill px-progress-fill-amber" style={{ width: "65%" }} />
      </div>
    </div>
  );
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未知";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(date);
}

function formatStreamStatus(process: StoryProcessJob): string {
  if (isTurnMaintenanceActive(process)) {
    return "剧情已完成，正在轮询状态维护";
  }
  if (process.status === "completed") {
    return "已完成";
  }
  if (process.status === "failed") {
    return "已失败";
  }
  if (!process.last_event_at) {
    return "等待首个实时事件";
  }
  const lastEventAt = new Date(process.last_event_at).getTime();
  if (Number.isNaN(lastEventAt)) {
    return "状态未知";
  }
  const seconds = Math.max(0, Math.round((Date.now() - lastEventAt) / 1000));
  if (seconds <= 10) {
    return "实时接收中";
  }
  if (seconds <= 45) {
    return "等待下一段输出";
  }
  return "可能正在等待模型或已切换轮询";
}

function formatMaintenanceStatus(process: StoryProcessJob): string {
  if (process.maintenance_status === "pending") {
    return "等待中";
  }
  if (process.maintenance_status === "running") {
    return "运行中";
  }
  if (process.maintenance_status === "skipped") {
    return "已延后";
  }
  if (process.maintenance_status === "failed") {
    return "失败";
  }
  return "完成";
}

function formatStageElapsed(value: string | null, now: number): string {
  if (!value) {
    return "等待中";
  }
  const startedAt = new Date(value).getTime();
  if (Number.isNaN(startedAt)) {
    return "计时未知";
  }
  const seconds = Math.max(0, Math.round((now - startedAt) / 1000));
  if (seconds < 60) {
    return `已等待 ${seconds} 秒`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `已等待 ${minutes} 分 ${remainingSeconds} 秒`;
}

function storyMaterialTitles(game: GameDetail): string[] {
  return storyMaterials(game)
    .slice(0, 6)
    .map((item, index) => pickString(item, "title") || `素材 ${index + 1}`);
}

function storyMaterials(game: GameDetail): Record<string, unknown>[] {
  const config = game.config?.story_settings;
  const materials = asRecord(config).story_material_library;
  return Array.isArray(materials)
    ? materials.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function pickString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value.trim() : "";
}
