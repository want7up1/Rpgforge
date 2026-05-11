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
      <section className="app-card app-card-pad">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="text-sm font-medium text-[color:var(--muted)]">RPGForge</p>
            <h1 className="mt-2 max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">
              继续你的 AI 文字冒险
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
              从一个想法生成世界设定，进入回合制剧情，并在资料页回顾长期记忆和世界资料。
            </p>
          </div>
          <div className="app-actions lg:min-w-80">
            <Link className="app-button app-button-primary" href="/games/new">
              新建游戏
            </Link>
            <Link className="app-button" href="/games">
              游戏列表
            </Link>
            <Link className="app-button" href="/settings">
              设置
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="app-card app-card-pad">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">最近游戏</h2>
              <p className="mt-1 text-sm text-[color:var(--muted)]">
                优先进入剧情，详情和资料可以在游戏内随时打开。
              </p>
            </div>
            <Link className="app-button" href="/games">
              查看全部
            </Link>
          </div>

          <div className="mt-4 grid gap-3">
            {gamesState.status === "loading" ? (
              <p className="text-sm text-[color:var(--muted)]">正在读取游戏...</p>
            ) : gamesState.status === "error" ? (
              <p className="app-alert">{gamesState.message}</p>
            ) : recentGames.length === 0 ? (
              <div className="rounded border border-dashed border-[color:var(--border)] p-4">
                <h3 className="font-semibold">还没有游戏</h3>
                <p className="mt-2 text-sm leading-6 text-[color:var(--muted)]">
                  从规则生成器开始，确认设定后创建第一局 RPG。
                </p>
                <Link className="app-button app-button-primary mt-4 w-full sm:w-fit" href="/games/new">
                  打开规则生成器
                </Link>
              </div>
            ) : (
              recentGames.map((game) => <RecentGameCard game={game} key={game.id} />)
            )}
          </div>
        </section>

        <aside className="app-card app-card-pad">
          <h2 className="text-lg font-semibold">运行状态</h2>
          <div className="mt-4 grid gap-3 text-sm">
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
            <p className="text-[color:var(--muted)]">
              {health.status === "online"
                ? `${health.data.service} · ${health.data.environment}`
                : health.status === "offline"
                  ? health.message
                  : "正在检查服务连接。"}
            </p>
            <Link className="app-button" href="/settings">
              管理 DeepSeek 配置
            </Link>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}

function RecentGameCard({ game }: { game: GameListItem }) {
  return (
    <article className="app-link-card">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="break-words font-semibold">{game.title}</h3>
          <p className="mt-1 line-clamp-2 text-sm leading-6 text-[color:var(--muted)]">
            {game.genre || "未分类"} · {game.description || "暂无简介"}
          </p>
        </div>
        <span className="app-pill">{game.status}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:flex sm:items-center sm:justify-between">
        <p className="col-span-2 text-xs text-[color:var(--muted)] sm:col-span-1">
          更新于 {formatDate(game.updated_at)}
        </p>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Link className="app-button app-button-primary" href={`/games/${game.id}/play`}>
            继续
          </Link>
          <Link className="app-button" href={`/games/${game.id}`}>
            详情
          </Link>
        </div>
      </div>
    </article>
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
