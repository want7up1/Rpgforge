"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { getApiBaseUrl, getGames } from "@/lib/api";
import type { GameListItem } from "@/lib/types";

type HealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
  timestamp: string;
};

type HealthState =
  | { status: "loading" }
  | { status: "online"; data: HealthResponse }
  | { status: "offline"; message: string };

type GamesState =
  | { status: "loading" }
  | { status: "ready"; games: GameListItem[] }
  | { status: "error"; message: string };

export default function Home() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const [gamesState, setGamesState] = useState<GamesState>({ status: "loading" });
  const apiUrl = useMemo(() => getApiBaseUrl(), []);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const response = await fetch(`${apiUrl}/health`, {
          signal: controller.signal,
          cache: "no-store"
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = (await response.json()) as HealthResponse;
        if (!controller.signal.aborted) {
          setHealth({ status: "online", data });
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setHealth({
            status: "offline",
            message: error instanceof Error ? error.message : "Unknown error"
          });
        }
      }
    }

    load();

    return () => controller.abort();
  }, [apiUrl]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadGames() {
      try {
        const games = await getGames();
        if (!controller.signal.aborted) {
          setGamesState({ status: "ready", games });
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setGamesState({
            status: "error",
            message: error instanceof Error ? error.message : "读取游戏列表失败。"
          });
        }
      }
    }

    loadGames();

    return () => controller.abort();
  }, []);

  const recentGames =
    gamesState.status === "ready"
      ? [...gamesState.games]
          .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
          .slice(0, 3)
      : [];
  const latestGame = recentGames[0] ?? null;

  return (
    <AppShell variant="title">
      <div className="title-screen">
        <div className="grid w-full max-w-2xl gap-8 px-2">
          <div className="grid gap-3 text-center">
            <p className="px-eyebrow">STATE-DRIVEN AI TEXT RPG</p>
            <h1 className="title-logo">RPG
              <wbr />FORGE</h1>
            <p className="text-xs tracking-[0.35em] text-[color:var(--faint)]">
              — 文 字 冒 险 终 端 —
            </p>
          </div>

          {gamesState.status === "loading" ? (
            <p className="text-center text-sm text-[color:var(--muted)]">
              <span className="px-caret" aria-hidden="true" /> 正在读取存档…
            </p>
          ) : null}
          {gamesState.status === "error" ? (
            <p className="px-alert">{gamesState.message}</p>
          ) : null}

          <nav aria-label="主菜单" className="grid gap-1 border-2 border-[color:var(--border)] bg-[color:var(--panel)] p-2">
            {latestGame ? (
              <Link className="title-menu-item" href={`/games/${latestGame.id}/play`}>
                <span>
                  继续冒险
                  <span className="ml-2 text-xs text-[color:var(--amber)]">
                    ◂ {latestGame.title} ▸
                  </span>
                </span>
              </Link>
            ) : null}
            <Link className="title-menu-item" href="/games/new">
              <span>新的冒险</span>
            </Link>
            <Link className="title-menu-item" href="/games">
              <span>读取存档</span>
            </Link>
            <Link className="title-menu-item" href="/workshop">
              <span>炼金工坊</span>
            </Link>
            <Link className="title-menu-item" href="/settings">
              <span>系统设置</span>
            </Link>
          </nav>

          {recentGames.length > 0 ? (
            <section className="grid gap-2">
              <p className="px-label text-center">最近冒险</p>
              <div className="grid gap-2">
                {recentGames.map((game, index) => (
                  <Link
                    className="save-slot"
                    href={`/games/${game.id}/play`}
                    key={game.id}
                  >
                    <span className="save-slot-index">SLOT {index + 1}</span>
                    <span className="flex flex-wrap items-center gap-2 pr-16">
                      <strong className="min-w-0 break-words">{game.title}</strong>
                      <span className="px-badge">{game.status}</span>
                    </span>
                    <span className="text-xs text-[color:var(--muted)]">
                      {game.genre || "未分类"} · 更新于 {formatDate(game.updated_at)}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ) : gamesState.status === "ready" ? (
            <p className="text-center text-sm text-[color:var(--muted)]">
              还没有任何冒险存档。选择「新的冒险」开始第一局。
            </p>
          ) : null}

          <footer className="flex items-center justify-center gap-2 text-xs text-[color:var(--faint)]">
            <span
              aria-hidden="true"
              className={
                health.status === "online"
                  ? "px-led px-led-on"
                  : health.status === "offline"
                    ? "px-led px-led-off"
                    : "px-led px-led-blink"
              }
            />
            <span>
              {health.status === "online"
                ? `API 在线 · ${health.data.service} · ${health.data.environment}`
                : health.status === "offline"
                  ? `API 离线 · ${health.message}`
                  : "正在检查 API 连接…"}
            </span>
          </footer>
        </div>
      </div>
    </AppShell>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未知时间";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}
