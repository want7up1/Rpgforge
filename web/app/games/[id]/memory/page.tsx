"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChangeEvent, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { JsonBlock } from "@/components/JsonBlock";
import {
  getContextDiagnostic,
  getGame,
  getGameMemory,
  getGameSettingsExport,
  getGameSettingsGuideExport,
  getGameScriptExport,
  getSettingVersions,
  getTurns,
  importGameSettings,
  rebuildGameSummaries,
  restoreSettingVersion,
  updateGameConfig
} from "@/lib/api";
import { downloadBlob } from "@/lib/downloads";
import type {
  ContextDiagnosticRead,
  GameDetail,
  GameMemoryRead,
  GameSettingVersionRead,
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

const STORY_SECTION_GUIDE: { key: string; label: string; help: string }[] = [
  {
    key: "game_profile",
    label: "游戏档案",
    help: "标题、题材、简介和整体基调。会影响列表展示、导出名称，以及 GM 对故事类型和表达气质的第一判断。"
  },
  {
    key: "worldview",
    label: "世界观",
    help: "世界事实、时代舞台、公开信息、隐藏真相、势力和地点。GM 用它保持世界一致，不把隐藏真相提前暴露给玩家。"
  },
  {
    key: "story_core",
    label: "故事核心",
    help: "核心幻想、主线悬念、长期目标、当前幕、必须保留和禁止偏离。它是防止剧情跑偏的最高层剧本承诺。"
  },
  {
    key: "core_characters",
    label: "核心人物",
    help: "主角、关键 NPC、同伴、反派和关系弧。GM 会用它维持人物动机、可见身份、秘密边界和关系推进。"
  },
  {
    key: "act_plan",
    label: "五幕主线",
    help: "每幕目标、必须节点、允许揭示、禁止揭示、完成锚点和转场条件。它决定剧情何时可从当前幕进入下一幕。"
  },
  {
    key: "main_quest_path",
    label: "主线轨迹",
    help: "软主线任务线。它告诉 GM 怎样推进主线，但不强迫玩家立刻离开当前场景或放弃自由探索。"
  },
  {
    key: "core_mechanics",
    label: "核心机制",
    help: "成长、资源、基地、调查、战斗、压力、判定等长期玩法规则。GM 会用它处理行动结果和代价。"
  },
  {
    key: "action_style_rules",
    label: "行动风格规则",
    help: "玩家调查、社交、探索、战斗、潜行等不同做法时的叙事和判定规则。当前回合会按玩家输入匹配其中一条。"
  },
  {
    key: "story_material_library",
    label: "剧本素材库",
    help: "可被当前回合召回的地点、势力、秘密、线索、物品、压力和反转素材。触发词和关键词越清晰，召回越稳定。"
  },
  {
    key: "home_base",
    label: "[地点]",
    help: "长期据点、组织后台、安全屋或移动基地。它影响休整、升级、情报、NPC 服务和长期剧情钩子。"
  },
  {
    key: "hard_rules",
    label: "强制规则",
    help: "最高优先级规则，包括必须遵守、禁止事项、秘密揭露和连续性。GM 运行时不能被临场发挥覆盖。"
  },
  {
    key: "generation_parameters",
    label: "生成参数",
    help: "每回合剧情字数、段落、标题、重点标记和近期回合摘录长度。它影响输出长度、节奏和 token 消耗。"
  }
];

export default function GameMemoryPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedTurnId, setSelectedTurnId] = useState<string>("");
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"summaries" | null>(null);

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
          正在读取剧本设定与记忆...
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
  onRefresh,
  onTurnChange,
  selectedTurnId,
  turns,
  versions
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | null;
  diagnostic: ContextDiagnosticRead | null;
  game: GameDetail;
  memory: GameMemoryRead;
  onRebuildSummaries: () => void;
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
  const storySettings = storySettingsFromGame(game);
  const summaryBuckets = useMemo(() => bucketSummaries(memory.summaries), [memory.summaries]);
  const materialCount = recordArray(storySettings.story_material_library).length;
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
            {materialCount} 条 · 摘要 {memory.summaries.length} 条
          </>
        }
        title={memory.game.title}
      />
      {exportStatus ? <p className="app-status">{exportStatus}</p> : null}
      {exportError ? <p className="app-alert">{exportError}</p> : null}

      <section className="grid grid-cols-3 gap-2 sm:gap-3">
        <Metric label="回合" value={memory.current_turn} />
        <Metric label="剧本素材" value={materialCount} />
        <Metric label="摘要" value={memory.summaries.length} />
      </section>

      <nav className="history-toolbar-group history-toolbar-tabs" aria-label="设定管理">
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
        <CoreSettingsSection diagnostic={diagnostic} game={game} />
      ) : null}
      {activeTab === "settings" ? (
        <UnifiedSettingsSection game={game} key={`settings-${game.config?.updated_at}`} onRefresh={onRefresh} />
      ) : null}
      {activeTab === "versions" ? (
        <VersionHistorySection gameId={memory.game.id} onRefresh={onRefresh} versions={versions} />
      ) : null}

      <details className="surface-panel">
        <summary className="cursor-pointer surface-title">维护与运行诊断</summary>
        <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <MaintenancePanel
            actionError={actionError}
            actionStatus={actionStatus}
            busyAction={busyAction}
            onRebuildSummaries={onRebuildSummaries}
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
  diagnostic,
  game
}: {
  diagnostic: ContextDiagnosticRead | null;
  game: GameDetail;
}) {
  const storySettings = storySettingsFromGame(game);
  const currentAct = currentActFromSettings(storySettings);

  return (
    <section className="surface-panel surface-panel-strong">
      <SectionHeader
        title="核心设定"
        subtitle="这里只读展示当前 story_settings v2 的核心内容；完整修改入口在设置页。"
      />
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <InfoBlock
          help="游戏标题、题材和简介。它决定 GM 对游戏类型与整体基调的初始判断。"
          title="游戏档案"
          value={asRecord(storySettings.game_profile)}
        />
        <InfoBlock
          help="核心幻想、主线悬念、长期目标和防跑偏边界。GM 每回合都会围绕这些承诺行动。"
          title="故事核心"
          value={asRecord(storySettings.story_core)}
        />
        <InfoBlock
          help="当前幕的目标、锚点、揭露限制和转场条件。未完成的必要锚点会延后进入下一幕。"
          title="当前幕"
          value={currentAct}
        />
        <InfoBlock
          help="本回合真正注入 GM 的派生运行视图，用来确认设定是否进入上下文。"
          title="运行视图"
          value={diagnostic?.runtime_story ?? {}}
        />
      </div>
    </section>
  );
}

function UnifiedSettingsSection({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const storySettings = storySettingsFromGame(game);

  return (
    <div className="grid gap-4">
      <SettingsImportExportSection game={game} onRefresh={onRefresh} />
      <StorySettingsOverview storySettings={storySettings} />
      <StorySettingsEditor game={game} onRefresh={onRefresh} />
    </div>
  );
}

function StorySettingsOverview({ storySettings }: { storySettings: Record<string, unknown> }) {
  return (
    <section className="surface-panel">
      <SectionHeader
        title="剧本与运行设定"
        subtitle="这些分区共同构成唯一主设定源。GM 运行时只从它派生当前幕、行动风格、素材召回和输出参数。"
      />
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {STORY_SECTION_GUIDE.map((section) => (
          <article
            className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3"
            key={section.key}
          >
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold">{section.label}</h3>
              <HelpMark text={section.help} />
              <span className="font-mono text-xs text-[color:var(--muted)]">{section.key}</span>
            </div>
            <div className="mt-3 max-h-72 overflow-auto rounded border border-[color:var(--border)]">
              <JsonBlock data={storySettings[section.key] ?? emptyValueForSection(section.key)} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function StorySettingsEditor({
  game,
  onRefresh
}: {
  game: GameDetail;
  onRefresh: () => Promise<void>;
}) {
  const currentSettings = storySettingsFromGame(game);
  const [draft, setDraft] = useState(() => formatJson(currentSettings));
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存 story_settings v2...");
    setError(null);
    try {
      await updateGameConfig(game.id, {
        story_settings_json: parseRecordJson(draft, "story_settings")
      });
      await onRefresh();
      setStatus("story_settings v2 已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存 story_settings 失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setDraft(formatJson(currentSettings));
    setError(null);
    setStatus("已恢复为当前已保存的 story_settings。");
  }

  return (
    <section className="surface-panel surface-panel-strong">
      <SectionHeader
        title="完整 JSON 编辑"
        subtitle="这里可以修改全部设定。导入、导出和保存都只作用于 story_settings，不会改回合历史、当前状态、摘要或存档。"
      />
      <StorySettingsStructureGuide />
      <form className="mt-4 grid gap-4" onSubmit={handleSubmit}>
        <TextareaField
          help="唯一主设定源。修改后保存，GM 下一回合会按新的世界观、人物、五幕、机制、素材、强制规则和生成参数运行。"
          label="story_settings v2 JSON"
          onChange={setDraft}
          rows={30}
          value={draft}
        />
        <div className="flex flex-wrap items-start gap-2">
          <button className="app-button app-button-primary" disabled={saving} type="submit">
            {saving ? "保存中..." : "保存 story_settings"}
          </button>
          <button className="app-button" disabled={saving} onClick={handleReset} type="button">
            恢复当前内容
          </button>
        </div>
        {status ? <p className="app-status">{status}</p> : null}
        {error ? <p className="app-alert">{error}</p> : null}
      </form>
    </section>
  );
}

function StorySettingsStructureGuide() {
  return (
    <div className="mt-4 grid gap-2 text-sm text-[color:var(--muted)] md:grid-cols-2">
      {STORY_SECTION_GUIDE.map((item) => (
        <div
          className="flex items-start gap-2 rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] px-3 py-2"
          key={item.key}
        >
          <span className="font-mono text-[color:var(--foreground)]">{item.key}</span>
          <HelpMark text={item.help} />
          <span>{item.label}</span>
        </div>
      ))}
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
  const [exportingGuide, setExportingGuide] = useState(false);
  const [importing, setImporting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setExporting(true);
    setStatus("正在导出 story_settings JSON...");
    setError(null);
    try {
      const { blob, filename } = await getGameSettingsExport(game.id);
      downloadBlob(blob, filename);
      setStatus("story_settings JSON 已开始下载。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出设置失败。");
      setStatus(null);
    } finally {
      setExporting(false);
    }
  }

  async function handleGuideExport() {
    setExportingGuide(true);
    setStatus("正在生成 story_settings 填写说明...");
    setError(null);
    try {
      const { blob, filename } = await getGameSettingsGuideExport(game.id);
      downloadBlob(blob, filename);
      setStatus("填写说明 Markdown 已开始下载。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "下载填写说明失败。");
      setStatus(null);
    } finally {
      setExportingGuide(false);
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setImporting(true);
    setStatus("正在导入 story_settings JSON...");
    setError(null);
    try {
      const payload = JSON.parse(await file.text()) as unknown;
      await importGameSettings(game.id, payload);
      await onRefresh();
      setStatus("story_settings 已导入并保存。");
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
        title="导入导出"
        subtitle="导出的 JSON 是当前游戏剧本设定源；填写说明是单独 Markdown 文档。两者都不包含回合历史、当前状态、摘要或存档进度。"
      />
      <div className="mt-4 grid gap-3 lg:grid-cols-[auto_1fr] lg:items-center">
        <div className="flex flex-wrap gap-2">
          <button
            className="app-button app-button-primary w-fit"
            disabled={exporting || exportingGuide || importing}
            onClick={handleExport}
            type="button"
          >
            {exporting ? "导出中..." : "导出 story_settings JSON"}
          </button>
          <button
            className="app-button w-fit"
            disabled={exporting || exportingGuide || importing}
            onClick={handleGuideExport}
            type="button"
          >
            {exportingGuide ? "下载中..." : "下载填写说明"}
          </button>
        </div>
        <label className="grid gap-1 text-sm font-medium">
          <SettingLabel
            help="选择符合 rpgforge.story.v2 格式的 JSON 文件。导入会覆盖剧本设定源，但不会触碰存档、回合、摘要或当前状态。"
            label="导入 story_settings JSON"
          />
          <input
            accept="application/json,.json"
            className="app-input"
            disabled={exporting || exportingGuide || importing}
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

function VersionHistorySection({
  gameId,
  onRefresh,
  versions
}: {
  gameId: string;
  onRefresh: () => Promise<void>;
  versions: GameSettingVersionRead[];
}) {
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRestore(versionId: string) {
    setRestoringId(versionId);
    setStatus("正在恢复该版本的 story_settings...");
    setError(null);
    try {
      await restoreSettingVersion(gameId, versionId);
      await onRefresh();
      setStatus("版本已恢复。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复版本失败。");
      setStatus(null);
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <section className="surface-panel">
      <SectionHeader
        title="版本历史"
        subtitle="保存、导入和恢复设置时会记录快照；恢复只影响设定，不影响存档进度。"
      />
      {status ? <p className="app-status mt-3">{status}</p> : null}
      {error ? <p className="app-alert mt-3">{error}</p> : null}
      <div className="mt-4 grid gap-3">
        {versions.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无设置版本。</p>
        ) : (
          versions.map((version) => (
            <article
              className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3"
              key={version.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold">
                    {version.scope} · {version.action}
                  </p>
                  <p className="text-xs text-[color:var(--muted)]">
                    {new Date(version.created_at).toLocaleString()}
                  </p>
                </div>
                <button
                  className="app-button"
                  disabled={restoringId === version.id}
                  onClick={() => handleRestore(version.id)}
                  type="button"
                >
                  {restoringId === version.id ? "恢复中..." : "恢复"}
                </button>
              </div>
              <details className="mt-3">
                <summary className="cursor-pointer text-sm text-[color:var(--muted)]">
                  查看快照
                </summary>
                <div className="mt-2 max-h-96 overflow-auto rounded border border-[color:var(--border)]">
                  <JsonBlock data={version.snapshot_json} />
                </div>
              </details>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function MaintenancePanel({
  actionError,
  actionStatus,
  busyAction,
  onRebuildSummaries
}: {
  actionError: string | null;
  actionStatus: string | null;
  busyAction: "summaries" | null;
  onRebuildSummaries: () => void;
}) {
  return (
    <section className="grid gap-3">
      <SectionHeader
        title="维护"
        subtitle="这里处理上下文摘要等运行辅助数据，不会修改 story_settings。"
      />
      <button
        className="app-button w-fit"
        disabled={busyAction === "summaries"}
        onClick={onRebuildSummaries}
        type="button"
      >
        {busyAction === "summaries" ? "重建中..." : "重建上下文摘要"}
      </button>
      {actionStatus ? <p className="app-status">{actionStatus}</p> : null}
      {actionError ? <p className="app-alert">{actionError}</p> : null}
    </section>
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
    <section className="grid gap-4">
      <SectionHeader
        title="运行诊断"
        subtitle="查看某一回合实际注入 GM 的 story_settings 派生视图。"
      />
      <label className="grid gap-1 text-sm font-medium">
        <SettingLabel
          help="选择一个历史回合后，可以查看当时 GM 收到的当前幕、行动风格、召回素材和摘要。"
          label="诊断回合"
        />
        <select className="app-input" onChange={onTurnChange} value={selectedTurnId}>
          <option value="">选择回合</option>
          {turns.map((turn) => (
            <option key={turn.id} value={turn.id}>
              #{turn.turn_number} · {turn.player_input.slice(0, 36)}
            </option>
          ))}
        </select>
      </label>
      {diagnostic ? (
        <div className="grid gap-3">
          <InfoBlock
            help="本回合根据玩家输入匹配到的行动风格规则，会影响判定方式和叙事侧重点。"
            title="选中的行动风格"
            value={diagnostic.selected_action_style ?? {}}
          />
          <InfoBlock
            help="GM 实际读取的当前剧本运行视图，包含当前幕、未完成锚点、下一幕、主线轨迹、人物、规则和生成参数。"
            title="runtime_story"
            value={diagnostic.runtime_story}
          />
          <InfoBlock
            help="根据玩家输入、当前位置、最近回合和关键词召回的剧本素材。"
            title="相关剧本素材"
            value={diagnostic.related_story_materials}
          />
          <InfoBlock
            help="进入上下文的摘要片段，用来避免越玩上下文越长。"
            title="记忆摘要"
            value={diagnostic.memory_summaries}
          />
        </div>
      ) : (
        <p className="text-sm text-[color:var(--muted)]">暂无可诊断回合。</p>
      )}
    </section>
  );
}

function SummarySection({ buckets }: { buckets: Record<string, SummaryRead[]> }) {
  return (
    <section className="surface-panel">
      <SectionHeader
        title="记忆摘要"
        subtitle="摘要是运行缓存，不属于剧本设定源；它用于压缩上下文和降低 token 消耗。"
      />
      <div className="mt-4 grid gap-3">
        {Object.entries(buckets).length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">暂无摘要。</p>
        ) : (
          Object.entries(buckets).map(([type, summaries]) => (
            <details className="rounded border border-[color:var(--border)] p-3" key={type}>
              <summary className="cursor-pointer text-sm font-semibold">
                {type} · {summaries.length} 条
              </summary>
              <div className="mt-3 grid gap-2">
                {summaries.map((summary) => (
                  <article
                    className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3 text-sm"
                    key={summary.id}
                  >
                    <p className="whitespace-pre-wrap text-[color:var(--foreground)]">
                      {summary.content}
                    </p>
                    {Object.keys(summary.important_facts).length > 0 ? (
                      <div className="mt-2 max-h-64 overflow-auto rounded border border-[color:var(--border)]">
                        <JsonBlock data={summary.important_facts} />
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            </details>
          ))
        )}
      </div>
    </section>
  );
}

function InfoBlock({
  help,
  title,
  value
}: {
  help: string;
  title: string;
  value: unknown;
}) {
  return (
    <article className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <HelpMark text={help} />
      </div>
      <div className="mt-2 max-h-96 overflow-auto rounded border border-[color:var(--border)]">
        <JsonBlock data={value} />
      </div>
    </article>
  );
}

function SectionHeader({
  subtitle,
  title
}: {
  subtitle?: ReactNode;
  title: ReactNode;
}) {
  return (
    <header>
      <h2 className="surface-title">{title}</h2>
      {subtitle ? <p className="mt-1 text-sm text-[color:var(--muted)]">{subtitle}</p> : null}
    </header>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="app-card app-card-pad">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function TextareaField({
  help,
  label,
  onChange,
  rows,
  value
}: {
  help: string;
  label: string;
  onChange: (value: string) => void;
  rows?: number;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      <SettingLabel help={help} label={label} />
      <textarea
        className="app-input min-h-[220px] font-mono text-xs"
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        value={value}
      />
    </label>
  );
}

function SettingLabel({ help, label }: { help: string; label: string }) {
  return (
    <span className="flex items-center gap-2">
      <span>{label}</span>
      <HelpMark text={help} />
    </span>
  );
}

function HelpMark({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        aria-label={text}
        className="flex h-5 w-5 items-center justify-center rounded-full border border-[color:var(--border)] text-xs font-semibold text-[color:var(--muted)] outline-none transition focus:border-[color:var(--accent)] focus:text-[color:var(--accent)] group-hover:border-[color:var(--accent)] group-hover:text-[color:var(--accent)]"
        type="button"
      >
        !
      </button>
      <span className="pointer-events-none absolute left-1/2 top-7 z-20 hidden w-72 -translate-x-1/2 rounded border border-[color:var(--border)] bg-[color:var(--panel)] p-3 text-left text-xs font-normal leading-5 text-[color:var(--foreground)] shadow-xl group-focus-within:block group-hover:block">
        {text}
      </span>
    </span>
  );
}

function tabButtonClass(active: boolean) {
  return active ? "history-toolbar-button active" : "history-toolbar-button";
}

function bucketSummaries(summaries: SummaryRead[]): Record<string, SummaryRead[]> {
  return summaries.reduce<Record<string, SummaryRead[]>>((accumulator, summary) => {
    const key = summary.type || "summary";
    accumulator[key] = [...(accumulator[key] ?? []), summary];
    return accumulator;
  }, {});
}

function storySettingsFromGame(game: GameDetail): Record<string, unknown> {
  return asRecord(game.config?.story_settings);
}

function currentActFromSettings(storySettings: Record<string, unknown>): Record<string, unknown> {
  const core = asRecord(storySettings.story_core);
  const currentActId = stringValue(core.current_act) || "act_1";
  const acts = recordArray(storySettings.act_plan);
  const matched =
    acts.find((act) =>
      [act.id, act.key, act.title, act.name].some((value) => stringValue(value) === currentActId)
    ) ?? acts[0];
  return matched ?? {};
}

function emptyValueForSection(sectionKey: string): unknown {
  return [
    "game_profile",
    "worldview",
    "story_core",
    "home_base",
    "hard_rules",
    "generation_parameters"
  ].includes(sectionKey)
    ? {}
    : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => {
        return !!item && typeof item === "object" && !Array.isArray(item);
      })
    : [];
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseRecordJson(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch (caught) {
    throw new Error(
      `${label} 不是合法 JSON：${caught instanceof Error ? caught.message : "解析失败"}`
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON object。`);
  }
  return parsed as Record<string, unknown>;
}
