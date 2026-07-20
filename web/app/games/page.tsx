"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { usePixelDialog } from "@/components/PixelDialog";
import { deleteGame, getGames } from "@/lib/api";
import type { GameListItem } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; games: GameListItem[] }
  | { status: "error"; message: string };

export default function GamesPage() {
  const dialog = usePixelDialog();
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
    const confirmedTitle = await dialog.prompt(
      `删除后无法恢复。请输入游戏标题确认删除：${game.title}`,
      { confirmLabel: "删除", danger: true }
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
          <p className="px-eyebrow">LOAD GAME</p>
          <h1 className="px-heading mt-2 text-3xl sm:text-4xl">冒险存档</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
            选择一个存档槽位继续冒险，或进入营地管理剧本设定、角色与旅程。
          </p>
        </div>
        <Link className="px-btn px-btn-primary" href="/games/new">
          ＋ 新的冒险
        </Link>
      </section>

      {actionError ? <section className="px-alert">{actionError}</section> : null}

      {state.status === "loading" ? (
        <p className="px-status">
          <span className="px-caret" aria-hidden="true" /> 正在读取存档…
        </p>
      ) : state.status === "error" ? (
        <p className="px-alert">{state.message}</p>
      ) : state.games.length === 0 ? (
        <section className="px-empty grid gap-3">
          <p className="text-base font-bold text-[color:var(--foreground)]">存档槽位全空</p>
          <p>输入一个冒险想法，锻造世界后开始第一局文字 RPG。</p>
          <Link className="px-btn px-btn-primary w-fit" href="/games/new">
            ＋ 新的冒险
          </Link>
        </section>
      ) : (
        <section className="grid gap-3">
          {state.games.map((game, index) => (
            <article className="save-slot" key={game.id}>
              <span className="save-slot-index">SLOT {index + 1}</span>
              <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-center">
                <div className="min-w-0 pr-14 lg:pr-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="break-words text-lg font-bold">{game.title}</h2>
                    <span className="px-badge px-badge-bright">{game.status}</span>
                  </div>
                  <p className="px-wrap mt-1.5 text-sm leading-6 text-[color:var(--muted)]">
                    {game.genre || "未分类"} · {game.description || "暂无简介"}
                  </p>
                  <p className="mt-1.5 text-xs text-[color:var(--faint)]">
                    更新于 {formatDate(game.updated_at)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link className="px-btn px-btn-primary" href={`/games/${game.id}/play`}>
                    ▸ 继续
                  </Link>
                  <Link className="px-btn" href={`/games/${game.id}/camp`}>
                    营地
                  </Link>
                  <button
                    className="px-btn px-btn-danger"
                    disabled={deletingId !== null}
                    onClick={() => handleDelete(game)}
                    type="button"
                  >
                    {deletingId === game.id ? "删除中" : "删除"}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}
    </AppShell>
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
