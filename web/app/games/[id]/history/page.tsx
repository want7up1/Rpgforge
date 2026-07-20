"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { CharacterModal } from "@/components/CharacterModal";
import { GameSubpageShell } from "@/components/GameMenu";
import { StoryMarkdown } from "@/components/StoryMarkdown";
import { buildChapterViews, type ChapterView } from "@/lib/gameExperience";
import { getCharacters, getGame, getTurns } from "@/lib/api";
import type { CharacterRead, GameDetail, TurnRead } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; turns: TurnRead[]; characters: CharacterRead[] }
  | { status: "error"; message: string };

type HistoryViewMode = "all" | "actions" | "story";
type HistoryExpandMode = "latest" | "all" | "none";
type HistoryLayoutMode = "turns" | "chapters";

export default function HistoryPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedCharacter, setSelectedCharacter] = useState<CharacterRead | null>(null);
  const [viewMode, setViewMode] = useState<HistoryViewMode>("all");
  const [expandMode, setExpandMode] = useState<HistoryExpandMode>("latest");
  const [layoutMode, setLayoutMode] = useState<HistoryLayoutMode>("turns");

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const [game, turns, characters] = await Promise.all([
          getGame(params.id),
          getTurns(params.id),
          getCharacters(params.id)
        ]);
        if (!controller.signal.aborted) {
          setState({ status: "ready", game, turns, characters });
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

  const chapters = useMemo(
    () => (state.status === "ready" ? buildChapterViews(state.game.summaries, state.turns) : []),
    [state]
  );

  return (
    <AppShell variant="focus">
      {state.status === "loading" ? (
        <section className="px-panel px-panel-pad text-sm text-[color:var(--muted)]">
          <span className="px-caret" aria-hidden="true" /> 正在读取旅程图卷…
        </section>
      ) : state.status === "error" ? (
        <section className="px-alert">{state.message}</section>
      ) : (
        <GameSubpageShell
          active="history"
          eyebrow="LOG · 旅程"
          gameId={params.id}
          primaryAction={
            <Link
              className="px-btn px-btn-primary w-full sm:w-fit"
              href={`/games/${params.id}/play`}
            >
              ▸ 继续冒险
            </Link>
          }
          subtitle={`共 ${state.turns.length} 个回合`}
          title={state.game.title}
        >
          <section className="px-panel px-panel-pad">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="px-heading text-base">旅程图卷</h2>
              <span className="px-badge">{state.turns.length} 回合</span>
            </div>
            <div className="mb-4 grid gap-2">
              <div className="flex flex-wrap gap-2" aria-label="历史视图">
                <button
                  className={layoutMode === "turns" ? "px-btn px-btn-primary" : "px-btn"}
                  onClick={() => setLayoutMode("turns")}
                  type="button"
                >
                  回合列表
                </button>
                <button
                  className={layoutMode === "chapters" ? "px-btn px-btn-primary" : "px-btn"}
                  onClick={() => setLayoutMode("chapters")}
                  type="button"
                >
                  章节视图
                </button>
              </div>
              {layoutMode === "turns" ? (
                <div className="flex flex-wrap gap-2" aria-label="历史显示内容">
                  <button
                    className={viewMode === "all" ? "px-btn px-btn-primary" : "px-btn"}
                    onClick={() => setViewMode("all")}
                    type="button"
                  >
                    全部
                  </button>
                  <button
                    className={viewMode === "actions" ? "px-btn px-btn-primary" : "px-btn"}
                    onClick={() => setViewMode("actions")}
                    type="button"
                  >
                    只看行动
                  </button>
                  <button
                    className={viewMode === "story" ? "px-btn px-btn-primary" : "px-btn"}
                    onClick={() => setViewMode("story")}
                    type="button"
                  >
                    只看剧情
                  </button>
                </div>
              ) : null}
              {layoutMode === "turns" ? (
                <div className="flex flex-wrap gap-2" aria-label="历史展开方式">
                  <button
                    className={expandMode === "latest" ? "px-btn px-btn-primary" : "px-btn"}
                    onClick={() => setExpandMode("latest")}
                    type="button"
                  >
                    最新
                  </button>
                  <button
                    className={expandMode === "all" ? "px-btn px-btn-primary" : "px-btn"}
                    onClick={() => setExpandMode("all")}
                    type="button"
                  >
                    展开全部
                  </button>
                  <button
                    className={expandMode === "none" ? "px-btn px-btn-primary" : "px-btn"}
                    onClick={() => setExpandMode("none")}
                    type="button"
                  >
                    折叠全部
                  </button>
                </div>
              ) : null}
            </div>
            {state.turns.length === 0 ? (
              <p className="px-empty">暂无历史回合。</p>
            ) : layoutMode === "chapters" ? (
              <ChapterTimeline
                chapters={chapters}
                characters={state.characters}
                onCharacterClick={setSelectedCharacter}
              />
            ) : (
              state.turns.map((turn) => (
                <details
                  className="px-fold mb-3"
                  key={turn.id}
                  open={
                    expandMode === "all" ||
                    (expandMode === "latest" && turn.id === state.turns[state.turns.length - 1]?.id)
                  }
                >
                  <summary>
                    <span className="font-bold">第 {turn.turn_number} 回合</span>
                    <span className="ml-2 text-xs text-[color:var(--muted)]">
                      {turn.model_used || "unknown model"}
                    </span>
                  </summary>
                  <div className="grid gap-3 border-t-2 border-[color:var(--border)] pt-3">
                    {viewMode !== "story" ? (
                      <div className="px-card px-card-green text-sm leading-6">
                        <div className="px-label">玩家行动</div>
                        <p className="px-wrap mt-1 whitespace-pre-wrap text-[color:var(--muted)]">
                          &gt; {turn.player_input}
                        </p>
                      </div>
                    ) : null}
                    {viewMode !== "actions" ? (
                      <div className="px-card text-sm leading-7">
                        <div className="px-label">剧情</div>
                        <StoryMarkdown
                          characters={state.characters}
                          className="mt-2 text-sm"
                          content={turn.gm_output}
                          onCharacterClick={setSelectedCharacter}
                        />
                      </div>
                    ) : null}
                  </div>
                </details>
              ))
            )}
          </section>
          <CharacterModal
            character={selectedCharacter}
            onClose={() => setSelectedCharacter(null)}
          />
        </GameSubpageShell>
      )}
    </AppShell>
  );
}

function ChapterTimeline({
  chapters,
  characters,
  onCharacterClick
}: {
  chapters: ChapterView[];
  characters: CharacterRead[];
  onCharacterClick: (character: CharacterRead) => void;
}) {
  if (chapters.length === 0) {
    return (
      <p className="px-empty">暂无可聚合的章节摘要。</p>
    );
  }

  return (
    <div className="grid gap-3">
      {chapters.map((chapter, index) => (
        <details
          className="px-fold"
          key={chapter.id}
          open={index === chapters.length - 1}
        >
          <summary>
            <span className="font-bold text-[color:var(--amber)]">{chapter.title}</span>
            <span className="ml-2 text-xs text-[color:var(--muted)]">{chapter.rangeLabel}</span>
          </summary>
          <div className="grid gap-3 border-t-2 border-[color:var(--border)] pt-3">
            {chapter.content ? (
              <StoryMarkdown
                characters={characters}
                className="text-sm"
                content={chapter.content}
                onCharacterClick={onCharacterClick}
              />
            ) : (
              <p className="text-sm text-[color:var(--muted)]">暂无章节摘要。</p>
            )}

            {chapter.importantFacts.length > 0 ? (
              <div className="px-card px-card-green">
                <h3 className="px-label">关键事实</h3>
                <ul className="mt-2 grid gap-1 pl-4 text-sm leading-6 text-[color:var(--muted)]">
                  {chapter.importantFacts.map((fact) => (
                    <li className="px-wrap list-disc" key={fact}>{fact}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {chapter.turns.length > 0 ? (
              <details className="px-fold">
                <summary>相关回合（{chapter.turns.length}）</summary>
                <div className="grid gap-2 border-t-2 border-[color:var(--border)] pt-3">
                  {chapter.turns.map((turn) => (
                    <article className="px-card px-card-green text-sm" key={turn.id}>
                      <div className="font-bold">第 {turn.turn_number} 回合</div>
                      <p className="px-wrap mt-1 whitespace-pre-wrap text-[color:var(--muted)]">
                        {turn.visible_summary || turn.player_input}
                      </p>
                    </article>
                  ))}
                </div>
              </details>
            ) : null}
          </div>
        </details>
      ))}
    </div>
  );
}
