"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { deleteGame, getGames } from "@/lib/api";
import type { GameListItem } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; games: GameListItem[] }
  | { status: "error"; message: string };

export default function GamesPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadGames() {
      try {
        const games = await getGames();
        if (!controller.signal.aborted) {
          setState({
            status: "ready",
            games: [...games].sort(
              (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            )
          });
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Unknown error"
          });
        }
      }
    }

    loadGames();

    return () => controller.abort();
  }, []);

  async function handleDelete(game: GameListItem) {
    const confirmedTitle = window.prompt(
      `删除后无法恢复。请输入游戏标题确认删除：${game.title}`
    );
    if (confirmedTitle === null) {
      return;
    }
    if (confirmedTitle !== game.title) {
      setActionError("标题不一致，已取消删除。");
      return;
    }

    setActionError(null);
    setDeletingId(game.id);
    try {
      await deleteGame(game.id);
      setState((current) =>
        current.status === "ready"
          ? { ...current, games: current.games.filter((item) => item.id !== game.id) }
          : current
      );
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "删除游戏失败。");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <AppShell>
      <section className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
        <div>
          <p className="text-sm font-bold uppercase text-[color:var(--gold)]">Adventures</p>
          <h1 className="mt-2 text-3xl font-black sm:text-4xl">冒险存档</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
            选择一局继续剧情，或进入概览查看剧本设定、角色档案和旅程记忆。
          </p>
        </div>
        <Link className="app-button app-button-primary" href="/games/new">
          创建新冒险
        </Link>
      </section>

      {actionError ? <section className="app-alert">{actionError}</section> : null}

      <section className="app-card app-card-pad">
        {state.status === "loading" ? (
          <p className="text-sm text-[color:var(--muted)]">正在读取游戏列表...</p>
        ) : state.status === "error" ? (
          <p className="app-alert">{state.message}</p>
        ) : state.games.length === 0 ? (
          <EmptyGames />
        ) : (
          <div className="grid gap-3">
            {state.games.map((game) => (
              <GameCard
                deleting={deletingId === game.id}
                disabled={deletingId !== null}
                game={game}
                key={game.id}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}

function EmptyGames() {
  return (
    <div className="flex flex-col gap-4 rounded border border-dashed border-[color:var(--border)] p-4 sm:p-6">
      <div>
        <h2 className="text-xl font-semibold">还没有冒险存档</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--muted)]">
          输入一个冒险想法，确认设定后生成世界并开始第一局 RPG。
        </p>
      </div>
      <Link className="app-button app-button-primary sm:w-fit" href="/games/new">
        创建新冒险
      </Link>
    </div>
  );
}

function GameCard({
  deleting,
  disabled,
  game,
  onDelete
}: {
  deleting: boolean;
  disabled: boolean;
  game: GameListItem;
  onDelete: (game: GameListItem) => void;
}) {
  return (
    <article className="app-link-card">
      <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-lg font-semibold">{game.title}</h2>
            <span className="app-pill">{game.status}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
            {game.genre || "未分类"} · {game.description || "暂无简介"}
          </p>
          <p className="mt-2 text-xs text-[color:var(--muted)]">
            更新于 {formatDate(game.updated_at)}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex lg:min-w-48">
          <Link className="app-button app-button-primary" href={`/games/${game.id}/play`}>
            继续冒险
          </Link>
          <Link className="app-button" href={`/games/${game.id}`}>
            概览
          </Link>
          <button
            className="app-button col-span-2 border-[color:var(--danger-border)] text-[color:var(--danger-text)] sm:col-span-1"
            disabled={disabled}
            onClick={() => onDelete(game)}
            type="button"
          >
            {deleting ? "删除中" : "删除"}
          </button>
        </div>
      </div>
    </article>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未知时间";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}
