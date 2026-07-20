"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export type GameSection =
  | "play"
  | "status"
  | "characters"
  | "history"
  | "memory"
  | "settings"
  | "camp";

const gameMenuItems: {
  key: GameSection;
  label: string;
  en: string;
  href: (gameId: string) => string;
}[] = [
  { key: "play", label: "剧情", en: "PLAY", href: (gameId) => `/games/${gameId}/play` },
  { key: "status", label: "状态", en: "STATUS", href: (gameId) => `/games/${gameId}/status` },
  { key: "characters", label: "角色", en: "PARTY", href: (gameId) => `/games/${gameId}/characters` },
  { key: "history", label: "旅程", en: "LOG", href: (gameId) => `/games/${gameId}/history` },
  { key: "memory", label: "记忆", en: "MEMO", href: (gameId) => `/games/${gameId}/memory` },
  { key: "settings", label: "设定", en: "SCRIPT", href: (gameId) => `/games/${gameId}/settings` },
  { key: "camp", label: "营地", en: "CAMP", href: (gameId) => `/games/${gameId}/camp` }
];

export function GameMenu({
  active,
  gameId,
  title
}: {
  active: GameSection | null;
  gameId: string;
  title?: string;
}) {
  return (
    <header className="px-topbar">
      <Link href="/" className="px-brand px-font text-[0.6rem]" title="返回标题画面">
        <span aria-hidden="true" className="text-[color:var(--amber)]">▓▓</span>
        RPGFORGE
      </Link>
      {title ? (
        <span className="min-w-0 truncate text-sm font-bold text-[color:var(--foreground)]">
          {title}
        </span>
      ) : null}
      <nav aria-label="游戏菜单" className="px-menu ml-auto">
        {gameMenuItems.map((item) => (
          <Link
            aria-current={active === item.key ? "page" : undefined}
            className={
              active === item.key ? "px-menu-link px-menu-link-active" : "px-menu-link"
            }
            href={item.href(gameId)}
            key={item.key}
          >
            <span>{item.label}</span>
            <span className="px-menu-en">{item.en}</span>
          </Link>
        ))}
        <Link className="px-menu-link" href="/games" title="离开本局，返回存档列表">
          <span>离开</span>
          <span className="px-menu-en">EXIT</span>
        </Link>
      </nav>
    </header>
  );
}

export function GameSubpageShell({
  active,
  children,
  eyebrow,
  gameId,
  meta,
  primaryAction,
  subtitle,
  title
}: {
  active: GameSection;
  children: ReactNode;
  eyebrow: string;
  gameId: string;
  meta?: ReactNode;
  primaryAction?: ReactNode;
  subtitle?: ReactNode;
  title: string;
}) {
  return (
    <div className="grid gap-4 sm:gap-5">
      <GameMenu active={active} gameId={gameId} />
      <section className="px-panel px-panel-strong px-panel-pad">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
          <div className="min-w-0">
            <p className="px-eyebrow">{eyebrow}</p>
            <h1 className="px-heading mt-2 break-words text-2xl sm:text-3xl">{title}</h1>
            {subtitle ? (
              <p className="px-wrap mt-2 text-sm leading-6 text-[color:var(--muted)]">{subtitle}</p>
            ) : null}
          </div>
          {meta || primaryAction ? (
            <div className="grid min-w-0 gap-2 sm:justify-items-end">
              {meta}
              {primaryAction}
            </div>
          ) : null}
        </div>
      </section>
      {children}
    </div>
  );
}
