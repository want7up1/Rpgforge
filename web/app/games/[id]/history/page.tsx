"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { CharacterModal } from "@/components/CharacterModal";
import { GamePageHeader } from "@/components/GamePageHeader";
import { StoryMarkdown } from "@/components/StoryMarkdown";
import { getCharacters, getGame, getTurns } from "@/lib/api";
import type { CharacterRead, GameDetail, TurnRead } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; turns: TurnRead[]; characters: CharacterRead[] }
  | { status: "error"; message: string };

export default function HistoryPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedCharacter, setSelectedCharacter] = useState<CharacterRead | null>(null);

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

  return (
    <AppShell variant="focus">
      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取历史...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <div className="mx-auto grid w-full max-w-3xl gap-4">
          <GamePageHeader
            active="history"
            eyebrow="历史"
            gameId={params.id}
            primaryAction={
              <Link
                className="app-button app-button-primary w-full sm:w-fit"
                href={`/games/${params.id}/play`}
              >
                继续游戏
              </Link>
            }
            subtitle={`共 ${state.turns.length} 个回合`}
            title={state.game.title}
          />

          <section className="grid gap-3">
            <h2 className="text-lg font-semibold">会话历史</h2>
            {state.turns.length === 0 ? (
              <p className="app-card app-card-pad text-sm text-[color:var(--muted)]">
                暂无历史回合。
              </p>
            ) : (
              state.turns.map((turn) => (
                <details
                  className="app-long-card app-card overflow-hidden"
                  key={turn.id}
                  open={turn.id === state.turns[state.turns.length - 1]?.id}
                >
                  <summary className="cursor-pointer px-4 py-3 text-sm">
                    <span className="font-semibold">第 {turn.turn_number} 回合</span>
                    <span className="ml-2 text-[color:var(--muted)]">
                      {turn.model_used || "unknown model"}
                    </span>
                  </summary>
                  <div className="border-t border-[color:var(--border)] p-4 pt-3">
                    <div className="rounded bg-[#f6f2e9] p-3 text-sm leading-6">
                      <div className="font-semibold">玩家行动</div>
                      <p className="mt-1 whitespace-pre-wrap text-[color:var(--muted)]">
                        {turn.player_input}
                      </p>
                    </div>
                    <div className="mt-3 rounded bg-[color:var(--input)] p-3 text-sm leading-7">
                      <div className="font-semibold">剧情</div>
                      <StoryMarkdown
                        characters={state.characters}
                        className="mt-2 text-sm"
                        content={turn.gm_output}
                        onCharacterClick={setSelectedCharacter}
                      />
                    </div>
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
