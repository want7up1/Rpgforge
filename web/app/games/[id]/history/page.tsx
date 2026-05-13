"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { CharacterModal } from "@/components/CharacterModal";
import { GamePageHeader } from "@/components/GamePageHeader";
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
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取历史...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <div className="mx-auto grid w-full max-w-5xl gap-4">
          <GamePageHeader
            active="history"
            eyebrow="历史"
            gameId={params.id}
            primaryAction={
              <Link
                className="app-button app-button-primary w-full sm:w-fit"
                href={`/games/${params.id}/play`}
              >
                继续冒险
              </Link>
            }
            subtitle={`共 ${state.turns.length} 个回合`}
            title={state.game.title}
          />

          <section className="surface-panel surface-panel-strong">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="surface-title">会话历史</h2>
              <span className="app-pill">{state.turns.length} 回合</span>
            </div>
            <div className="history-toolbar">
              <div className="history-toolbar-group" aria-label="历史视图">
                <button
                  className={historyControlClass(layoutMode === "turns")}
                  onClick={() => setLayoutMode("turns")}
                  type="button"
                >
                  回合列表
                </button>
                <button
                  className={historyControlClass(layoutMode === "chapters")}
                  onClick={() => setLayoutMode("chapters")}
                  type="button"
                >
                  章节视图
                </button>
              </div>
              {layoutMode === "turns" ? (
                <div className="history-toolbar-group" aria-label="历史显示内容">
                <button
                  className={historyControlClass(viewMode === "all")}
                  onClick={() => setViewMode("all")}
                  type="button"
                >
                  全部
                </button>
                <button
                  className={historyControlClass(viewMode === "actions")}
                  onClick={() => setViewMode("actions")}
                  type="button"
                >
                  只看行动
                </button>
                <button
                  className={historyControlClass(viewMode === "story")}
                  onClick={() => setViewMode("story")}
                  type="button"
                >
                  只看剧情
                </button>
                </div>
              ) : null}
              {layoutMode === "turns" ? (
                <div className="history-toolbar-group" aria-label="历史展开方式">
                <button
                  className={historyControlClass(expandMode === "latest")}
                  onClick={() => setExpandMode("latest")}
                  type="button"
                >
                  最新
                </button>
                <button
                  className={historyControlClass(expandMode === "all")}
                  onClick={() => setExpandMode("all")}
                  type="button"
                >
                  展开全部
                </button>
                <button
                  className={historyControlClass(expandMode === "none")}
                  onClick={() => setExpandMode("none")}
                  type="button"
                >
                  折叠全部
                </button>
                </div>
              ) : null}
            </div>
            {state.turns.length === 0 ? (
              <p className="archive-card text-sm text-[color:var(--muted)]">
                暂无历史回合。
              </p>
            ) : layoutMode === "chapters" ? (
              <ChapterTimeline
                chapters={chapters}
                characters={state.characters}
                onCharacterClick={setSelectedCharacter}
              />
            ) : (
              state.turns.map((turn) => (
                <details
                  className="archive-card archive-card-accent app-long-card mb-3 overflow-hidden"
                  key={turn.id}
                  open={
                    expandMode === "all" ||
                    (expandMode === "latest" && turn.id === state.turns[state.turns.length - 1]?.id)
                  }
                >
                  <summary className="cursor-pointer text-sm">
                    <span className="font-semibold">第 {turn.turn_number} 回合</span>
                    <span className="ml-2 text-[color:var(--muted)]">
                      {turn.model_used || "unknown model"}
                    </span>
                  </summary>
                  <div className="mt-3 border-t border-[color:var(--border)] pt-3">
                    {viewMode !== "story" ? (
                      <div className="archive-card archive-card-green text-sm leading-6">
                        <div className="font-semibold">玩家行动</div>
                        <p className="app-wrap-text mt-1 whitespace-pre-wrap text-[color:var(--muted)]">
                          {turn.player_input}
                        </p>
                      </div>
                    ) : null}
                    {viewMode !== "actions" ? (
                      <div className={viewMode === "story" ? "archive-card text-sm leading-7" : "archive-card mt-3 text-sm leading-7"}>
                        <div className="font-semibold">剧情</div>
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
        </div>
      )}
    </AppShell>
  );
}

function historyControlClass(active: boolean) {
  return active ? "app-button app-button-primary" : "app-button";
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
      <p className="archive-card text-sm text-[color:var(--muted)]">
        暂无可聚合的章节摘要。
      </p>
    );
  }

  return (
    <div className="chapter-timeline">
      {chapters.map((chapter, index) => (
        <details
          className="chapter-card"
          key={chapter.id}
          open={index === chapters.length - 1}
        >
          <summary>
            <span className="chapter-card-title">{chapter.title}</span>
            <span className="chapter-card-range">{chapter.rangeLabel}</span>
          </summary>
          <div className="chapter-card-body">
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
              <div className="chapter-facts">
                <h3>关键事实</h3>
                <ul>
                  {chapter.importantFacts.map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {chapter.turns.length > 0 ? (
              <details className="chapter-related-turns">
                <summary>相关回合（{chapter.turns.length}）</summary>
                <div className="mt-3 grid gap-2">
                  {chapter.turns.map((turn) => (
                    <article className="archive-card archive-card-green text-sm" key={turn.id}>
                      <div className="font-semibold">第 {turn.turn_number} 回合</div>
                      <p className="app-wrap-text mt-1 whitespace-pre-wrap text-[color:var(--muted)]">
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
