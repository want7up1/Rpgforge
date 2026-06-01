"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { getGame } from "@/lib/api";
import {
  formatLogEntry,
  getStateV2FromGame,
  ratioPercent,
  relationshipAxes,
  threadStatusLabel,
  type AbilityState,
  type ConditionState,
  type QuestItem,
  type RelationshipTrack,
  type SkillState,
  type StateV2
} from "@/lib/stateV2";
import type { GameDetail } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; stateV2: StateV2 }
  | { status: "error"; message: string };

export default function GameStatusPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const game = await getGame(params.id);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game, stateV2: getStateV2FromGame(game) });
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

  return (
    <AppShell>
      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取角色状态...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <StatusView game={state.game} stateV2={state.stateV2} />
      )}
    </AppShell>
  );
}

function StatusView({ game, stateV2 }: { game: GameDetail; stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;
  const xpPercent = ratioPercent(protagonist.xp, protagonist.next_level_xp);
  const activeQuestCount = stateV2.quest_log.active.length;
  const activeThreadCount = stateV2.open_threads.active.length;

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader
        active="status"
        eyebrow="状态"
        gameId={game.id}
        primaryAction={
          <Link className="app-button app-button-primary w-full sm:w-fit" href={`/games/${game.id}/play`}>
            继续冒险
          </Link>
        }
        subtitle={protagonist.identity || game.description || "当前档案尚未记录主角身份。"}
        title={protagonist.name || game.title}
      />

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        <Metric label="等级" value={`Lv.${protagonist.level}`} />
        <Metric label="总经验" value={protagonist.total_xp} />
        <Metric label="任务" value={activeQuestCount} />
        <Metric label="线索" value={activeThreadCount} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <CharacterPanel stateV2={stateV2} xpPercent={xpPercent} />
        <ScenePanel stateV2={stateV2} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <SkillsPanel skills={stateV2.skills} />
        <div className="grid gap-4">
          <ConditionsPanel conditions={stateV2.conditions} />
          {stateV2.abilities.length > 0 ? (
            <AbilitiesPanel abilities={stateV2.abilities} />
          ) : null}
        </div>
      </section>

      <RelationshipsPanel relationships={stateV2.relationship_tracks} />
      <QuestThreadPanel stateV2={stateV2} />
      <NpcPanel stateV2={stateV2} />
    </div>
  );
}

function CharacterPanel({ stateV2, xpPercent }: { stateV2: StateV2; xpPercent: number }) {
  const protagonist = stateV2.protagonist_sheet;
  const attributeEntries = useMemo(
    () =>
      Object.entries(protagonist.attributes).filter(([, value]) => formatValue(value).length > 0),
    [protagonist.attributes]
  );

  return (
    <section className="surface-panel surface-panel-strong">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">主角</h2>
        <span className="app-pill">Lv.{protagonist.level}</span>
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="font-medium">经验</span>
          <span className="text-[color:var(--muted)]">
            {protagonist.xp}/{protagonist.next_level_xp}
          </span>
        </div>
        <ProgressBar value={xpPercent} className="mt-2" />
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <CompactField label="姓名" value={protagonist.name || "未记录"} />
        <CompactField label="身份" value={protagonist.identity || "未记录"} />
      </div>
      {attributeEntries.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-sm font-semibold">属性</h3>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {attributeEntries.map(([key, value]) => (
              <CompactField key={key} label={key} value={formatValue(value)} />
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ScenePanel({ stateV2 }: { stateV2: StateV2 }) {
  const scene = stateV2.active_scene;
  const storyProgress = stateV2.story_progress;

  return (
    <section className="surface-panel surface-panel-strong">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">当前局面</h2>
        <span className="app-pill">第 {scene.turn} 回合</span>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <CompactField label="当前幕" value={formatStoryProgress(storyProgress)} />
        <CompactField label="幕完成锚点" value={formatAnchorProgress(storyProgress)} />
        <CompactField label="地点" value={scene.location || "未记录"} />
        <CompactField label="时间" value={scene.time || "未记录"} />
        <CompactField label="压力" value={scene.pressure || "暂无"} />
        <CompactField
          label="同行"
          value={stateV2.party.length > 0 ? stateV2.party.join("、") : "暂无"}
        />
      </div>
      {scene.present_npcs.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-sm font-semibold">在场 NPC</h3>
          <PillList values={scene.present_npcs} />
        </div>
      ) : null}
    </section>
  );
}

function formatStoryProgress(progress: StateV2["story_progress"]): string {
  const currentAct = progress.current_act || "未记录";
  const advanceNote =
    progress.last_advance_turn !== null ? `第 ${progress.last_advance_turn} 回合推进` : "";
  return [currentAct, advanceNote].filter(Boolean).join(" · ");
}

function formatAnchorProgress(progress: StateV2["story_progress"]): string {
  const countLabel = `${progress.completed_anchors.length} 个已完成`;
  const readyLabel = progress.ready_for_next_act ? "可进入下一幕" : "未满足过渡条件";
  return `${countLabel} · ${readyLabel}`;
}

function SkillsPanel({ skills }: { skills: SkillState[] }) {
  return (
    <section className="surface-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">技能熟练度</h2>
        <span className="app-pill">{skills.length} 项</span>
      </div>
      <div className="mt-4 grid gap-3">
        {skills.length === 0 ? (
          <EmptyText>尚未记录技能。技能会在剧情中实际使用后出现。</EmptyText>
        ) : (
          skills.map((skill) => (
            <article className="archive-card archive-card-green" key={skill.name}>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="break-words text-sm font-semibold">{skill.name}</h3>
                  <p className="mt-1 text-xs text-[color:var(--muted)]">Lv.{skill.level}</p>
                </div>
                <span className="text-sm font-medium">{skill.mastery}%</span>
              </div>
              <ProgressBar value={skill.mastery} className="mt-3" />
              <p className="mt-2 text-xs text-[color:var(--muted)]">
                {skill.xp}/{skill.next_level_xp} 熟练经验
              </p>
              {skill.recent_events.length > 0 ? (
                <RecentLog entries={skill.recent_events} />
              ) : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function ConditionsPanel({ conditions }: { conditions: ConditionState[] }) {
  return (
    <section className="surface-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">当前状态</h2>
        <span className="app-pill">{conditions.length} 项</span>
      </div>
      <div className="mt-4 grid gap-2">
        {conditions.length === 0 ? (
          <EmptyText>没有持续状态。</EmptyText>
        ) : (
          conditions.map((condition) => (
            <article className="archive-card" key={condition.name}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold">{condition.name}</h3>
                <span className="app-pill">{condition.severity}</span>
              </div>
              <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
                {condition.status}
                {condition.duration ? ` · ${condition.duration}` : ""}
                {condition.source ? ` · 来源：${condition.source}` : ""}
              </p>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function AbilitiesPanel({ abilities }: { abilities: AbilityState[] }) {
  return (
    <section className="surface-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">能力</h2>
        <span className="app-pill">{abilities.length} 项</span>
      </div>
      <div className="mt-4 grid gap-3">
        {abilities.map((ability) => (
          <article className="archive-card archive-card-accent" key={ability.name}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold">{ability.name}</h3>
              <span className="app-pill">Lv.{ability.level}</span>
            </div>
            <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
              {ability.description || ability.status}
            </p>
            <div className="app-wrap-text mt-3 grid gap-2 text-xs text-[color:var(--muted)] sm:grid-cols-2">
              {ability.resource_cost ? <span>消耗：{ability.resource_cost}</span> : null}
              {ability.cooldown ? <span>冷却：{ability.cooldown}</span> : null}
              {ability.usage_note ? <span className="sm:col-span-2">{ability.usage_note}</span> : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function RelationshipsPanel({ relationships }: { relationships: RelationshipTrack[] }) {
  return (
    <section className="surface-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">NPC 关系</h2>
        <span className="app-pill">{relationships.length} 人</span>
      </div>
      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        {relationships.length === 0 ? (
          <EmptyText>尚未形成可记录的 NPC 关系。</EmptyText>
        ) : (
          relationships.map((relationship) => (
            <RelationshipCard key={relationship.npc} relationship={relationship} />
          ))
        )}
      </div>
    </section>
  );
}

function RelationshipCard({ relationship }: { relationship: RelationshipTrack }) {
  const hasQuantifiedAxis = relationshipAxes.some(({ key }) => relationship[key] !== null);

  return (
    <article className="archive-card archive-card-green">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{relationship.npc}</h3>
        {relationship.stage ? <span className="app-pill">{relationship.stage}</span> : null}
      </div>
      {hasQuantifiedAxis ? (
        <div className="mt-4 grid gap-3">
          {relationshipAxes.map(({ key, label }) => (
            <AxisBar key={key} label={label} value={relationship[key] ?? 0} />
          ))}
        </div>
      ) : (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <CompactField label="关系" value={relationship.relationship || "未记录"} />
          <CompactField label="态度" value={relationship.attitude || "未记录"} />
        </div>
      )}
      {relationship.recent_interaction ? (
        <p className="app-wrap-text mt-3 text-sm leading-6 text-[color:var(--muted)]">
          {relationship.recent_interaction}
        </p>
      ) : null}
      {relationship.recent_events.length > 0 ? (
        <RecentLog entries={relationship.recent_events} />
      ) : null}
    </article>
  );
}

function QuestThreadPanel({ stateV2 }: { stateV2: StateV2 }) {
  const { active, completed, failed } = stateV2.quest_log;
  // 已完成 + 已失败合并到次要折叠区，让玩家看到任务史。hidden 桶是剧情伏笔，刻意不展示（展示=剧透）。
  const settledQuests: { quest: QuestItem; outcome: "completed" | "failed" }[] = [
    ...completed.map((quest) => ({ quest, outcome: "completed" as const })),
    ...failed.map((quest) => ({ quest, outcome: "failed" as const }))
  ];

  return (
    <section className="grid gap-4 xl:grid-cols-2">
      <section className="surface-panel">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="surface-title">任务</h2>
          <span className="app-pill">{active.length} 个进行中</span>
        </div>
        <div className="mt-4 grid gap-3">
          {active.length === 0 ? (
            <EmptyText>暂无进行中的任务。</EmptyText>
          ) : (
            active.map((quest, index) => (
              <article className="archive-card archive-card-accent" key={`active-${quest.name}-${index}`}>
                <h3 className="font-semibold">{quest.name}</h3>
                <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
                  {quest.objective || quest.status}
                </p>
              </article>
            ))
          )}
        </div>
        {settledQuests.length > 0 ? (
          <details className="mt-3 rounded border border-[color:var(--border)] bg-[color:var(--input)]">
            <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
              已完成 / 已结束（{settledQuests.length}）
            </summary>
            <div className="grid gap-2 border-t border-[color:var(--border)] p-3">
              {settledQuests.map(({ quest, outcome }, index) => (
                <article
                  className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3"
                  key={`${outcome}-${quest.name}-${index}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-medium text-[color:var(--muted)]">{quest.name}</h3>
                    <span className="app-pill">{outcome === "failed" ? "已失败" : "已完成"}</span>
                  </div>
                  {quest.objective ? (
                    <p className="app-wrap-text mt-2 text-xs leading-5 text-[color:var(--muted)]">
                      {quest.objective}
                    </p>
                  ) : null}
                </article>
              ))}
            </div>
          </details>
        ) : null}
      </section>

      <section className="surface-panel">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="surface-title">未解线索</h2>
          <span className="app-pill">{stateV2.open_threads.active.length} 条</span>
        </div>
        <div className="mt-4 grid gap-3">
          {stateV2.open_threads.active.length === 0 ? (
            <EmptyText>暂无未解线索。</EmptyText>
          ) : (
            stateV2.open_threads.active.map((thread, index) => {
              const statusLabel = threadStatusLabel(thread.status);
              // status 中文映射；无实义时回退到来源，两者皆空则不渲染附注行。
              const detail = [statusLabel, thread.source].filter(Boolean).join(" · ");
              return (
                <article className="archive-card" key={`${thread.title}-${thread.source}-${index}`}>
                  <h3 className="font-semibold">{thread.title}</h3>
                  {detail ? (
                    <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
                      {detail}
                    </p>
                  ) : null}
                </article>
              );
            })
          )}
        </div>
      </section>
    </section>
  );
}

function NpcPanel({ stateV2 }: { stateV2: StateV2 }) {
  return (
    <section className="surface-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">已知 NPC</h2>
        <span className="app-pill">{stateV2.npc_registry.length} 人</span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {stateV2.npc_registry.length === 0 ? (
          <EmptyText>暂无已登记 NPC。</EmptyText>
        ) : (
          stateV2.npc_registry.map((npc) => (
            <article className="archive-card" key={npc.id || npc.name}>
              <h3 className="font-semibold">{npc.name}</h3>
              <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
                {[npc.identity, npc.status, npc.location, npc.relationship || npc.attitude]
                  .filter(Boolean)
                  .join(" · ") || "暂无更多记录。"}
              </p>
            </article>
          ))
        )}
      </div>
    </section>
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

function CompactField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[color:var(--border)] bg-[color:var(--input)] p-3">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="app-wrap-text mt-1 text-sm font-medium leading-6">{value}</p>
    </div>
  );
}

function AxisBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium">{label}</span>
        <span className="text-[color:var(--muted)]">{value}</span>
      </div>
      <ProgressBar value={value} className="mt-1.5" />
    </div>
  );
}

function ProgressBar({ value, className = "" }: { value: number; className?: string }) {
  return (
    <div
      aria-label={`进度 ${value}%`}
      className={`h-2 overflow-hidden rounded-full bg-[color:var(--soft-panel)] ${className}`}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-[color:var(--accent)] transition-[width]"
        style={{ width: `${value}%` }}
      />
    </div>
  );
}

function RecentLog({ entries }: { entries: Record<string, unknown>[] }) {
  return (
    <details className="mt-3 rounded border border-[color:var(--border)] bg-[color:var(--input)]">
      <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">最近变化</summary>
      <div className="grid gap-2 border-t border-[color:var(--border)] p-3">
        {entries.map((entry, index) => (
          <p className="app-wrap-text text-xs leading-5 text-[color:var(--muted)]" key={index}>
            {formatLogEntry(entry)}
          </p>
        ))}
      </div>
    </details>
  );
}

function PillList({ values }: { values: string[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {values.map((value) => (
        <span className="app-pill" key={value}>
          {value}
        </span>
      ))}
    </div>
  );
}

function EmptyText({ children }: { children: string }) {
  return (
    <p className="app-wrap-text rounded border border-dashed border-[color:var(--border)] p-3 text-sm leading-6 text-[color:var(--muted)]">
      {children}
    </p>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(formatValue).filter(Boolean).join("、");
  }
  return "";
}
