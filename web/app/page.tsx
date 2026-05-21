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

  return (
    <AppShell>
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_24rem]">
        {gamesState.status === "loading" ? (
          <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
            正在读取冒险存档...
          </section>
        ) : gamesState.status === "error" ? (
          <section className="app-alert">{gamesState.message}</section>
        ) : recentGames.length > 0 ? (
          <LauncherHero game={recentGames[0]} />
        ) : (
          <EmptyLauncher />
        )}

        <aside className="app-card app-card-pad grid content-start gap-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">存档列表</h2>
            <Link className="app-button" href="/games">
              全部
            </Link>
          </div>
          <div className="grid gap-3">
            {gamesState.status === "ready" && recentGames.length > 0 ? (
              recentGames.map((game) => <RecentGameCard game={game} key={game.id} compact />)
            ) : (
              <p className="text-sm leading-6 text-[color:var(--muted)]">
                还没有冒险。创建第一场冒险后，这里会显示最近存档。
              </p>
            )}
          </div>
          <Link className="app-button app-button-primary" href="/games/new">
            创建新冒险
          </Link>
          <Link className="app-button" href="/settings">
            DeepSeek 设置
          </Link>
          <SystemStatus health={health} />
        </aside>
      </section>
    </AppShell>
  );
}

function LauncherHero({ game }: { game: GameListItem }) {
  return (
    <section className="relative overflow-hidden rounded-lg border border-[color:var(--border)] bg-[linear-gradient(120deg,rgba(12,17,15,0.96),rgba(33,46,39,0.88),rgba(93,73,42,0.58))] p-5 shadow-[var(--shadow)] sm:p-7 lg:min-h-[24rem]">
      <div className="pointer-events-none absolute inset-y-8 right-6 hidden w-72 rounded-lg border border-[color:var(--border)] bg-[linear-gradient(rgba(217,179,111,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(217,179,111,0.12)_1px,transparent_1px)] bg-[length:32px_32px] opacity-70 lg:block" />
      <div className="relative z-10 grid min-h-[20rem] content-between gap-8">
        <div>
          <p className="text-sm font-bold text-[color:var(--gold)]">当前冒险 · 最近存档</p>
          <h1 className="mt-3 max-w-3xl break-words text-4xl font-black leading-none sm:text-6xl">
            {game.title}
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-[color:var(--muted)]">
            {game.description || "继续这段尚未完成的文字 RPG。"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="app-pill">{game.genre || "未分类"}</span>
          <span className="app-pill">{game.status}</span>
          <span className="app-pill">更新于 {formatDate(game.updated_at)}</span>
        </div>
        <div className="grid gap-2 sm:flex sm:flex-wrap">
          <Link className="app-button app-button-primary sm:min-w-32" href={`/games/${game.id}/play`}>
            继续冒险
          </Link>
          <Link className="app-button sm:min-w-28" href={`/games/${game.id}/characters`}>
            角色档案
          </Link>
          <Link className="app-button sm:min-w-28" href={`/games/${game.id}/history`}>
            旅程记录
          </Link>
        </div>
      </div>
    </section>
  );
}

function EmptyLauncher() {
  return (
    <section className="app-card app-card-pad grid min-h-[20rem] content-center gap-4">
      <div>
        <p className="text-sm font-bold text-[color:var(--gold)]">RPGForge</p>
        <h1 className="mt-2 text-3xl font-black sm:text-5xl">开始第一场冒险</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[color:var(--muted)]">
          输入一个世界想法，确认设定后生成剧本设定、角色、状态和初始剧情。
        </p>
      </div>
      <Link className="app-button app-button-primary w-full sm:w-fit" href="/games/new">
        创建新冒险
      </Link>
    </section>
  );
}

function RecentGameCard({
  compact = false,
  game
}: {
  compact?: boolean;
  game: GameListItem;
}) {
  return (
    <article className="app-link-card">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="break-words font-semibold">{game.title}</h3>
          {!compact ? (
            <p className="mt-1 line-clamp-2 text-sm leading-6 text-[color:var(--muted)]">
              {game.genre || "未分类"} · {game.description || "暂无简介"}
            </p>
          ) : null}
        </div>
        <span className="app-pill">{game.status}</span>
      </div>
      <div className="mt-2 grid gap-2 sm:flex sm:items-center sm:justify-between">
        <p className="text-xs text-[color:var(--muted)]">
          更新于 {formatDate(game.updated_at)}
        </p>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Link className="app-button app-button-primary" href={`/games/${game.id}/play`}>
            继续冒险
          </Link>
          <Link className="app-button" href={`/games/${game.id}`}>
            概览
          </Link>
        </div>
      </div>
    </article>
  );
}

function SystemStatus({ health }: { health: HealthState }) {
  return (
    <div className="border-t border-[color:var(--border)] pt-3 text-sm">
      <div className="flex items-center gap-2">
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            health.status === "online"
              ? "bg-[color:var(--success)]"
              : health.status === "offline"
                ? "bg-[color:var(--warning)]"
                : "bg-[color:var(--muted)]"
          }`}
        />
        <span className="font-medium">{formatHealthStatus(health)}</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-[color:var(--muted)]">
        {health.status === "online"
          ? `${health.data.service} · ${health.data.environment}`
          : health.status === "offline"
            ? health.message
            : "正在检查服务连接。"}
      </p>
    </div>
  );
}

function formatHealthStatus(health: HealthState) {
  if (health.status === "online") {
    return "API 在线";
  }
  if (health.status === "offline") {
    return "API 离线";
  }
  return "检查中";
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
