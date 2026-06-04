"use client";

import Link from "next/link";
import { useMemo } from "react";

import { buildBoardModel } from "@/lib/generatorBoard";

export function SettingsOverviewCard({
  gameId,
  storySettings
}: {
  gameId: string;
  storySettings: Record<string, unknown>;
}) {
  const model = useMemo(() => buildBoardModel({ source: "settings", settings: storySettings }), [storySettings]);
  const cats = model.categories.filter((c) => c.blocks.length > 0);
  return (
    <section className="surface-panel surface-panel-strong">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="surface-title">设定概览</h2>
          {cats.map((c) => (
            <span
              className="app-pill"
              key={c.id}
              style={c.tone === "danger" ? { borderColor: "#e0a23d", color: "#b5701f" } : undefined}
            >
              {c.icon} {c.label} {c.blocks.length}
            </span>
          ))}
        </div>
        <Link className="app-button app-button-primary w-full sm:w-fit" href={`/games/${gameId}/settings`}>
          查看 / 编辑全部设定 →
        </Link>
      </div>
    </section>
  );
}
