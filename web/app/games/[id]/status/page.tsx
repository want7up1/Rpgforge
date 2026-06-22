"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { getGame } from "@/lib/api";
import {
  getStateV2FromGame,
  threadStatusLabel,
  type ConditionState,
  type QuestItem,
  type RelationshipTrack,
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
  const progress = stateV2.story_progress;
  const activeQuestCount = stateV2.quest_log.active.length;
  const activeThreadCount = stateV2.open_threads.active.length;
  // 结局标记：通关或失败时在状态页顶部提示（与 play 页结局视图呼应）。
  const endingLabel = progress.defeat
    ? "失败结局"
    : progress.campaign_complete
      ? "已通关"
      : "";

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader
        active="status"
        eyebrow="状态"
        gameId={game.id}
        meta={endingLabel ? <span className="app-pill">{endingLabel}</span> : undefined}
        primaryAction={
          <Link className="app-button app-button-primary w-full sm:w-fit" href={`/games/${game.id}/play`}>
            继续冒险
          </Link>
        }
        subtitle={protagonist.identity || game.description || "当前档案尚未记录主角身份。"}
        title={protagonist.name || game.title}
      />

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        <Metric label="状态" value={stateV2.conditions.length} />
        <Metric label="关系" value={stateV2.relationship_tracks.length} />
        <Metric label="任务" value={activeQuestCount} />
        <Metric label="线索" value={activeThreadCount} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <CharacterPanel stateV2={stateV2} />
        <ScenePanel stateV2={stateV2} />
      </section>

      <ConditionsPanel conditions={stateV2.conditions} />
      <RelationshipsPanel relationships={stateV2.relationship_tracks} />
      <QuestThreadPanel stateV2={stateV2} />
      <NpcPanel stateV2={stateV2} />
    </div>
  );
}

function CharacterPanel({ stateV2 }: { stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;

  return (
    <section className="surface-panel surface-panel-strong">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="surface-title">主角</h2>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <CompactField label="姓名" value={protagonist.name || "未记录"} />
        <CompactField label="身份" value={protagonist.identity || "未记录"} />
      </div>
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
  // 显示"本幕已完成/required 总数"，而非全局 completed_anchors（含历史幕）造成的误导。
  const p = progress.current_act_anchor_progress;
  const countLabel =
    p && p.total > 0
      ? `本幕 ${p.done}/${p.total} 锚点`
      : `${progress.completed_anchors.length} 个已完成`;
  const readyLabel = progress.ready_for_next_act ? "可进入下一幕" : "未满足过渡条件";
  return `${countLabel} · ${readyLabel}`;
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
          conditions.map((condition) => {
            // 纯文字处境：状态一句话 + 可选补充/来源，无 severity/duration 数字。
            const detail = [condition.status, condition.note].filter(Boolean).join(" · ");
            return (
              <article className="archive-card" key={condition.name}>
                <h3 className="font-semibold">{condition.name}</h3>
                {detail || condition.source ? (
                  <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
                    {detail}
                    {condition.source ? `${detail ? " · " : ""}来源：${condition.source}` : ""}
                  </p>
                ) : null}
              </article>
            );
          })
        )}
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
  // 纯叙事：status 是一句关系叙述，note 是可选补充，皆为文字、无数值轴。
  return (
    <article className="archive-card archive-card-green">
      <h3 className="font-semibold">{relationship.npc}</h3>
      <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
        {relationship.status || "尚无明确的关系描述。"}
      </p>
      {relationship.note ? (
        <p className="app-wrap-text mt-2 text-sm leading-6 text-[color:var(--muted)]">
          {relationship.note}
        </p>
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
