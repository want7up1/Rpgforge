"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";

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
  getGameScriptExport,
  getSettingVersions,
  getTurns,
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
  AdvancedConfigJsonDraft,
  LoreDiagnosticRead,
  LoreEntryCreate,
  LoreEntryMemoryRead,
  ModeCreate,
  ModeRead,
  SummaryRead,
  TurnRead
} from "@/lib/types";

type MemoryTab = "core" | "lore" | "modes" | "advanced" | "versions";

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
    setActionStatus("正在重建世界书向量...");
    try {
      const result = await reindexGameLore(params.id);
      await refreshMemory();
      setActionStatus(`世界书向量已重建，更新 ${result.updated}/${result.total} 条。`);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "重建世界书向量失败。");
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
    { key: "lore", label: "世界资料" },
    { key: "modes", label: "模式注入" },
    { key: "advanced", label: "高级指令" },
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
            当前回合 {memory.current_turn} · 历史 {memory.turn_count} 回 · 世界资料{" "}
            {memory.lore_entries.length} 条 · 摘要 {memory.summaries.length} 条
          </>
        }
        title={memory.game.title}
      />
      {exportStatus ? <p className="app-status">{exportStatus}</p> : null}
      {exportError ? <p className="app-alert">{exportError}</p> : null}

      <section className="grid grid-cols-3 gap-2 sm:gap-3">
        <Metric label="回合" value={memory.current_turn} />
        <Metric label="世界资料" value={memory.lore_entries.length} />
        <Metric label="摘要" value={memory.summaries.length} />
      </section>

      <nav className="history-toolbar-group sm:grid-cols-5" aria-label="设定管理">
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
          onRefresh={onRefresh}
        />
      ) : null}
      {activeTab === "lore" ? (
        <LoreManagerSection
          entries={memory.lore_entries}
          gameId={memory.game.id}
          key={`lore-${memory.lore_entries.map((entry) => entry.updated_at).join("-")}`}
          onRefresh={onRefresh}
        />
      ) : null}
      {activeTab === "modes" ? (
        <ModeManagerSection
          gameId={memory.game.id}
          key={`modes-${game.modes.map((mode) => mode.updated_at).join("-")}`}
          modes={game.modes}
          onRefresh={onRefresh}
        />
      ) : null}
      {activeTab === "advanced" ? (
        <AdvancedSettingsSection
          game={game}
          key={`advanced-${game.updated_at}`}
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
  memory,
  onRefresh
}: {
  contract: ContractView;
  diagnostic: ContextDiagnosticRead | null;
  game: GameDetail;
  memory: GameMemoryRead;
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
    title: game.title,
    genre: game.genre ?? "",
    description: game.description ?? "",
    summary: pickString(worldview, ["summary", "overview", "theme", "setting"]),
    tone: pickString(worldview, ["tone", "mood"]),
    playerFantasy: pickString(campaign, ["player_fantasy", "premise"]),
    centralQuestion: pickString(campaign, ["central_question"]),
    mainGoal:
      pickString(campaign, ["main_goal", "core_goal", "objective", "goal"]) ||
      pickString(currentAct, ["objective", "goal"]) ||
      pickString(campaign, ["premise"]),
    currentAct: pickString(campaign, ["current_act", "act", "stage", "phase"]),
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
    setStatus("正在保存核心设定...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        title: form.title,
        genre: nullableText(form.genre),
        description: nullableText(form.description),
        worldview: {
          summary: nullableText(form.summary),
          tone: nullableText(form.tone),
          genre: nullableText(form.genre),
          key_npcs: textToList(form.keyNpcs),
          conflicts: textToList(form.keyConflicts)
        },
        campaign_contract: {
          player_fantasy: nullableText(form.playerFantasy),
          central_question: nullableText(form.centralQuestion),
          main_goal: nullableText(form.mainGoal),
          current_act: nullableText(form.currentAct),
          key_npcs: textToList(form.keyNpcs),
          key_conflicts: textToList(form.keyConflicts),
          must_preserve: textToList(form.mustPreserve),
          must_not_become: textToList(form.mustNotBecome),
          forbidden_drift: textToList(form.forbiddenDrift)
        },
        story_contract: {
          narrative_style: nullableText(form.narrativeStyle),
          tone: nullableText(form.tone)
        }
      });
      await onRefresh();
      setStatus("核心设定已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存核心设定失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-panel surface-panel-strong">
      <SectionHeader
        title="核心设定"
        subtitle="这些设定会直接进入剧情导演和 GM 上下文，影响之后的剧情方向。"
      />
      <ContractSection contract={contract} />
      <BlueprintReadOnlySection script={script} />
      <MechanicsOverviewSection
        diagnostic={diagnostic}
        entries={memory.lore_entries}
        game={game}
        modes={game.modes}
      />
      <form className="mt-5 grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-3 lg:grid-cols-3">
          <TextField label="标题" value={form.title} onChange={(title) => setForm({ ...form, title })} />
          <TextField label="题材" value={form.genre} onChange={(genre) => setForm({ ...form, genre })} />
          <TextField label="当前幕" value={form.currentAct} onChange={(currentAct) => setForm({ ...form, currentAct })} />
        </div>
        <TextareaField label="简介" value={form.description} onChange={(description) => setForm({ ...form, description })} />
        <TextareaField label="世界观摘要" value={form.summary} onChange={(summary) => setForm({ ...form, summary })} />
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="核心幻想" value={form.playerFantasy} onChange={(playerFantasy) => setForm({ ...form, playerFantasy })} />
          <TextareaField label="核心悬念" value={form.centralQuestion} onChange={(centralQuestion) => setForm({ ...form, centralQuestion })} />
          <TextareaField label="主线目标" value={form.mainGoal} onChange={(mainGoal) => setForm({ ...form, mainGoal })} />
          <TextareaField label="叙事风格" value={form.narrativeStyle} onChange={(narrativeStyle) => setForm({ ...form, narrativeStyle })} />
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          <TextareaField label="关键 NPC / 势力" value={form.keyNpcs} onChange={(keyNpcs) => setForm({ ...form, keyNpcs })} helper="每行一项" />
          <TextareaField label="关键冲突" value={form.keyConflicts} onChange={(keyConflicts) => setForm({ ...form, keyConflicts })} helper="每行一项" />
          <TextareaField label="禁止偏离点" value={form.forbiddenDrift} onChange={(forbiddenDrift) => setForm({ ...form, forbiddenDrift })} helper="每行一项" />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="必须保留" value={form.mustPreserve} onChange={(mustPreserve) => setForm({ ...form, mustPreserve })} helper="每行一项" />
          <TextareaField label="禁止变成" value={form.mustNotBecome} onChange={(mustNotBecome) => setForm({ ...form, mustNotBecome })} helper="每行一项" />
        </div>
        <TextField label="基调" value={form.tone} onChange={(tone) => setForm({ ...form, tone })} />
        <FormActions saving={saving} status={status} error={error} submitLabel="保存核心设定" />
      </form>
    </section>
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
          <h4 className="text-sm font-semibold">核心机制世界资料</h4>
          {activeMechanicEntries.length === 0 ? (
            <p className="mt-3 text-sm text-[color:var(--muted)]">暂无核心机制世界资料。</p>
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
          emptyText={diagnostic ? "当前回合没有常驻注入条目。" : "暂无运行时诊断。"}
          items={alwaysOnRuntime.map((entry) => `${entry.title} · ${entry.type ?? "unknown"}`)}
          title="当前常驻注入"
        />
        <MechanicsListCard
          emptyText={diagnostic ? "当前回合没有相关召回条目。" : "暂无运行时诊断。"}
          items={relatedRuntime.map((entry) => `${entry.title} · 命中 ${entry.matched_terms.length} 项`)}
          title="当前相关召回"
        />
        <MechanicsListCard
          emptyText="暂无启用模式。"
          items={enabledModes.map((mode) => `${mode.name} · ${mode.priority ?? "medium"}`)}
          title="已启用模式注入"
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
      <p className="app-status mt-3">世界资料索引：{embeddedLoreCount}/{loreCount}</p>
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
          {busyAction === "lore" ? "重建中..." : "重建世界资料索引"}
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
          <LoreDiagnosticList label="常驻世界书" entries={diagnostic.always_on_lore} />
          <LoreDiagnosticList label="相关世界书" entries={diagnostic.related_lore} />
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

function LoreManagerSection({
  entries,
  gameId,
  onRefresh
}: {
  entries: LoreEntryMemoryRead[];
  gameId: string;
  onRefresh: () => Promise<void>;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeEntries = entries.filter((entry) => entry.is_active);
  const archivedEntries = entries.filter((entry) => !entry.is_active);

  async function saveLore(payload: LoreEntryCreate, entry?: LoreEntryMemoryRead) {
    setStatus(entry ? "正在保存世界资料..." : "正在新增世界资料...");
    setError(null);
    try {
      if (entry) {
        await updateLoreEntry(gameId, entry.id, payload);
      } else {
        await createLoreEntry(gameId, payload);
      }
      setEditingId(null);
      await onRefresh();
      setStatus(entry ? "世界资料已保存。" : "世界资料已新增。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存世界资料失败。");
      setStatus(null);
    }
  }

  async function archiveEntry(entry: LoreEntryMemoryRead) {
    setStatus("正在归档世界资料...");
    setError(null);
    try {
      await archiveLoreEntry(gameId, entry.id);
      await onRefresh();
      setStatus("世界资料已归档，不会再注入后续剧情。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "归档世界资料失败。");
      setStatus(null);
    }
  }

  async function restoreEntry(entry: LoreEntryMemoryRead) {
    setStatus("正在恢复世界资料...");
    setError(null);
    try {
      await updateLoreEntry(gameId, entry.id, { is_active: true });
      await onRefresh();
      setStatus("世界资料已恢复。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复世界资料失败。");
      setStatus(null);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="世界资料"
        subtitle="世界资料会按常驻和触发词进入后续剧情上下文。归档后保留记录，但不会再注入。"
      />
      <LoreEditor onSubmit={(payload) => saveLore(payload)} />
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
      <div className="mt-5 grid gap-3 lg:grid-cols-2">
        {activeEntries.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无世界资料。</p>
        ) : (
          activeEntries.map((entry) => (
            <article
              className="archive-card archive-card-accent app-long-card"
              key={entry.id}
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-semibold">{entry.title}</h3>
                  <p className="mt-1 text-xs text-[color:var(--muted)]">
                    {entry.type || "unknown"} · {entry.priority || "medium"} ·{" "}
                    {entry.always_on ? "常驻" : "触发"} ·{" "}
                    {entry.embedding_configured ? "已索引" : "未索引"}
                  </p>
                </div>
                <span className="app-pill">
                  启用 · {entry.visibility || "mixed"}
                </span>
              </div>
              {editingId === entry.id ? (
                <LoreEditor entry={entry} onCancel={() => setEditingId(null)} onSubmit={(payload) => saveLore(payload, entry)} />
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
                    <button className="app-button" onClick={() => setEditingId(entry.id)} type="button">
                      编辑
                    </button>
                    <button className="app-button" onClick={() => archiveEntry(entry)} type="button">
                      归档
                    </button>
                  </div>
                </>
              )}
            </article>
          ))
        )}
      </div>
      {archivedEntries.length > 0 ? (
        <details className="mt-4 rounded border border-[color:var(--border)]" open={showArchived}>
          <summary
            className="cursor-pointer px-3 py-2 text-sm font-semibold"
            onClick={() => setShowArchived(!showArchived)}
          >
            已归档世界资料（{archivedEntries.length}）
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

function LoreEditor({
  entry,
  onCancel,
  onSubmit
}: {
  entry?: LoreEntryMemoryRead;
  onCancel?: () => void;
  onSubmit: (payload: LoreEntryCreate) => void;
}) {
  const [form, setForm] = useState({
    title: entry?.title ?? "",
    type: entry?.type ?? "setting",
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
        type: "setting",
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
        常驻注入
      </label>
      <div className="grid gap-3 lg:grid-cols-2">
        <TextareaField label="关键词" value={form.keywords} onChange={(keywords) => setForm({ ...form, keywords })} helper="每行一项" />
        <TextareaField label="触发词" value={form.triggerWords} onChange={(triggerWords) => setForm({ ...form, triggerWords })} helper="每行一项" />
      </div>
      <TextareaField label="公开信息" value={form.publicInfo} onChange={(publicInfo) => setForm({ ...form, publicInfo })} />
      <TextareaField label="GM 隐藏信息" value={form.gmSecret} onChange={(gmSecret) => setForm({ ...form, gmSecret })} />
      <TextareaField label="完整注入内容" value={form.content} onChange={(content) => setForm({ ...form, content })} required />
      <TextareaField label="使用说明" value={form.usageNote} onChange={(usageNote) => setForm({ ...form, usageNote })} />
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary" type="submit">
          {entry ? "保存世界资料" : "新增世界资料"}
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
    setStatus(mode ? "正在保存模式注入..." : "正在新增模式注入...");
    setError(null);
    try {
      if (mode) {
        await updateMode(gameId, mode.id, payload);
      } else {
        await createMode(gameId, payload);
      }
      setEditingId(null);
      await onRefresh();
      setStatus(mode ? "模式注入已保存。" : "模式注入已新增。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存模式注入失败。");
      setStatus(null);
    }
  }

  async function toggleMode(mode: ModeRead) {
    setStatus(mode.enabled ? "正在停用模式..." : "正在启用模式...");
    setError(null);
    try {
      await updateMode(gameId, mode.id, { enabled: !mode.enabled });
      await onRefresh();
      setStatus(mode.enabled ? "模式已停用。" : "模式已启用。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "切换模式失败。");
      setStatus(null);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="模式注入"
        subtitle="模式会根据玩家行动触发不同 GM 指令，例如调查、战斗、社交或潜行。停用后不会再命中。"
      />
      <ModeEditor onSubmit={(payload) => saveMode(payload)} />
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
      <div className="mt-5 grid gap-3 lg:grid-cols-2">
        {modes.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无模式注入。</p>
        ) : (
          modes.map((mode) => (
            <article
              className={`archive-card app-long-card ${mode.enabled ? "archive-card-green" : "opacity-70"}`}
              key={mode.id}
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-semibold">{mode.name}</h3>
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
                      {mode.enabled ? "停用" : "启用"}
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
        启用模式
      </label>
      <TextareaField label="触发词" value={form.triggers} onChange={(triggers) => setForm({ ...form, triggers })} helper="每行一项" />
      <TextareaField label="注入指令" value={form.injection} onChange={(injection) => setForm({ ...form, injection })} required />
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary" type="submit">
          {mode ? "保存模式" : "新增模式"}
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
  const script = asRecord(game.config?.script_outline);
  const campaign = asRecord(script.campaign_contract);
  const director = asRecord(script.director_contract);
  const story = asRecord(script.story_contract);
  const [form, setForm] = useState({
    systemPrompt: game.config?.system_prompt ?? "",
    generationNotes: game.config?.generation_notes ?? "",
    premise: pickString(campaign, ["premise"]),
    canonTerms: listToText(pickList(campaign, ["canon_terms"])),
    actPlan: listToText(pickList(campaign, ["act_plan"])),
    directorFocus: pickString(director, ["narrative_focus", "focus"]),
    directorPacing: pickString(director, ["pacing"]),
    directorGuardrails: listToText(pickList(director, ["guardrails"])),
    forbiddenReveals: listToText(pickList(director, ["forbidden_reveals"])),
    storyTone: pickString(story, ["tone"]),
    storyPacing: pickString(story, ["pacing"])
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存高级指令...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        system_prompt: nullableText(form.systemPrompt),
        generation_notes: nullableText(form.generationNotes),
        campaign_contract: {
          premise: nullableText(form.premise),
          canon_terms: textToList(form.canonTerms),
          act_plan: textToList(form.actPlan)
        },
        director_contract: {
          narrative_focus: nullableText(form.directorFocus),
          pacing: nullableText(form.directorPacing),
          guardrails: textToList(form.directorGuardrails),
          forbidden_reveals: textToList(form.forbiddenReveals)
        },
        story_contract: {
          tone: nullableText(form.storyTone),
          pacing: nullableText(form.storyPacing)
        }
      });
      await onRefresh();
      setStatus("高级指令已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存高级指令失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface-panel surface-panel-strong">
      <SectionHeader
        title="高级指令"
        subtitle="这里用于细调 GM 系统提示、生成备注、导演约束和剧情风格。只影响之后生成的剧情。"
      />
      <form className="mt-4 grid gap-4" onSubmit={handleSubmit}>
        <TextareaField label="GM 系统提示" value={form.systemPrompt} onChange={(systemPrompt) => setForm({ ...form, systemPrompt })} rows={8} />
        <TextareaField label="生成备注" value={form.generationNotes} onChange={(generationNotes) => setForm({ ...form, generationNotes })} rows={5} />
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="剧本前提" value={form.premise} onChange={(premise) => setForm({ ...form, premise })} />
          <TextareaField label="正典词条" value={form.canonTerms} onChange={(canonTerms) => setForm({ ...form, canonTerms })} helper="每行一项" />
        </div>
        <TextareaField label="幕结构计划" value={form.actPlan} onChange={(actPlan) => setForm({ ...form, actPlan })} helper="每行一项" />
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="导演叙事焦点" value={form.directorFocus} onChange={(directorFocus) => setForm({ ...form, directorFocus })} />
          <TextareaField label="导演节奏" value={form.directorPacing} onChange={(directorPacing) => setForm({ ...form, directorPacing })} />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextareaField label="导演护栏" value={form.directorGuardrails} onChange={(directorGuardrails) => setForm({ ...form, directorGuardrails })} helper="每行一项" />
          <TextareaField label="禁止提前揭示" value={form.forbiddenReveals} onChange={(forbiddenReveals) => setForm({ ...form, forbiddenReveals })} helper="每行一项" />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TextField label="剧情基调" value={form.storyTone} onChange={(storyTone) => setForm({ ...form, storyTone })} />
          <TextField label="剧情节奏" value={form.storyPacing} onChange={(storyPacing) => setForm({ ...form, storyPacing })} />
        </div>
        <FormActions saving={saving} status={status} error={error} submitLabel="保存高级指令" />
      </form>
      <AdvancedJsonSection game={game} onRefresh={onRefresh} />
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
    setStatus("正在保存高级 JSON...");
    setError(null);
    try {
      const payload: AdvancedConfigJsonDraft = {
        worldview_json: parseRecordJson(draft.worldviewJson, "worldview"),
        script_outline_json: parseRecordJson(draft.scriptOutlineJson, "script_outline")
      };
      await updateGameConfig(game.id, payload);
      await onRefresh();
      setStatus("高级 JSON 已保存，并已自动保留用户创作简报与内部角色归档字段。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存高级 JSON 失败。");
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
        高级 JSON
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
            {saving ? "保存中..." : "保存高级 JSON"}
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

function SectionHeader({ subtitle, title }: { subtitle: string; title: string }) {
  return (
    <div>
      <h2 className="surface-title">{title}</h2>
      <p className="surface-subtle mt-1">{subtitle}</p>
    </div>
  );
}

function TextField({
  label,
  onChange,
  required = false,
  value
}: {
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      {label}
      <input
        className="app-input"
        onChange={(event) => onChange(event.target.value)}
        required={required}
        value={value}
      />
    </label>
  );
}

function TextareaField({
  helper,
  label,
  onChange,
  required = false,
  rows = 4,
  value
}: {
  helper?: string;
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  rows?: number;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      <span className="flex items-center justify-between gap-2">
        {label}
        {helper ? <span className="text-xs font-normal text-[color:var(--muted)]">{helper}</span> : null}
      </span>
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
      <span className="text-xs font-medium text-[color:var(--muted)]">{label}</span>
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

function tabButtonClass(active: boolean) {
  return active ? "app-button app-button-primary" : "app-button";
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
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
  const rule = pickString(record, ["rule", "description", "content", "effect"]);
  const progression = pickString(record, ["progression", "stage", "track"]);
  const pieces = [name, rule, progression].map((item) => item.trim()).filter(Boolean);
  if (pieces.length > 0) {
    return [pieces.join(" · ")];
  }
  return Object.entries(record)
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${String(item)}`);
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

function versionLabel(version: GameSettingVersionRead) {
  const scopeLabel: Record<string, string> = {
    config: "核心设定",
    lore: "世界资料",
    mode: "模式注入"
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
    return [title, type, active].filter(Boolean).join(" · ") || "世界资料快照";
  }
  if (version.scope === "mode") {
    const name = pickString(snapshot, ["name"]);
    const active = snapshot.enabled === false ? "停用" : "启用";
    return [name, active].filter(Boolean).join(" · ") || "模式快照";
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
