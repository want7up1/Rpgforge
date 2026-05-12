"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { BackButton } from "@/components/BackButton";

export type GameSection = "overview" | "play" | "memory" | "status" | "characters" | "history";

type GamePageHeaderProps = {
  active: GameSection;
  backFallbackHref?: string;
  eyebrow: string;
  gameId: string;
  meta?: ReactNode;
  primaryAction?: ReactNode;
  subtitle?: ReactNode;
  title: string;
};

const gameNavItems: { key: GameSection; label: string; href: (gameId: string) => string }[] = [
  { key: "overview", label: "概览", href: (gameId) => `/games/${gameId}` },
  { key: "play", label: "剧情", href: (gameId) => `/games/${gameId}/play` },
  { key: "memory", label: "资料", href: (gameId) => `/games/${gameId}/memory` },
  { key: "status", label: "状态", href: (gameId) => `/games/${gameId}/status` },
  { key: "characters", label: "角色", href: (gameId) => `/games/${gameId}/characters` },
  { key: "history", label: "历史", href: (gameId) => `/games/${gameId}/history` },
];

export function GamePageHeader({
  active,
  backFallbackHref,
  eyebrow,
  gameId,
  meta,
  primaryAction,
  subtitle,
  title,
}: GamePageHeaderProps) {
  return (
    <section className="game-page-hero">
      <div className="grid gap-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
          <div className="min-w-0">
            <p className="game-page-eyebrow">{eyebrow}</p>
            <h1 className="game-page-title">
              {title}
            </h1>
            {subtitle ? (
              <p className="mt-3 max-w-4xl text-sm leading-6 text-[color:var(--muted)]">
                {subtitle}
              </p>
            ) : null}
          </div>
          {meta || primaryAction ? (
            <div className="grid gap-2 sm:justify-items-end">
              {meta}
              {primaryAction}
            </div>
          ) : null}
        </div>

        <div className="game-page-nav-row">
          <div className="game-nav-back">
            <BackButton fallbackHref={backFallbackHref ?? `/games/${gameId}`} label="返回" />
          </div>
          <nav aria-label="游戏内导航" className="game-nav lg:justify-end">
            {gameNavItems.map((item) => (
              <Link
                aria-current={active === item.key ? "page" : undefined}
                className={
                  active === item.key
                    ? "game-nav-link game-nav-link-active"
                    : "game-nav-link"
                }
                href={item.href(gameId)}
                key={item.key}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </section>
  );
}
