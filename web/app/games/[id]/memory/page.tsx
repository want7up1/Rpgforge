"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChangeEvent, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { JsonBlock } from "@/components/JsonBlock";
import { buildContractView, type ContractView } from "@/lib/gameExperience";
import {
  archiveLoreEntry,
  createLoreEntry,
  createMode,
  getContextDiagnostic,
  getGame,
  getGameMemory,
  getGameSettingsExport,
  getGameScriptExport,
  getSettingVersions,
  getTurns,
  importGameSettings,
  rebuildGameSummaries,
  reindexGameLore,
  restoreSettingVersion,
  updateGameConfig,
  updateLoreEntry,
  updateMode
} from "@/lib/api";
import { downloadBlob } from "@/lib/downloads";
import type {
  ContextDiagnosticRead,
  GameDetail,
  GameMemoryRead,
  GameSettingVersionRead,
  GenerationSettings,
  AdvancedConfigJsonDraft,
  LoreDiagnosticRead,
  LoreEntryCreate,
  LoreEntryMemoryRead,
  ModeCreate,
  ModeRead,
  SummaryRead,
  TurnRead
} from "@/lib/types";

type MemoryTab = "core" | "settings" | "versions";

type LoadState =
  | { status: "loading" }
  | {
      status: "ready";
      game: GameDetail;
      memory: GameMemoryRead;
      versions: GameSettingVersionRead[];
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
        const [memory, turns, game, versions] = await Promise.all([
          getGameMemory(params.id),
          getTurns(params.id),
          getGame(params.id),
          getSettingVersions(params.id)
        ]);
        const latestTurn = turns[turns.length - 1];
        const diagnostic = latestTurn
          ? await getContextDiagnostic(params.id, latestTurn.id)
          : null;
        if (!controller.signal.aborted) {
          setSelectedTurnId(latestTurn?.id ?? "");
          setState({ status: "ready", game, memory, versions, turns, diagnostic });
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
    const [memory, turns, game, versions] = await Promise.all([
      getGameMemory(params.id),
      getTurns(params.id),
      getGame(params.id),
      getSettingVersions(params.id)
    ]);
    const turnId = selectedTurnId || turns[turns.length - 1]?.id || "";
    const diagnostic = turnId ? await getContextDiagnostic(params.id, turnId) : null;
    setState({ status: "ready", game, memory, versions, turns, diagnostic });
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
    setActionStatus("正在重建剧本素材向量...");
    try {
      const result = await reindexGameLore(params.id);
      await refreshMemory();
      setActionStatus(`剧本素材向量已重建，更新 ${result.updated}/${result.total} 条。`);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "重建剧本素材向量失败。");
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
          game={state.game}
          memory={state.memory}
          onRebuildSummaries={handleRebuildSummaries}
          onReindexLore={handleReindexLore}
          onRefresh={refreshMemory}
          onTurnChange={handleTurnChange}
          selectedTurnId={selectedTurnId}
          turns={state.turns}
          versions={state.versions}
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
  game,
  memory,
  onRebuildSummaries,
  onReindexLore,
  onRefresh,
  onTurnChange,
  selectedTurnId,
  turns,
  versions
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | "lore" | null;
  diagnostic: ContextDiagnosticRead | null;
  game: GameDetail;
  memory: GameMemoryRead;
  onRebuildSummaries: () => void;
  onReindexLore: () => void;
  onRefresh: () => Promise<void>;
  onTurnChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  selectedTurnId: string;
  turns: TurnRead[];
  versions: GameSettingVersionRead[];
}) {
  const [activeTab, setActiveTab] = useState<MemoryTab>("core");
  const [exportingScript, setExportingScript] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const summaryBuckets = useMemo(() => bucketSummaries(memory.summaries), [memory.summaries]);
  const contract = useMemo(() => buildContractView(game), [game]);
  const embeddedLoreCount = memory.lore_entries.filter((entry) => entry.embedding_configured).length;
  const tabs: { key: MemoryTab; label: string }[] = [
    { key: "core", label: "核心设定" },
    { key: "settings", label: "设置" },
    { key: "versions", label: "版本历史" }
  ];

  async function handleScriptExport() {
    setExportingScript(true);
    setExportStatus("正在生成剧本 Markdown...");
    setExportError(null);
    try {
      const { blob, filename } = await getGameScriptExport(memory.game.id);
      downloadBlob(blob, filename);
      setExportStatus("剧本 Markdown 已开始下载。");
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "导出剧本失败。");
      setExportStatus(null);
    } finally {
      setExportingScript(false);
    }
  }

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader
        active="memory"
        eyebrow="资料"
        gameId={memory.game.id}
        primaryAction={
          <div className="grid w-full gap-2 sm:flex sm:w-fit sm:flex-wrap sm:justify-end">
            <button
              className="app-button w-full sm:w-fit"
              disabled={exportingScript}
              onClick={handleScriptExport}
              type="button"
            >
              {exportingScript ? "导出中..." : "导出剧本"}
            </button>
            <Link
              className="app-button app-button-primary w-full sm:w-fit"
              href={`/games/${memory.game.id}/play`}
            >
              继续冒险
            </Link>
          </div>
        }
        subtitle={
          <>
            当前回合 {memory.current_turn} · 历史 {memory.turn_count} 回 · 剧本素材{" "}
            {memory.lore_entries.length} 条 · 摘要 {memory.summaries.length} 条
          </>
        }
        title={memory.game.title}
      />
      {exportStatus ? <p className="app-status">{exportStatus}</p> : null}
      {exportError ? <p className="app-alert">{exportError}</p> : null}

      <section className="grid grid-cols-3 gap-2 sm:gap-3">
        <Metric label="回合" value={memory.current_turn} />
        <Metric label="剧本素材" value={memory.lore_entries.length} />
        <Metric label="摘要" value={memory.summaries.length} />
      </section>

      <nav className="history-toolbar-group sm:grid-cols-3" aria-label="设定管理">
        {tabs.map((tab) => (
          <button
            className={tabButtonClass(activeTab === tab.key)}
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "core" ? (
        <CoreSettingsSection
          contract={contract}
          diagnostic={diagnostic}
          game={game}
          key={`core-${game.updated_at}`}
          memory={memory}
        />
      ) : null}
      {activeTab === "settings" ? (
        <UnifiedSettingsSection
          game={game}
          key={`settings-${game.updated_at}-${memory.lore_entries.map((entry) => entry.updated_at).join("-")}-${game.modes.map((mode) => mode.updated_at).join("-")}`}
          memory={memory}
          onRefresh={onRefresh}
        />
      ) : null}
      {activeTab === "versions" ? (
        <VersionHistorySection
          gameId={memory.game.id}
          onRefresh={onRefresh}
          versions={versions}
        />
      ) : null}

      <details className="surface-panel">
        <summary className="cursor-pointer surface-title">高级维护与诊断</summary>
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

      <SummarySection buckets={summaryBuckets} />
    </div>
  );
}

function CoreSettingsSection({
  contract,
  diagnostic,
  game,
  memory
}: {
  contract: ContractView;
  diagnostic: ContextDiagnosticRead | null;
  game: GameDetail;
  memory: GameMemoryRead;
}) {
  const script = asRecord(game.config?.script_outline);

  return (
    <section className="surface-panel surface-panel-strong">
      <SectionHeader
        title="核心设定"
        subtitle="这里仅展示当前剧情锚点、剧本蓝图和运行时注入诊断。所有可编辑项目已合并到设置。"
      />
      <ContractSection contract={contract} />
      <BlueprintReadOnlySection script={script} />
      <MechanicsOverviewSection
        diagnostic={diagnostic}
        entries={memory.lore_entries}
        game={game}
        modes={game.modes}
      />
    </section>
  );
}

function UnifiedSettingsSection({
  game,
  memory,
  onRefresh
}: {
  game: GameDetail;
  memory: GameMemoryRead;
  onRefresh: () => Promise<void>;
}) {
  const script = asRecord(game.config?.script_outline);
  const storySignalTypes = new Set(["clue", "pressure", "twist", "secret", "foreshadow"]);
  const signalEntries = memory.lore_entries.filter((entry) =>
    storySignalTypes.has((entry.type ?? "").toLowerCase())
  );
  const materialEntries = memory.lore_entries.filter(
    (entry) => !storySignalTypes.has((entry.type ?? "").toLowerCase())
  );

  return (
    <div className="grid gap-4">
      <SettingsImportExportSection game={game} onRefresh={onRefresh} />
      <WorldAndGenreSection game={game} onRefresh={onRefresh} />
      <CampaignPromiseSection game={game} onRefresh={onRefresh} />
      <PlotStructureSection game={game} script={script} onRefresh={onRefresh} />
      <LoreManagerSection
        createLabel="新增剧本素材"
        defaultType="npc"
        emptyText="暂无人物、地点、势力或物品素材。"
        entries={materialEntries}
        gameId={memory.game.id}
        saveLabel="保存剧本素材"
        subtitle="这些素材会在相关剧情中作为人物、地点、势力、物品或规则依据，帮助 GM 保持世界一致。"
        title="人物、地点与势力"
        onRefresh={onRefresh}
      />
      <LoreManagerSection
        createLabel="新增线索素材"
        defaultType="clue"
        emptyText="暂无线索、秘密或压力素材。"
        entries={signalEntries}
        gameId={memory.game.id}
        saveLabel="保存线索素材"
        subtitle="这些素材决定哪些真相可以被看见、哪些秘密需要隐藏，以及剧情压力如何推进。"
        title="线索、秘密与压力"
        onRefresh={onRefresh}
      >
        <ScriptStructurePreview script={script} variant="signals" />
      </LoreManagerSection>
      <ModeManagerSection gameId={memory.game.id} modes={game.modes} onRefresh={onRefresh} />
      <AdvancedSettingsSection game={game} onRefresh={onRefresh} />
      <AdvancedJsonSection game={game} onRefresh={onRefresh} />
    </div>
  );
}

function SettingsImportExportSection({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setExporting(true);
    setStatus("正在导出设置 JSON...");
    setError(null);
    try {
      const { blob, filename } = await getGameSettingsExport(game.id);
      downloadBlob(blob, filename);
      setStatus("设置 JSON 已开始下载。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出设置失败。");
      setStatus(null);
    } finally {
      setExporting(false);
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setImporting(true);
    setStatus("正在导入设置 JSON...");
    setError(null);
    try {
      const payload = JSON.parse(await file.text()) as unknown;
      await importGameSettings(game.id, payload);
      await onRefresh();
      setStatus("设置已导入，剧本素材索引已同步重建。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导入设置失败。");
      setStatus(null);
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="设置导入导出"
        subtitle="导出的 settings JSON 只包含设定，不包含回合历史、当前状态、摘要或存档进度。"
      />
      <div className="mt-4 grid gap-3 lg:grid-cols-[auto_1fr] lg:items-center">
        <button
          className="app-button app-button-primary w-fit"
          disabled={exporting || importing}
          onClick={handleExport}
          type="button"
        >
          {exporting ? "导出中..." : "导出设置 JSON"}
        </button>
        <label className="grid gap-1 text-sm font-medium">
          <SettingLabel label="导入设置 JSON" />
          <input
            accept="application/json,.json"
            className="app-input"
            disabled={exporting || importing}
            onChange={handleImport}
            type="file"
          />
        </label>
      </div>
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
    </section>
  );
}

function WorldAndGenreSection({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const worldview = asRecord(game.config?.worldview);
  const script = asRecord(game.config?.script_outline);
  const story = asRecord(script.story_contract);
  const [form, setForm] = useState({
    title: game.title,
    genre: game.genre ?? "",
    description: game.description ?? "",
    summary: pickString(worldview, ["summary", "overview", "theme", "setting"]),
    tone: pickString(worldview, ["tone", "mood"]) || pickString(story, ["tone"])
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存世界与题材...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        title: form.title,
        genre: nullableText(form.genre),
        description: nullableText(form.description),
        worldview: {
          summary: nullableText(form.summary),
          tone: nullableText(form.tone),
          genre: nullableText(form.genre)
        },
        story_contract: {
          tone: nullableText(form.tone)
        }
      });
      await onRefresh();
      setStatus("世界与题材已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存世界与题材失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="世界与题材"
        subtitle="定义这个游戏是什么类型、发生在什么世界、整体气质和玩家进入故事时看到的第一层背景。"
      />
      <form className="mt-4 grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextField label="标题" value={form.title} onChange={(title) => setForm({ ...form, title })} />
          <TextField label="题材" value={form.genre} onChange={(genre) => setForm({ ...form, genre })} />
        </div>
        <TextareaField label="简介" value={form.description} onChange={(description) => setForm({ ...form, description })} />
        <TextareaField label="世界观摘要" value={form.summary} onChange={(summary) => setForm({ ...form, summary })} />
        <TextField label="基调" value={form.tone} onChange={(tone) => setForm({ ...form, tone })} />
        <FormActions saving={saving} status={status} error={error} submitLabel="保存世界与题材" />
      </form>
    </section>
  );
}

function CampaignPromiseSection({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const worldview = asRecord(game.config?.worldview);
  const script = asRecord(game.config?.script_outline);
  const campaign = asRecord(script.campaign_contract);
  const story = asRecord(script.story_contract);
  const acts = Array.isArray(script.acts) ? script.acts : [];
  const currentActId = pickString(campaign, ["current_act", "act", "stage", "phase"]);
  const currentAct = asRecord(
    acts.find((item) => {
      const act = asRecord(item);
      return (
        pickString(act, ["id", "key", "name", "title"]) === currentActId ||
        pickString(act, ["id", "key"]) === currentActId
      );
    }) ?? acts[0]
  );
  const [form, setForm] = useState({
    premise: pickString(campaign, ["premise"]),
    playerFantasy: pickString(campaign, ["player_fantasy", "premise"]),
    centralQuestion: pickString(campaign, ["central_question"]),
    mainGoal:
      pickString(campaign, ["main_goal", "core_goal", "objective", "goal"]) ||
      pickString(currentAct, ["objective", "goal"]) ||
      pickString(campaign, ["premise"]),
    canonTerms: listToText(pickList(campaign, ["canon_terms"])),
    keyNpcs: listToText([
      ...pickList(campaign, ["key_npcs", "important_npcs"]),
      ...namesFromRelationshipArcs(pickList(campaign, ["relationship_arcs"])),
      ...pickList(worldview, ["key_npcs"])
    ]),
    keyConflicts: listToText([
      ...pickList(campaign, ["key_conflicts", "main_conflict"]),
      ...pickList(worldview, ["conflicts", "core_conflicts", "main_conflict"])
    ]),
    mustPreserve: listToText([
      ...pickList(campaign, ["must_preserve"]),
      ...pickList(asRecord(script.user_brief), ["must_include"])
    ]),
    mustNotBecome: listToText([
      ...pickList(campaign, ["must_not_become"]),
      ...pickList(asRecord(script.user_brief), ["forbidden_content"])
    ]),
    forbiddenDrift: listToText(pickList(campaign, ["forbidden_drift", "must_not", "avoid"])),
    narrativeStyle: listToText([
      pickString(story, ["narrative_style", "style", "voice"]),
      pickString(worldview, ["tone", "mood"]),
      ...pickList(campaign, ["tone_do"]),
      ...pickList(campaign, ["tone_dont"]),
      ...pickList(campaign, ["pacing_rules"])
    ])
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存主线承诺...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        campaign_contract: {
          premise: nullableText(form.premise),
          player_fantasy: nullableText(form.playerFantasy),
          central_question: nullableText(form.centralQuestion),
          main_goal: nullableText(form.mainGoal),
          canon_terms: textToList(form.canonTerms),
          key_npcs: textToList(form.keyNpcs),
          key_conflicts: textToList(form.keyConflicts),
          must_preserve: textToList(form.mustPreserve),
          must_not_become: textToList(form.mustNotBecome),
          forbidden_drift: textToList(form.forbiddenDrift)
        },
        worldview: {
          key_npcs: textToList(form.keyNpcs),
          conflicts: textToList(form.keyConflicts)
        },
        story_contract: {
          narrative_style: nullableText(form.narrativeStyle)
        }
      });
      await onRefresh();
      setStatus("主线承诺已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存主线承诺失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="主线承诺"
        subtitle="锁定玩家最想体验的核心幻想、主线问题和不能偏离的边界，避免后续剧情跑题。"
      />
      <form className="mt-4 grid gap-4" onSubmit={handleSubmit}>
        <TextareaField label="剧本前提" value={form.premise} onChange={(premise) => setForm({ ...form, premise })} />
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="核心幻想" value={form.playerFantasy} onChange={(playerFantasy) => setForm({ ...form, playerFantasy })} />
          <TextareaField label="核心悬念" value={form.centralQuestion} onChange={(centralQuestion) => setForm({ ...form, centralQuestion })} />
          <TextareaField label="主线目标" value={form.mainGoal} onChange={(mainGoal) => setForm({ ...form, mainGoal })} />
          <TextareaField label="叙事风格" value={form.narrativeStyle} onChange={(narrativeStyle) => setForm({ ...form, narrativeStyle })} />
        </div>
        <TextareaField label="正典词条" value={form.canonTerms} onChange={(canonTerms) => setForm({ ...form, canonTerms })} helper="每行一项" />
        <div className="grid gap-3 lg:grid-cols-3">
          <TextareaField label="关键 NPC / 势力" value={form.keyNpcs} onChange={(keyNpcs) => setForm({ ...form, keyNpcs })} helper="每行一项" />
          <TextareaField label="关键冲突" value={form.keyConflicts} onChange={(keyConflicts) => setForm({ ...form, keyConflicts })} helper="每行一项" />
          <TextareaField label="禁止偏离点" value={form.forbiddenDrift} onChange={(forbiddenDrift) => setForm({ ...form, forbiddenDrift })} helper="每行一项" />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="必须保留" value={form.mustPreserve} onChange={(mustPreserve) => setForm({ ...form, mustPreserve })} helper="每行一项" />
          <TextareaField label="禁止变成" value={form.mustNotBecome} onChange={(mustNotBecome) => setForm({ ...form, mustNotBecome })} helper="每行一项" />
        </div>
        <FormActions saving={saving} status={status} error={error} submitLabel="保存主线承诺" />
      </form>
    </section>
  );
}

function PlotStructureSection({
  game,
  onRefresh,
  script
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
  script: Record<string, unknown>;
}) {
  const campaign = asRecord(script.campaign_contract);
  const director = asRecord(script.director_contract);
  const [form, setForm] = useState({
    currentAct: pickString(campaign, ["current_act", "act", "stage", "phase"]),
    actPlan: listToText(pickList(campaign, ["act_plan"])),
    directorFocus: pickString(director, ["narrative_focus", "focus"]),
    directorPacing: pickString(director, ["pacing"]),
    directorGuardrails: listToText(pickList(director, ["guardrails"])),
    forbiddenReveals: listToText(pickList(director, ["forbidden_reveals"]))
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存剧情结构...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        campaign_contract: {
          current_act: nullableText(form.currentAct),
          act_plan: textToList(form.actPlan)
        },
        director_contract: {
          narrative_focus: nullableText(form.directorFocus),
          pacing: nullableText(form.directorPacing),
          guardrails: textToList(form.directorGuardrails),
          forbidden_reveals: textToList(form.forbiddenReveals)
        }
      });
      await onRefresh();
      setStatus("剧情结构已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存剧情结构失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="剧情结构"
        subtitle="管理当前幕、章节计划、真相揭示和导演节奏，决定故事先推进什么、暂时隐藏什么。"
      />
      <ScriptStructurePreview script={script} variant="structure" />
      <form className="mt-4 grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextField label="当前幕" value={form.currentAct} onChange={(currentAct) => setForm({ ...form, currentAct })} />
          <TextareaField label="幕结构计划" value={form.actPlan} onChange={(actPlan) => setForm({ ...form, actPlan })} helper="每行一项" />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="导演叙事焦点" value={form.directorFocus} onChange={(directorFocus) => setForm({ ...form, directorFocus })} />
          <TextareaField label="导演节奏" value={form.directorPacing} onChange={(directorPacing) => setForm({ ...form, directorPacing })} />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="导演护栏" value={form.directorGuardrails} onChange={(directorGuardrails) => setForm({ ...form, directorGuardrails })} helper="每行一项" />
          <TextareaField label="禁止提前揭示" value={form.forbiddenReveals} onChange={(forbiddenReveals) => setForm({ ...form, forbiddenReveals })} helper="每行一项" />
        </div>
        <FormActions saving={saving} status={status} error={error} submitLabel="保存剧情结构" />
      </form>
    </section>
  );
}

function GenerationSettingsFields({
  form,
  updateField
}: {
  form: Record<keyof Required<GenerationSettings>, string>;
  updateField: (key: keyof Required<GenerationSettings>, value: string) => void;
}) {
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 lg:grid-cols-3">
        <NumberField label="剧情目标最少字数" value={form.narrative_target_min_chars} onChange={(value) => updateField("narrative_target_min_chars", value)} />
        <NumberField label="剧情目标最多字数" value={form.narrative_target_max_chars} onChange={(value) => updateField("narrative_target_max_chars", value)} />
        <NumberField label="剧情最低字数" value={form.narrative_min_chars} onChange={(value) => updateField("narrative_min_chars", value)} />
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <NumberField label="最少段落" value={form.paragraph_min} onChange={(value) => updateField("paragraph_min", value)} />
        <NumberField label="最多段落" value={form.paragraph_max} onChange={(value) => updateField("paragraph_max", value)} />
        <NumberField label="场景标题上限" value={form.scene_heading_max} onChange={(value) => updateField("scene_heading_max", value)} />
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <NumberField label="重点标记最少" value={form.emphasis_min} onChange={(value) => updateField("emphasis_min", value)} />
        <NumberField label="重点标记最多" value={form.emphasis_max} onChange={(value) => updateField("emphasis_max", value)} />
        <NumberField label="近期回合片段长度" value={form.recent_turn_excerpt_chars} onChange={(value) => updateField("recent_turn_excerpt_chars", value)} />
      </div>
    </div>
  );
}

function ContractSection({ contract }: { contract: ContractView }) {
  return (
    <div className="rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">当前锁定摘要</h3>
          <p className="surface-subtle mt-1">
            这些内容来自创建时的世界与导演约束，用来检查剧情是否仍贴合最初方向。
          </p>
        </div>
        <span className="app-pill">预览</span>
      </div>

      {!contract.hasContent ? (
        <p className="mt-4 rounded border border-dashed border-[color:var(--border)] p-3 text-sm text-[color:var(--muted)]">
          当前存档没有可展示的核心设定锁定信息。
        </p>
      ) : (
        <div className="contract-grid mt-4">
          {contract.sections.map((section) => (
            <article className="contract-card" key={section.key}>
              <h3>{section.label}</h3>
              {section.items.length > 0 ? (
                <ul>
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p>未记录。</p>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function BlueprintReadOnlySection({ script }: { script: Record<string, unknown> }) {
  const cards = [
    {
      key: "user_brief",
      label: "用户创作简报",
      items: readableLines(script.user_brief)
    },
    {
      key: "truth_map",
      label: "真相地图",
      items: readableLines(script.truth_map)
    },
    {
      key: "clue_ladder",
      label: "线索阶梯",
      items: readableLines(script.clue_ladder)
    },
    {
      key: "pressure_clock",
      label: "压力时钟",
      items: readableLines(script.pressure_clock)
    }
  ];
  const visibleCards = cards.filter((card) => card.items.length > 0);
  if (visibleCards.length === 0) {
    return null;
  }

  return (
    <section className="mt-4 rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3">
      <h3 className="text-sm font-semibold">编剧蓝图</h3>
      <p className="surface-subtle mt-1">
        这些内容来自创建时的自动扩写，用于约束真相、线索和压力推进。
      </p>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {visibleCards.map((card) => (
          <article className="archive-card" key={card.key}>
            <h4 className="text-sm font-semibold">{card.label}</h4>
            <ul className="mt-2 grid gap-1 text-sm leading-6 text-[color:var(--muted)]">
              {card.items.slice(0, 6).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function MechanicsOverviewSection({
  diagnostic,
  entries,
  game,
  modes
}: {
  diagnostic: ContextDiagnosticRead | null;
  entries: LoreEntryMemoryRead[];
  game: GameDetail;
  modes: ModeRead[];
}) {
  const script = asRecord(game.config?.script_outline);
  const campaign = asRecord(script.campaign_contract);
  const contractMechanics = uniqueStrings([
    ...readableLines(script.mechanics_contract),
    ...readableLines(campaign.mechanics_contract),
    ...pickList(campaign, ["pacing_rules"])
  ]).slice(0, 8);
  const activeMechanicEntries = entries
    .filter((entry) => {
      const type = (entry.type ?? "").toLowerCase();
      return (
        entry.is_active &&
        (["core_rule", "mechanic", "rule"].includes(type) ||
          (entry.always_on && ["critical", "high"].includes(entry.priority ?? "")))
      );
    })
    .slice(0, 8);
  const alwaysOnRuntime = diagnostic?.always_on_lore ?? [];
  const relatedRuntime = diagnostic?.related_lore ?? [];
  const enabledModes = modes.filter((mode) => mode.enabled);

  return (
    <section className="mt-4 rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">机制与规则总览</h3>
          <p className="surface-subtle mt-1">
            用来确认创建时设定的机制是否已经固定、索引，并会进入后续 GM 上下文。
          </p>
        </div>
        <span className="app-pill">
          {entries.filter((entry) => entry.embedding_configured).length}/{entries.length} 已索引
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <MechanicsListCard
          emptyText="暂无结构化机制契约。"
          items={contractMechanics}
          title="结构化机制契约"
        />
        <article className="archive-card">
          <h4 className="text-sm font-semibold">核心机制素材</h4>
          {activeMechanicEntries.length === 0 ? (
            <p className="mt-3 text-sm text-[color:var(--muted)]">暂无核心机制素材。</p>
          ) : (
            <div className="mt-3 grid gap-3">
              {activeMechanicEntries.map((entry) => (
                <div className="rounded border border-[color:var(--border)] p-3" key={entry.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <h5 className="font-semibold">{entry.title}</h5>
                    <span className="app-pill">{entryStatus(entry)}</span>
                  </div>
                  <p className="mt-2 line-clamp-3 text-sm leading-6 text-[color:var(--muted)]">
                    {entry.public_info || entry.content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </article>
        <MechanicsListCard
          emptyText={diagnostic ? "当前回合没有持续参与的素材。" : "暂无运行时诊断。"}
          items={alwaysOnRuntime.map((entry) => `${entry.title} · ${entry.type ?? "unknown"}`)}
          title="当前持续素材"
        />
        <MechanicsListCard
          emptyText={diagnostic ? "当前回合没有相关召回条目。" : "暂无运行时诊断。"}
          items={relatedRuntime.map((entry) => `${entry.title} · 命中 ${entry.matched_terms.length} 项`)}
          title="当前相关召回"
        />
        <MechanicsListCard
          emptyText="暂无启用行动风格。"
          items={enabledModes.map((mode) => `${mode.name} · ${mode.priority ?? "medium"}`)}
          title="已启用行动风格"
        />
        <MechanicsListCard
          emptyText="当前行动没有命中模式。"
          items={
            diagnostic?.selected_mode
              ? [
                  `${diagnostic.selected_mode.name} · ${
                    diagnostic.selected_mode.priority ?? "medium"
                  }`
                ]
              : []
          }
          title="当前命中模式"
        />
      </div>
    </section>
  );
}

function MechanicsListCard({
  emptyText,
  items,
  title
}: {
  emptyText: string;
  items: string[];
  title: string;
}) {
  return (
    <article className="archive-card">
      <h4 className="text-sm font-semibold">{title}</h4>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-[color:var(--muted)]">{emptyText}</p>
      ) : (
        <ul className="mt-3 grid gap-2 text-sm leading-6">
          {items.map((item) => (
            <li className="rounded border border-[color:var(--border)] px-3 py-2" key={item}>
              {item}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <article className="metric-tile">
      <p className="metric-tile-label">{label}</p>
      <p className="metric-tile-value">{value}</p>
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
    <section className="archive-card">
      <h2 className="surface-title">维护</h2>
      <p className="surface-subtle mt-1">
        摘要和向量会影响下一次剧情生成时注入的上下文。正常游戏时不需要频繁操作。
      </p>
      <p className="app-status mt-3">剧本素材索引：{embeddedLoreCount}/{loreCount}</p>
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
          {busyAction === "lore" ? "重建中..." : "重建剧本素材索引"}
        </button>
      </div>
      {actionStatus ? <p className="app-status mt-3">{actionStatus}</p> : null}
      {actionError ? <p className="app-alert mt-3">{actionError}</p> : null}
    </section>
  );
}

function SummarySection({ buckets }: { buckets: Record<string, SummaryRead[]> }) {
  return (
    <section className="surface-panel surface-panel-strong">
      <h2 className="surface-title">上下文记忆</h2>
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
        <article className="archive-card archive-card-green" key={summary.id}>
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
    <section className="archive-card">
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
            <p className="app-wrap-text mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
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
          <details className="rounded border border-[color:var(--border)]">
            <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
              实际注入的剧本锁定
            </summary>
            <div className="grid gap-3 border-t border-[color:var(--border)] p-3">
              <RuntimeBlueprintSummary diagnostic={diagnostic} />
              <JsonBlock
                data={{
                  campaign_contract: diagnostic.campaign_contract,
                  story_blueprint: diagnostic.story_blueprint
                }}
              />
            </div>
          </details>
          <LoreDiagnosticList label="持续素材" entries={diagnostic.always_on_lore} />
          <LoreDiagnosticList label="相关素材" entries={diagnostic.related_lore} />
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

function RuntimeBlueprintSummary({ diagnostic }: { diagnostic: ContextDiagnosticRead }) {
  const contract = asRecord(diagnostic.campaign_contract);
  const blueprint = asRecord(diagnostic.story_blueprint);
  const currentAct = asRecord(blueprint.current_act);
  const items = [
    ["核心悬念", pickString(blueprint, ["central_question"]) || pickString(contract, ["central_question"])],
    ["主线目标", pickString(blueprint, ["main_goal"]) || pickString(contract, ["main_goal", "premise"])],
    [
      "当前幕",
      [
        pickString(currentAct, ["id", "key"]),
        pickString(currentAct, ["name", "title"]),
        pickString(currentAct, ["objective", "dramatic_question"])
      ]
        .filter(Boolean)
        .join(" · ")
    ],
    ["禁止揭露", readableLines(currentAct.forbidden_reveals).slice(0, 3).join("；")],
    ["压力时钟", readableLines(blueprint.pressure_clock).slice(0, 3).join("；")]
  ].filter(([, value]) => value);

  if (items.length === 0) {
    return (
      <p className="rounded border border-dashed border-[color:var(--border)] p-3 text-sm text-[color:var(--muted)]">
        当前诊断没有剧本锁定摘要。
      </p>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div className="rounded border border-[color:var(--border)] p-3" key={label}>
          <p className="text-xs font-medium text-[color:var(--muted)]">{label}</p>
          <p className="app-wrap-text mt-1 text-sm leading-6">{value}</p>
        </div>
      ))}
    </div>
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
          <article className="archive-card" key={entry.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="font-semibold">{entry.title}</h4>
                <span className="text-xs text-[color:var(--muted)]">
                  {entry.score === null ? "常驻" : `score ${entry.score}`}
                </span>
              </div>
              <p className="app-wrap-text mt-2 max-h-20 overflow-auto text-xs leading-5 text-[color:var(--muted)]">
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

function ScriptStructurePreview({
  script,
  variant
}: {
  script: Record<string, unknown>;
  variant: "structure" | "signals";
}) {
  const cards =
    variant === "structure"
      ? [
          {
            key: "acts",
            label: "幕结构",
            help: "幕结构决定当前故事处于哪个阶段，每一幕应该完成什么目标，以及哪些揭示需要推迟。",
            items: readableLines(script.acts)
          },
          {
            key: "completion_anchors",
            label: "当前幕完成锚点",
            help: "完成锚点是进入下一幕前需要自然发生的关键事件；它们是通行条件，不是强制任务清单。",
            items: actAnchorLines(script.acts)
          },
          {
            key: "truth_map",
            label: "真相地图",
            help: "真相地图记录隐藏事实和公开伪装，帮助 GM 慢慢揭示秘密而不是一次说破。",
            items: readableLines(script.truth_map)
          },
          {
            key: "clue_ladder",
            label: "线索阶梯",
            help: "线索阶梯决定玩家应该先看到哪些表层线索，再逐步接近更深层真相。",
            items: readableLines(script.clue_ladder)
          },
          {
            key: "pressure_clock",
            label: "压力时钟",
            help: "压力时钟定义拖延、失败或敌方行动会带来的升级后果，让剧情保持推进压力。",
            items: readableLines(script.pressure_clock)
          }
        ]
      : [
          {
            key: "truth_map",
            label: "隐藏真相",
            help: "这里的内容通常不能直接告诉玩家，只能通过可观察线索、异常行为或后续事件逐步浮现。",
            items: readableLines(script.truth_map)
          },
          {
            key: "clue_ladder",
            label: "线索路径",
            help: "这里决定玩家调查时能获得什么证据，以及这些证据会指向哪些下一步行动。",
            items: readableLines(script.clue_ladder)
          },
          {
            key: "pressure_clock",
            label: "压力推进",
            help: "这里决定故事在玩家犹豫、失败或拖延时如何升级，避免剧情停在原地。",
            items: readableLines(script.pressure_clock)
          }
        ];
  const visibleCards = cards.filter((card) => card.items.length > 0);
  if (visibleCards.length === 0) {
    return null;
  }
  return (
    <div className="mt-4 grid gap-3 lg:grid-cols-2">
      {visibleCards.map((card) => (
        <article className="archive-card" key={card.key}>
          <SectionSubheader title={card.label} help={card.help} />
          <ul className="mt-3 grid gap-2 text-sm leading-6 text-[color:var(--muted)]">
            {card.items.slice(0, 8).map((item, index) => (
              <li className="rounded border border-[color:var(--border)] px-3 py-2" key={`${card.key}-${index}`}>
                {item}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

function LoreManagerSection({
  children,
  createLabel = "新增剧本素材",
  defaultType = "setting",
  emptyText = "暂无剧本素材。",
  entries,
  gameId,
  onRefresh,
  saveLabel = "保存剧本素材",
  subtitle,
  title
}: {
  children?: ReactNode;
  createLabel?: string;
  defaultType?: string;
  emptyText?: string;
  entries: LoreEntryMemoryRead[];
  gameId: string;
  onRefresh: () => Promise<void>;
  saveLabel?: string;
  subtitle: string;
  title: string;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeEntries = entries.filter((entry) => entry.is_active);
  const archivedEntries = entries.filter((entry) => !entry.is_active);
  const activeGroups = groupLoreEntries(activeEntries);

  async function saveLore(payload: LoreEntryCreate, entry?: LoreEntryMemoryRead) {
    setStatus(entry ? "正在保存剧本素材..." : "正在新增剧本素材...");
    setError(null);
    try {
      if (entry) {
        await updateLoreEntry(gameId, entry.id, payload);
      } else {
        await createLoreEntry(gameId, payload);
      }
      setEditingId(null);
      await onRefresh();
      setStatus(entry ? "剧本素材已保存。" : "剧本素材已新增。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存剧本素材失败。");
      setStatus(null);
    }
  }

  async function archiveEntry(entry: LoreEntryMemoryRead) {
    setStatus("正在归档剧本素材...");
    setError(null);
    try {
      await archiveLoreEntry(gameId, entry.id);
      await onRefresh();
      setStatus("剧本素材已归档，不会再参与后续剧情。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "归档剧本素材失败。");
      setStatus(null);
    }
  }

  async function restoreEntry(entry: LoreEntryMemoryRead) {
    setStatus("正在恢复剧本素材...");
    setError(null);
    try {
      await updateLoreEntry(gameId, entry.id, { is_active: true });
      await onRefresh();
      setStatus("剧本素材已恢复。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复剧本素材失败。");
      setStatus(null);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title={title}
        subtitle={subtitle}
      />
      {children}
      <LoreEditor
        createLabel={createLabel}
        defaultType={defaultType}
        saveLabel={saveLabel}
        onSubmit={(payload) => saveLore(payload)}
      />
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
      <div className="mt-5 grid gap-4">
        {activeEntries.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">{emptyText}</p>
        ) : (
          activeGroups.map((group) => (
            <div className="grid gap-3" key={group.label}>
              <SectionSubheader title={group.label} help={group.help} />
              <div className="grid gap-3 lg:grid-cols-2">
                {group.entries.map((entry) => (
                  <LoreEntryCard
                    editing={editingId === entry.id}
                    entry={entry}
                    key={entry.id}
                    onArchive={() => archiveEntry(entry)}
                    onCancel={() => setEditingId(null)}
                    onEdit={() => setEditingId(entry.id)}
                    onSave={(payload) => saveLore(payload, entry)}
                    saveLabel={saveLabel}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </div>
      {archivedEntries.length > 0 ? (
        <details className="mt-4 rounded border border-[color:var(--border)]" open={showArchived}>
          <summary
            className="cursor-pointer px-3 py-2 text-sm font-semibold"
            onClick={() => setShowArchived(!showArchived)}
          >
            已归档素材（{archivedEntries.length}）
          </summary>
          <div className="grid gap-3 border-t border-[color:var(--border)] p-3 lg:grid-cols-2">
            {archivedEntries.map((entry) => (
              <article className="archive-card app-long-card opacity-75" key={entry.id}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">{entry.title}</h3>
                    <p className="mt-1 text-xs text-[color:var(--muted)]">
                      {entry.type || "unknown"} · 已归档
                    </p>
                  </div>
                  <button className="app-button" onClick={() => restoreEntry(entry)} type="button">
                    恢复
                  </button>
                </div>
                <p className="app-wrap-text mt-3 max-h-32 overflow-auto whitespace-pre-wrap text-sm leading-6">
                  {entry.content}
                </p>
              </article>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function LoreEntryCard({
  editing,
  entry,
  onArchive,
  onCancel,
  onEdit,
  onSave,
  saveLabel
}: {
  editing: boolean;
  entry: LoreEntryMemoryRead;
  onArchive: () => void;
  onCancel: () => void;
  onEdit: () => void;
  onSave: (payload: LoreEntryCreate) => void;
  saveLabel: string;
}) {
  return (
    <article className="archive-card archive-card-accent app-long-card">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="inline-flex items-center gap-2 font-semibold">
            {entry.title}
            <HelpMark text={entryHelpText(entry)} />
          </h3>
          <p className="mt-1 text-xs text-[color:var(--muted)]">
            {entry.type || "unknown"} · {entry.priority || "medium"} ·{" "}
            {entry.always_on ? "持续参与" : "触发参与"} ·{" "}
            {entry.embedding_configured ? "可检索" : "待索引"}
          </p>
        </div>
        <span className="app-pill">
          启用 · {entry.visibility || "mixed"}
        </span>
      </div>
      {editing ? (
        <LoreEditor
          entry={entry}
          onCancel={onCancel}
          onSubmit={onSave}
          saveLabel={saveLabel}
        />
      ) : (
        <>
          <p className="app-wrap-text mt-3 max-h-44 overflow-auto whitespace-pre-wrap text-sm leading-6">
            {entry.content}
          </p>
          <TagRow label="关键词" values={entry.keywords} />
          <TagRow label="触发词" values={entry.trigger_words} />
          {entry.usage_note ? (
            <p className="app-wrap-text mt-3 text-xs leading-5 text-[color:var(--muted)]">
              {entry.usage_note}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="app-button" onClick={onEdit} type="button">
              编辑
            </button>
            <button className="app-button" onClick={onArchive} type="button">
              归档
            </button>
          </div>
        </>
      )}
    </article>
  );
}

function LoreEditor({
  createLabel = "新增剧本素材",
  defaultType = "setting",
  entry,
  onCancel,
  onSubmit,
  saveLabel = "保存剧本素材"
}: {
  createLabel?: string;
  defaultType?: string;
  entry?: LoreEntryMemoryRead;
  onCancel?: () => void;
  onSubmit: (payload: LoreEntryCreate) => void;
  saveLabel?: string;
}) {
  const [form, setForm] = useState({
    title: entry?.title ?? "",
    type: entry?.type ?? defaultType,
    priority: entry?.priority ?? "medium",
    visibility: entry?.visibility ?? "mixed",
    alwaysOn: entry?.always_on ?? false,
    keywords: listToText(entry?.keywords ?? []),
    triggerWords: listToText(entry?.trigger_words ?? []),
    publicInfo: entry?.public_info ?? "",
    gmSecret: entry?.gm_secret ?? "",
    content: entry?.content ?? "",
    usageNote: entry?.usage_note ?? ""
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      title: form.title,
      type: nullableText(form.type),
      priority: nullableText(form.priority),
      visibility: nullableText(form.visibility),
      always_on: form.alwaysOn,
      keywords: textToList(form.keywords),
      trigger_words: textToList(form.triggerWords),
      public_info: nullableText(form.publicInfo),
      gm_secret: nullableText(form.gmSecret),
      content: form.content,
      usage_note: nullableText(form.usageNote)
    });
    if (!entry) {
      setForm({
        title: "",
        type: defaultType,
        priority: "medium",
        visibility: "mixed",
        alwaysOn: false,
        keywords: "",
        triggerWords: "",
        publicInfo: "",
        gmSecret: "",
        content: "",
        usageNote: ""
      });
    }
  }

  return (
    <form className={entry ? "mt-4 grid gap-3" : "mt-4 grid gap-3 rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3"} onSubmit={handleSubmit}>
      <div className="grid gap-3 lg:grid-cols-4">
        <TextField label="标题" value={form.title} onChange={(title) => setForm({ ...form, title })} />
        <TextField label="类型" value={form.type} onChange={(type) => setForm({ ...form, type })} />
        <TextField label="优先级" value={form.priority} onChange={(priority) => setForm({ ...form, priority })} />
        <TextField label="可见性" value={form.visibility} onChange={(visibility) => setForm({ ...form, visibility })} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input checked={form.alwaysOn} onChange={(event) => setForm({ ...form, alwaysOn: event.target.checked })} type="checkbox" />
        <SettingLabel label="持续参与剧情" />
      </label>
      <div className="grid gap-3 lg:grid-cols-2">
        <TextareaField label="关键词" value={form.keywords} onChange={(keywords) => setForm({ ...form, keywords })} helper="每行一项" />
        <TextareaField label="触发词" value={form.triggerWords} onChange={(triggerWords) => setForm({ ...form, triggerWords })} helper="每行一项" />
      </div>
      <TextareaField label="公开信息" value={form.publicInfo} onChange={(publicInfo) => setForm({ ...form, publicInfo })} />
      <TextareaField label="GM 隐藏信息" value={form.gmSecret} onChange={(gmSecret) => setForm({ ...form, gmSecret })} />
      <TextareaField label="剧情使用内容" value={form.content} onChange={(content) => setForm({ ...form, content })} required />
      <TextareaField label="使用说明" value={form.usageNote} onChange={(usageNote) => setForm({ ...form, usageNote })} />
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary" type="submit">
          {entry ? saveLabel : createLabel}
        </button>
        {onCancel ? (
          <button className="app-button" onClick={onCancel} type="button">
            取消
          </button>
        ) : null}
      </div>
    </form>
  );
}

function ModeManagerSection({
  gameId,
  modes,
  onRefresh
}: {
  gameId: string;
  modes: ModeRead[];
  onRefresh: () => Promise<void>;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function saveMode(payload: ModeCreate, mode?: ModeRead) {
    setStatus(mode ? "正在保存行动风格规则..." : "正在新增行动风格规则...");
    setError(null);
    try {
      if (mode) {
        await updateMode(gameId, mode.id, payload);
      } else {
        await createMode(gameId, payload);
      }
      setEditingId(null);
      await onRefresh();
      setStatus(mode ? "行动风格规则已保存。" : "行动风格规则已新增。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存行动风格规则失败。");
      setStatus(null);
    }
  }

  async function toggleMode(mode: ModeRead) {
    setStatus(mode.enabled ? "正在停用行动规则..." : "正在启用行动规则...");
    setError(null);
    try {
      await updateMode(gameId, mode.id, { enabled: !mode.enabled });
      await onRefresh();
      setStatus(mode.enabled ? "行动规则已停用。" : "行动规则已启用。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "切换行动规则失败。");
      setStatus(null);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="玩法规则与行动风格"
        subtitle="这些规则会根据玩家行动触发不同 GM 写法，例如调查、社交、探索、战斗或潜行。"
      />
      <ModeEditor onSubmit={(payload) => saveMode(payload)} />
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
      <div className="mt-5 grid gap-3 lg:grid-cols-2">
        {modes.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无行动风格规则。</p>
        ) : (
          modes.map((mode) => (
            <article
              className={`archive-card app-long-card ${mode.enabled ? "archive-card-green" : "opacity-70"}`}
              key={mode.id}
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="inline-flex items-center gap-2 font-semibold">
                    {mode.name}
                    <HelpMark text="这条行动风格规则会在玩家输入命中触发词时改变 GM 的处理方式，例如更重视线索、风险、谈判或战斗节奏。" />
                  </h3>
                  <p className="mt-1 text-xs text-[color:var(--muted)]">
                    {mode.priority || "medium"} · {mode.enabled ? "启用" : "停用"}
                  </p>
                </div>
                <span className="app-pill">{mode.enabled ? "可触发" : "已停用"}</span>
              </div>
              {editingId === mode.id ? (
                <ModeEditor
                  mode={mode}
                  onCancel={() => setEditingId(null)}
                  onSubmit={(payload) => saveMode(payload, mode)}
                />
              ) : (
                <>
                  <TagRow label="触发词" values={mode.triggers} />
                  <p className="app-wrap-text mt-3 max-h-44 overflow-auto whitespace-pre-wrap text-sm leading-6">
                    {mode.injection}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="app-button" onClick={() => setEditingId(mode.id)} type="button">
                      编辑
                    </button>
                    <button className="app-button" onClick={() => toggleMode(mode)} type="button">
                      {mode.enabled ? "停用规则" : "启用规则"}
                    </button>
                  </div>
                </>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function ModeEditor({
  mode,
  onCancel,
  onSubmit
}: {
  mode?: ModeRead;
  onCancel?: () => void;
  onSubmit: (payload: ModeCreate) => void;
}) {
  const [form, setForm] = useState({
    name: mode?.name ?? "",
    priority: mode?.priority ?? "medium",
    enabled: mode?.enabled ?? true,
    triggers: listToText(mode?.triggers ?? []),
    injection: mode?.injection ?? ""
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      name: form.name,
      priority: nullableText(form.priority),
      enabled: form.enabled,
      triggers: textToList(form.triggers),
      injection: form.injection
    });
    if (!mode) {
      setForm({
        name: "",
        priority: "medium",
        enabled: true,
        triggers: "",
        injection: ""
      });
    }
  }

  return (
    <form
      className={mode ? "mt-4 grid gap-3" : "mt-4 grid gap-3 rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3"}
      onSubmit={handleSubmit}
    >
      <div className="grid gap-3 lg:grid-cols-[1fr_160px]">
        <TextField label="名称" value={form.name} onChange={(name) => setForm({ ...form, name })} />
        <TextField label="优先级" value={form.priority} onChange={(priority) => setForm({ ...form, priority })} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} type="checkbox" />
        <SettingLabel label="启用规则" />
      </label>
      <TextareaField label="触发词" value={form.triggers} onChange={(triggers) => setForm({ ...form, triggers })} helper="每行一项" />
      <TextareaField label="行动规则" value={form.injection} onChange={(injection) => setForm({ ...form, injection })} required />
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary" type="submit">
          {mode ? "保存行动规则" : "新增行动规则"}
        </button>
        {onCancel ? (
          <button className="app-button" onClick={onCancel} type="button">
            取消
          </button>
        ) : null}
      </div>
    </form>
  );
}

function AdvancedSettingsSection({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const initialSettings = normalizeGenerationSettings(game.config?.generation_settings);
  const script = asRecord(game.config?.script_outline);
  const story = asRecord(script.story_contract);
  const [form, setForm] = useState({
    systemPrompt: game.config?.system_prompt ?? "",
    generationNotes: game.config?.generation_notes ?? "",
    storyTone: pickString(story, ["tone"]),
    storyPacing: pickString(story, ["pacing"])
  });
  const [generationForm, setGenerationForm] = useState<Record<keyof Required<GenerationSettings>, string>>({
    narrative_target_min_chars: String(initialSettings.narrative_target_min_chars),
    narrative_target_max_chars: String(initialSettings.narrative_target_max_chars),
    narrative_min_chars: String(initialSettings.narrative_min_chars),
    paragraph_min: String(initialSettings.paragraph_min),
    paragraph_max: String(initialSettings.paragraph_max),
    scene_heading_max: String(initialSettings.scene_heading_max),
    emphasis_min: String(initialSettings.emphasis_min),
    emphasis_max: String(initialSettings.emphasis_max),
    recent_turn_excerpt_chars: String(initialSettings.recent_turn_excerpt_chars)
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function updateGenerationField(key: keyof Required<GenerationSettings>, value: string) {
    setGenerationForm({ ...generationForm, [key]: value });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存 GM 输出与运行参数...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        system_prompt: nullableText(form.systemPrompt),
        generation_notes: nullableText(form.generationNotes),
        generation_settings: {
          narrative_target_min_chars: intField(generationForm.narrative_target_min_chars),
          narrative_target_max_chars: intField(generationForm.narrative_target_max_chars),
          narrative_min_chars: intField(generationForm.narrative_min_chars),
          paragraph_min: intField(generationForm.paragraph_min),
          paragraph_max: intField(generationForm.paragraph_max),
          scene_heading_max: intField(generationForm.scene_heading_max),
          emphasis_min: intField(generationForm.emphasis_min),
          emphasis_max: intField(generationForm.emphasis_max),
          recent_turn_excerpt_chars: intField(generationForm.recent_turn_excerpt_chars)
        },
        story_contract: {
          tone: nullableText(form.storyTone),
          pacing: nullableText(form.storyPacing)
        }
      });
      await onRefresh();
      setStatus("GM 输出与运行参数已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存 GM 输出与运行参数失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-panel surface-panel-strong">
      <SectionHeader
        title="GM 输出与运行参数"
        subtitle="控制 GM 每回合写多长、如何分段、突出哪些重点，以及额外遵守的系统提示和生成备注。"
      />
      <form className="mt-4 grid gap-4" onSubmit={handleSubmit}>
        <div>
          <SectionSubheader
            title="正文长度与格式"
            help="这些数字会直接进入 GM runtime，决定每回合 narrative 的目标长度、段落节奏、标题数量、重点标记密度，以及近期回合摘录长度。"
          />
          <div className="mt-3">
            <GenerationSettingsFields form={generationForm} updateField={updateGenerationField} />
          </div>
        </div>
        <div>
          <SectionSubheader
            title="GM 语言与额外规则"
            help="这些文本会影响 GM 的表达方式、临场取舍和叙事口吻，适合写全局补充规则而不是单个场景细节。"
          />
        </div>
        <TextareaField label="GM 系统提示" value={form.systemPrompt} onChange={(systemPrompt) => setForm({ ...form, systemPrompt })} rows={8} />
        <TextareaField label="生成备注" value={form.generationNotes} onChange={(generationNotes) => setForm({ ...form, generationNotes })} rows={5} />
        <div className="grid gap-3 lg:grid-cols-2">
          <TextField label="剧情基调" value={form.storyTone} onChange={(storyTone) => setForm({ ...form, storyTone })} />
          <TextField label="剧情节奏" value={form.storyPacing} onChange={(storyPacing) => setForm({ ...form, storyPacing })} />
        </div>
        <FormActions saving={saving} status={status} error={error} submitLabel="保存 GM 输出与运行参数" />
      </form>
    </section>
  );
}

function AdvancedJsonSection({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const [draft, setDraft] = useState({
    worldviewJson: formatJson(asRecord(game.config?.worldview)),
    scriptOutlineJson: formatJson(asRecord(game.config?.script_outline))
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存专家 JSON...");
    setError(null);
    try {
      const payload: AdvancedConfigJsonDraft = {
        worldview_json: parseRecordJson(draft.worldviewJson, "worldview"),
        script_outline_json: parseRecordJson(draft.scriptOutlineJson, "script_outline")
      };
      await updateGameConfig(game.id, payload);
      await onRefresh();
      setStatus("专家 JSON 已保存，并已自动保留用户创作简报与内部角色归档字段。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存专家 JSON 失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setDraft({
      worldviewJson: formatJson(asRecord(game.config?.worldview)),
      scriptOutlineJson: formatJson(asRecord(game.config?.script_outline))
    });
    setError(null);
    setStatus("已恢复为当前已保存内容。");
  }

  return (
    <details className="mt-5 rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)]">
      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
        <span className="inline-flex items-center gap-2">
          专家 JSON
          <HelpMark text="这里保留完整 worldview 和 script_outline。适合修正结构化表单没有覆盖的字段，也可以查看剧本生成时留下的完整设定。" />
        </span>
      </summary>
      <form className="grid gap-4 border-t border-[color:var(--border)] p-3" onSubmit={handleSubmit}>
        <p className="text-sm leading-6 text-[color:var(--muted)]">
          这里可以直接修正 worldview 和 script_outline。保存时会校验 JSON 对象，并保留用户创作简报、角色归档和必须/禁止约束。
        </p>
        <div className="grid gap-3 xl:grid-cols-2">
          <TextareaField
            label="worldview JSON"
            onChange={(worldviewJson) => setDraft({ ...draft, worldviewJson })}
            rows={16}
            value={draft.worldviewJson}
          />
          <TextareaField
            label="script_outline JSON"
            onChange={(scriptOutlineJson) => setDraft({ ...draft, scriptOutlineJson })}
            rows={16}
            value={draft.scriptOutlineJson}
          />
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <button className="app-button app-button-primary" disabled={saving} type="submit">
            {saving ? "保存中..." : "保存专家 JSON"}
          </button>
          <button className="app-button" disabled={saving} onClick={handleReset} type="button">
            恢复当前内容
          </button>
        </div>
        {status ? <p className="app-status">{status}</p> : null}
        {error ? <p className="app-alert">{error}</p> : null}
      </form>
    </details>
  );
}

function VersionHistorySection({
  gameId,
  onRefresh,
  versions
}: {
  gameId: string;
  onRefresh: () => Promise<void>;
  versions: GameSettingVersionRead[];
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function restoreVersion(version: GameSettingVersionRead) {
    setBusyId(version.id);
    setStatus("正在恢复版本...");
    setError(null);
    try {
      await restoreSettingVersion(gameId, version.id);
      await onRefresh();
      setStatus("版本已恢复，新的恢复版本已写入历史。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复版本失败。");
      setStatus(null);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="版本历史"
        subtitle="每次新增、编辑、归档、恢复都会留下快照。可以把任意版本恢复为当前设定。"
      />
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
      <div className="mt-4 grid gap-3">
        {versions.length === 0 ? (
          <p className="rounded border border-dashed border-[color:var(--border)] p-3 text-sm text-[color:var(--muted)]">
            暂无版本记录。第一次保存设定后会自动生成基线版本。
          </p>
        ) : (
          versions.map((version) => (
            <article className="archive-card" key={version.id}>
              <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-start">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{versionLabel(version)}</h3>
                    <span className="app-pill">{version.action}</span>
                  </div>
                  <p className="mt-1 text-xs text-[color:var(--muted)]">
                    {formatDateTime(version.created_at)}
                    {version.entity_id ? ` · ${version.entity_id}` : ""}
                  </p>
                </div>
                <button
                  className="app-button app-button-primary"
                  disabled={busyId !== null}
                  onClick={() => restoreVersion(version)}
                  type="button"
                >
                  {busyId === version.id ? "恢复中..." : "恢复此版本"}
                </button>
              </div>
              <p className="mt-3 text-sm leading-6 text-[color:var(--muted)]">
                {versionSummary(version)}
              </p>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function SectionHeader({
  help,
  subtitle,
  title
}: {
  help?: string;
  subtitle: string;
  title: string;
}) {
  return (
    <div>
      <h2 className="surface-title inline-flex items-center gap-2">
        {title}
        <HelpMark text={help ?? helpTextForLabel(title)} />
      </h2>
      <p className="surface-subtle mt-1">{subtitle}</p>
    </div>
  );
}

function SectionSubheader({ help, title }: { help?: string; title: string }) {
  return (
    <h3 className="inline-flex items-center gap-2 text-sm font-semibold">
      {title}
      <HelpMark text={help ?? helpTextForLabel(title)} />
    </h3>
  );
}

function HelpMark({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex align-middle">
      <button
        aria-label={`说明：${text}`}
        className="inline-grid h-5 w-5 place-items-center rounded-full border border-[color:var(--border)] bg-[color:var(--input)] text-xs font-bold text-[color:var(--gold)] outline-none transition group-hover:border-[color:var(--gold)] group-focus-visible:border-[color:var(--gold)]"
        type="button"
      >
        !
      </button>
      <span
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 hidden w-72 -translate-x-1/2 rounded border border-[color:var(--border)] bg-[#111412] p-3 text-left text-xs font-normal leading-5 text-[color:var(--foreground)] shadow-xl group-hover:block group-focus-within:block"
        role="tooltip"
      >
        {text}
      </span>
    </span>
  );
}

function SettingLabel({
  helper,
  help,
  label
}: {
  helper?: string;
  help?: string;
  label: string;
}) {
  return (
    <span className="flex items-center justify-between gap-2">
      <span className="inline-flex items-center gap-1.5">
        {label}
        <HelpMark text={help ?? helpTextForLabel(label)} />
      </span>
      {helper ? <span className="text-xs font-normal text-[color:var(--muted)]">{helper}</span> : null}
    </span>
  );
}

function TextField({
  help,
  label,
  onChange,
  required = false,
  value
}: {
  help?: string;
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      <SettingLabel help={help} label={label} />
      <input
        className="app-input"
        onChange={(event) => onChange(event.target.value)}
        required={required}
        value={value}
      />
    </label>
  );
}

function NumberField({
  help,
  label,
  onChange,
  value
}: {
  help?: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      <SettingLabel help={help} label={label} />
      <input
        className="app-input"
        inputMode="numeric"
        min={0}
        onChange={(event) => onChange(event.target.value)}
        type="number"
        value={value}
      />
    </label>
  );
}

function TextareaField({
  helper,
  help,
  label,
  onChange,
  required = false,
  rows = 4,
  value
}: {
  helper?: string;
  help?: string;
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  rows?: number;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      <SettingLabel helper={helper} help={help} label={label} />
      <textarea
        className="app-input min-h-24 resize-y"
        onChange={(event) => onChange(event.target.value)}
        required={required}
        rows={rows}
        value={value}
      />
    </label>
  );
}

function FormActions({
  error,
  saving,
  status,
  submitLabel
}: {
  error: string | null;
  saving: boolean;
  status: string | null;
  submitLabel: string;
}) {
  return (
    <div className="grid gap-2">
      <button className="app-button app-button-primary w-fit" disabled={saving} type="submit">
        {saving ? "保存中..." : submitLabel}
      </button>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
    </div>
  );
}

function TagRow({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1 text-xs font-medium text-[color:var(--muted)]">
        {label}
        <HelpMark text={helpTextForLabel(label)} />
      </span>
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

type LoreEntryGroup = {
  entries: LoreEntryMemoryRead[];
  help: string;
  label: string;
};

function groupLoreEntries(entries: LoreEntryMemoryRead[]): LoreEntryGroup[] {
  const groups = new Map<string, LoreEntryGroup>();
  for (const entry of entries) {
    const category = loreCategory(entry.type);
    if (!groups.has(category.label)) {
      groups.set(category.label, { ...category, entries: [] });
    }
    groups.get(category.label)?.entries.push(entry);
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    entries: group.entries.sort((a, b) => priorityRank(b.priority) - priorityRank(a.priority))
  }));
}

function loreCategory(type: string | null): Omit<LoreEntryGroup, "entries"> {
  const normalized = (type ?? "").toLowerCase();
  if (["npc", "character", "person"].includes(normalized)) {
    return {
      label: "人物",
      help: "人物素材会影响 NPC 的动机、关系、秘密和出场方式，让角色在多回合中保持一致。"
    };
  }
  if (["location", "place", "scene"].includes(normalized)) {
    return {
      label: "地点",
      help: "地点素材会影响场景细节、可调查对象、风险来源和玩家能采取的行动。"
    };
  }
  if (["faction", "organization", "group"].includes(normalized)) {
    return {
      label: "势力",
      help: "势力素材会影响阵营目标、冲突升级、资源分布和 NPC 的立场。"
    };
  }
  if (["item", "artifact", "prop"].includes(normalized)) {
    return {
      label: "物品",
      help: "物品素材会影响线索、能力、交易筹码或剧情机关，GM 会在相关行动中引用它。"
    };
  }
  if (["mechanic", "core_rule", "rule"].includes(normalized)) {
    return {
      label: "机制规则",
      help: "机制规则会影响游戏方式，例如成长、战斗、调查、资源或特殊能力如何被描述和推进。"
    };
  }
  if (["clue", "secret", "pressure", "twist", "foreshadow"].includes(normalized)) {
    return {
      label: "线索与压力",
      help: "这类素材控制玩家能发现什么、暂时不能知道什么，以及剧情何时升级。"
    };
  }
  return {
    label: "其他设定",
    help: "这些设定会作为补充素材参与后续剧情，帮助 GM 保持世界、人物和规则的一致性。"
  };
}

function priorityRank(priority: string | null) {
  return { critical: 4, high: 3, medium: 2, low: 1 }[priority ?? "medium"] ?? 2;
}

function entryHelpText(entry: LoreEntryMemoryRead) {
  return [
    `类型：${loreCategory(entry.type).label}。`,
    entry.always_on
      ? "它会持续参与剧情上下文，强烈影响后续走向。"
      : "它通常在玩家提到关键词或相关行动时参与剧情。",
    entry.gm_secret ? "包含隐藏信息，GM 只能转化为线索或异常表现，不能直接剧透。" : "",
    entry.usage_note ? `使用方式：${entry.usage_note}` : ""
  ].filter(Boolean).join(" ");
}

function tabButtonClass(active: boolean) {
  return active ? "app-button app-button-primary" : "app-button";
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function pickBoolean(value: unknown, fallback: boolean) {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "y"].includes(normalized)) {
      return true;
    }
    if (["false", "0", "no", "n"].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2);
}

function parseRecordJson(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch (caught) {
    const detail = caught instanceof Error ? caught.message : "无法解析";
    throw new Error(`${label} JSON 格式错误：${detail}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON 对象。`);
  }
  return parsed as Record<string, unknown>;
}

function pickString(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return "";
}

function pickList(record: Record<string, unknown>, keys: string[]) {
  const values: string[] = [];
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) {
      values.push(
        ...value
          .map((item) => (typeof item === "string" ? item.trim() : ""))
          .filter(Boolean)
      );
    } else if (typeof value === "string" && value.trim()) {
      values.push(value.trim());
    }
  }
  return Array.from(new Set(values));
}

function readableLines(value: unknown): string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap(readableLines);
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return [String(value).trim()].filter(Boolean);
  }
  const record = asRecord(value);
  const name = pickString(record, ["name", "title", "mechanic", "rule"]);
  const rule = pickString(record, [
    "rule",
    "description",
    "content",
    "effect",
    "story_effect",
    "completion_signal",
    "objective"
  ]);
  const progression = pickString(record, ["progression", "stage", "track"]);
  const pieces = [name, rule, progression].map((item) => item.trim()).filter(Boolean);
  if (pieces.length > 0) {
    return [pieces.join(" · ")];
  }
  return Object.entries(record)
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${String(item)}`);
}

function actAnchorLines(value: unknown): string[] {
  return asList(value).flatMap((item) => {
    const act = asRecord(item);
    const actLabel =
      pickString(act, ["id", "key"]) ||
      pickString(act, ["name", "title"]) ||
      "未命名幕";
    return asList(act.completion_anchors).map((anchorItem) => {
      const anchor = asRecord(anchorItem);
      const anchorId = pickString(anchor, ["id", "key"]);
      const title = pickString(anchor, ["title", "name"]) || anchorId || "未命名锚点";
      const required = pickBoolean(anchor.required, true) ? "必要" : "可选";
      const signal = pickString(anchor, ["completion_signal", "signal"]);
      const effect = pickString(anchor, ["story_effect", "effect"]);
      return [actLabel, required, title, signal, effect].filter(Boolean).join(" · ");
    });
  });
}

function namesFromRelationshipArcs(arcs: string[]) {
  return arcs
    .map((arc) => arc.split(/[：:]/)[0]?.trim() ?? "")
    .filter(Boolean);
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function entryStatus(entry: LoreEntryMemoryRead) {
  return [
    entry.always_on ? "常驻" : "触发",
    entry.embedding_configured ? "已索引" : "未索引",
    entry.priority ?? "medium"
  ].join(" · ");
}

function listToText(values: string[]) {
  const uniqueValues = values.map((value) => value.trim()).filter(Boolean);
  return Array.from(new Set(uniqueValues)).join("\n");
}

function textToList(text: string) {
  const values = text
    .split(/[\n,，、]/)
    .map((value) => value.trim())
    .filter(Boolean);
  return Array.from(new Set(values));
}

function nullableText(text: string) {
  const trimmed = text.trim();
  return trimmed.length > 0 ? trimmed : null;
}

const HELP_TEXTS: Record<string, string> = {
  "世界与题材": "定义游戏的题材、世界背景和整体气质，是后续剧情描述、场景选择和 NPC 风格的基础。",
  "主线承诺": "锁定玩家最初想玩的核心方向，防止后续即兴生成偏离主题或改写关键设定。",
  "剧情结构": "管理故事分幕、真相揭示和压力节奏，影响 GM 每回合推进什么、暂时隐藏什么。",
  "人物、地点与势力": "这些素材会在相关情境中被召回，决定人物、地点、势力和物品如何参与剧情。",
  "线索、秘密与压力": "这些设定控制调查路径、隐藏真相、反转材料和剧情升级压力。",
  "玩法规则与行动风格": "这些规则会根据玩家行动改变 GM 的处理方式，决定调查、社交、战斗等场景的写法。",
  "GM 输出与运行参数": "这些设置直接影响每回合文本长度、格式密度、叙事口吻和额外生成规则。",
  "设置导入导出": "用于备份或迁移完整设定，不包含回合历史、当前状态、摘要或存档进度。",
  "标题": "游戏名称会出现在页面和导出文件中，也会作为世界与剧本识别锚点。",
  "题材": "题材影响 GM 对场景、冲突、风险、道具和角色表达方式的选择。",
  "简介": "简介是玩家和 GM 理解初始故事的短背景，会影响开局和后续上下文定位。",
  "世界观摘要": "世界观摘要描述玩家可理解的大背景，GM 会据此保持场景和设定一致。",
  "基调": "基调影响文字情绪、镜头质感、NPC 反应和危险程度。",
  "剧本前提": "剧本前提是故事成立的核心句，会约束后续剧情不要变成另一种故事。",
  "核心幻想": "核心幻想描述玩家希望体验的感觉，例如调查、成长、权谋、求生或浪漫。",
  "核心悬念": "核心悬念是长期驱动玩家追问的问题，会影响线索和真相揭示节奏。",
  "主线目标": "主线目标决定玩家长期要完成什么，GM 会用它判断每回合推进是否相关。",
  "叙事风格": "叙事风格影响文字密度、视角、节奏和表现手法。",
  "正典词条": "正典词条用于锁定必须保持一致的名称、概念、组织或专有设定。",
  "关键 NPC / 势力": "这些角色或组织会被视为主线相关对象，更容易进入冲突和线索设计。",
  "关键冲突": "关键冲突决定故事压力来自哪里，会影响 NPC 决策和事件升级方向。",
  "禁止偏离点": "这些内容会阻止 GM 把故事带向不想要的题材、设定或终局方向。",
  "必须保留": "这些元素来自玩家创作意图，保存后会被长期保护，不应被后续生成覆盖。",
  "禁止变成": "这些是故事不能转变成的方向，用于防止风格和世界观漂移。",
  "当前幕": "当前幕告诉导演系统故事现在处于哪个阶段，影响允许揭示和推进目标。",
  "幕结构计划": "幕结构计划描述后续阶段安排，帮助 GM 按阶段推进而不是随机扩张。",
  "导演叙事焦点": "叙事焦点说明近期剧情应该优先服务什么目标，例如调查、关系或危机升级。",
  "导演节奏": "导演节奏限制推进速度，避免过快揭示真相或过慢停滞。",
  "导演护栏": "导演护栏是本剧本的安全边界，会约束 GM 不做破坏设定的展开。",
  "禁止提前揭示": "这些内容必须暂时隐藏，只能通过线索、异常和铺垫逐步接近。",
  "剧情目标最少字数": "GM 会把每回合正文尽量写到这个下限以上，让叙事更充分。",
  "剧情目标最多字数": "GM 会把每回合正文控制在这个范围内，避免单回合过长。",
  "剧情最低字数": "低于这个值通常说明剧情太短，除非当前情境确实很短。",
  "最少段落": "控制正文最少分成几段，影响阅读节奏和场景展开程度。",
  "最多段落": "控制正文最多分成几段，避免过度切碎叙事。",
  "场景标题上限": "控制每回合最多出现几个场景标题，防止正文被标题打散。",
  "重点标记最少": "建议 GM 至少突出几个关键线索或重要对象。",
  "重点标记最多": "限制加粗重点数量，避免整段文本都变成强调。",
  "近期回合片段长度": "控制最近回合原文摘录进入上下文的长度，越长越连贯但越耗 token。",
  "GM 系统提示": "这是额外给 GM 的全局规则，适合写口吻、禁忌、叙事原则和玩法偏好。",
  "生成备注": "生成备注用于记录补充说明，会影响后续剧情生成但不直接展示给玩家。",
  "剧情基调": "剧情基调用于描述故事情绪，会影响每回合文字氛围。",
  "剧情节奏": "剧情节奏用于控制推进速度、紧张度和信息释放密度。",
  "导入设置 JSON": "导入会覆盖当前剧本设定、素材和行动规则，但不复制回合进度或状态。",
  "worldview JSON": "完整世界观 JSON，适合编辑结构化表单没有覆盖的世界字段。",
  "script_outline JSON": "完整剧本 JSON，包含创作简报、幕结构、契约、真相、线索和压力。",
  "名称": "名称用于识别这条规则或素材，GM 和界面都会用它作为引用锚点。",
  "类型": "类型决定素材会被归入人物、地点、势力、线索、机制等哪类剧本模块。",
  "优先级": "优先级越高，相关剧情中越容易被选中或更强烈地影响 GM。",
  "可见性": "可见性说明这条素材哪些部分能被玩家知道，哪些只能作为隐藏依据。",
  "持续参与剧情": "开启后，这条素材更容易持续进入上下文，适合核心地点、核心规则和主线对象。",
  "关键词": "关键词用于检索这条素材，玩家行动提到相关词时更容易触发。",
  "触发词": "触发词用于匹配玩家输入，影响素材或行动规则是否进入本回合。",
  "公开信息": "公开信息可以被 GM 转化为玩家可见描述。",
  "GM 隐藏信息": "隐藏信息只用于保持真相一致，不能直接剧透给玩家。",
  "剧情使用内容": "这是 GM 实际参考的完整素材内容，会影响场景、线索、人物和规则。",
  "使用说明": "使用说明告诉 GM 什么时候引用这条素材，以及引用时应避免什么。",
  "启用规则": "关闭后这条行动规则不会再根据玩家输入触发。",
  "行动规则": "行动规则说明命中触发词后 GM 应如何处理这一类行动。"
};

function helpTextForLabel(label: string) {
  return HELP_TEXTS[label] ?? `“${label}”会作为剧本设定的一部分影响后续剧情生成、上下文注入或界面展示。`;
}

const DEFAULT_GENERATION_SETTINGS: Required<GenerationSettings> = {
  narrative_target_min_chars: 800,
  narrative_target_max_chars: 1200,
  narrative_min_chars: 700,
  paragraph_min: 3,
  paragraph_max: 6,
  scene_heading_max: 1,
  emphasis_min: 2,
  emphasis_max: 4,
  recent_turn_excerpt_chars: 420
};

function normalizeGenerationSettings(
  value: GenerationSettings | null | undefined
): Required<GenerationSettings> {
  const settings = { ...DEFAULT_GENERATION_SETTINGS };
  if (!value) {
    return settings;
  }
  for (const key of Object.keys(settings) as (keyof Required<GenerationSettings>)[]) {
    const numericValue = Number(value[key]);
    if (Number.isFinite(numericValue)) {
      settings[key] = Math.max(0, Math.trunc(numericValue));
    }
  }
  settings.narrative_target_max_chars = Math.max(
    settings.narrative_target_min_chars,
    settings.narrative_target_max_chars
  );
  settings.narrative_min_chars = Math.min(
    settings.narrative_min_chars,
    settings.narrative_target_min_chars
  );
  settings.paragraph_min = Math.max(1, settings.paragraph_min);
  settings.paragraph_max = Math.max(settings.paragraph_min, settings.paragraph_max);
  settings.emphasis_max = Math.max(settings.emphasis_min, settings.emphasis_max);
  return settings;
}

function intField(value: string) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.max(0, parsed);
}

function versionLabel(version: GameSettingVersionRead) {
  const scopeLabel: Record<string, string> = {
    config: "核心设定",
    lore: "剧本素材",
    mode: "行动风格",
    settings_import: "设置导入"
  };
  return scopeLabel[version.scope] ?? version.scope;
}

function versionSummary(version: GameSettingVersionRead) {
  const snapshot = asRecord(version.snapshot_json);
  if (version.scope === "config") {
    const title = pickString(snapshot, ["title"]);
    const genre = pickString(snapshot, ["genre"]);
    return [title, genre].filter(Boolean).join(" · ") || "配置快照";
  }
  if (version.scope === "lore") {
    const title = pickString(snapshot, ["title"]);
    const type = pickString(snapshot, ["type"]);
    const active = snapshot.is_active === false ? "已归档" : "启用";
    return [title, type, active].filter(Boolean).join(" · ") || "剧本素材快照";
  }
  if (version.scope === "mode") {
    const name = pickString(snapshot, ["name"]);
    const active = snapshot.enabled === false ? "停用" : "启用";
    return [name, active].filter(Boolean).join(" · ") || "模式快照";
  }
  if (version.scope === "settings_import") {
    const game = asRecord(snapshot.game);
    return pickString(game, ["title"]) || "设置导入快照";
  }
  return "设定快照";
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
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
