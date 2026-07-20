"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GameSubpageShell } from "@/components/GameMenu";
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
    <AppShell variant="focus">
      {state.status === "loading" ? (
        <section className="px-panel px-panel-pad text-sm text-[color:var(--muted)]">
          <span className="px-caret" aria-hidden="true" /> 正在读取角色状态…
        </section>
      ) : state.status === "error" ? (
        <section className="px-alert">{state.message}</section>
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
    <GameSubpageShell
      active="status"
      eyebrow="STATUS · 状态"
      gameId={game.id}
      meta={endingLabel ? <span className="px-badge px-badge-amber">{endingLabel}</span> : undefined}
      primaryAction={
        <Link className="px-btn px-btn-primary w-full sm:w-fit" href={`/games/${game.id}/play`}>
          ▸ 继续冒险
        </Link>
      }
      subtitle={protagonist.identity || game.description || "当前档案尚未记录主角身份。"}
      title={protagonist.name || game.title}
    >
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
    </GameSubpageShell>
  );
}

function CharacterPanel({ stateV2 }: { stateV2: StateV2 }) {
  const protagonist = stateV2.protagonist_sheet;

  return (
    <section className="px-panel px-panel-strong px-panel-pad">
      <h2 className="px-heading text-base">主角</h2>
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
    <section className="px-panel px-panel-strong px-panel-pad">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="px-heading text-base">当前局面</h2>
        <span className="px-badge px-badge-bright">第 {scene.turn} 回合</span>
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
          <h3 className="px-label">在场 NPC</h3>
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
    <section className="px-panel px-panel-pad">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="px-heading text-base">当前状态</h2>
        <span className="px-badge">{conditions.length} 项</span>
      </div>
      <div className="mt-4 grid gap-2">
        {conditions.length === 0 ? (
          <EmptyText>没有持续状态。</EmptyText>
        ) : (
          conditions.map((condition) => {
            // 纯文字处境：状态一句话 + 可选补充/来源，无 severity/duration 数字。
            const detail = [condition.status, condition.note].filter(Boolean).join(" · ");
            return (
              <article className="px-card" key={condition.name}>
                <h3 className="font-bold text-[color:var(--phosphor)]">{condition.name}</h3>
                {detail || condition.source ? (
                  <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">
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
    <section className="px-panel px-panel-pad">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="px-heading text-base">NPC 关系</h2>
        <span className="px-badge">{relationships.length} 人</span>
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
    <article className="px-card px-card-green">
      <h3 className="font-bold text-[color:var(--phosphor)]">{relationship.npc}</h3>
      <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">
        {relationship.status || "尚无明确的关系描述。"}
      </p>
      {relationship.note ? (
        <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">
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
      <section className="px-panel px-panel-pad">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="px-heading text-base">任务</h2>
          <span className="px-badge">{active.length} 个进行中</span>
        </div>
        <div className="mt-4 grid gap-3">
          {active.length === 0 ? (
            <EmptyText>暂无进行中的任务。</EmptyText>
          ) : (
            active.map((quest, index) => (
              <article className="px-card px-card-accent" key={`active-${quest.name}-${index}`}>
                <h3 className="font-bold">{quest.name}</h3>
                <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">
                  {quest.objective || quest.status}
                </p>
              </article>
            ))
          )}
        </div>
        {settledQuests.length > 0 ? (
          <details className="px-fold mt-3">
            <summary>已完成 / 已结束（{settledQuests.length}）</summary>
            <div className="grid gap-2 border-t-2 border-[color:var(--border)] pt-3">
              {settledQuests.map(({ quest, outcome }, index) => (
                <article
                  className="px-card"
                  key={`${outcome}-${quest.name}-${index}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-medium text-[color:var(--muted)]">{quest.name}</h3>
                    <span className="px-badge">{outcome === "failed" ? "已失败" : "已完成"}</span>
                  </div>
                  {quest.objective ? (
                    <p className="px-wrap mt-2 text-xs leading-5 text-[color:var(--muted)]">
                      {quest.objective}
                    </p>
                  ) : null}
                </article>
              ))}
            </div>
          </details>
        ) : null}
      </section>

      <section className="px-panel px-panel-pad">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="px-heading text-base">未解线索</h2>
          <span className="px-badge">{stateV2.open_threads.active.length} 条</span>
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
                <article className="px-card" key={`${thread.title}-${thread.source}-${index}`}>
                  <h3 className="font-bold">{thread.title}</h3>
                  {detail ? (
                    <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">
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
    <section className="px-panel px-panel-pad">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="px-heading text-base">已知 NPC</h2>
        <span className="px-badge">{stateV2.npc_registry.length} 人</span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {stateV2.npc_registry.length === 0 ? (
          <EmptyText>暂无已登记 NPC。</EmptyText>
        ) : (
          stateV2.npc_registry.map((npc) => (
            <article className="px-card" key={npc.id || npc.name}>
              <h3 className="font-bold text-[color:var(--phosphor)]">{npc.name}</h3>
              <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">
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
    <article className="px-metric">
      <p className="px-metric-label">{label}</p>
      <p className="px-metric-value">{value}</p>
    </article>
  );
}

function CompactField({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-2 border-[color:var(--border)] bg-[color:var(--input)] p-3">
      <p className="px-label">{label}</p>
      <p className="px-wrap mt-1 text-sm font-medium leading-6">{value}</p>
    </div>
  );
}

function PillList({ values }: { values: string[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {values.map((value) => (
        <span className="px-badge" key={value}>
          {value}
        </span>
      ))}
    </div>
  );
}

function EmptyText({ children }: { children: string }) {
  return <p className="px-empty">{children}</p>;
}
