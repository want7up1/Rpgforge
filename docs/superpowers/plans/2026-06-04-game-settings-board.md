# 已有剧本设定看板 + 信息架构去重 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给已有剧本一个专属「设定」页（复用生成页的 6 分类看板，可编辑），并重整信息架构——把散在「概览/资料」两页的 story_settings 展示/编辑/导入导出/版本统一到设定页，概览/资料各回归本职、消除重复。

**Architecture:** 纯前端。复用 PR #3 的 `buildBoardModel`/`SettingsBoard`（把生成专属的 diff/锁定 props 改为可选）+ 既有后端端点（`updateGameConfig`/`getSettingVersions`/`restoreSettingVersion`/`importGameSettings`/`getGameSettingsExport`/`getGameSettingsGuideExport`）。无后端改动、无新表、无新 LLM 调用。

**Tech Stack:** Next.js(App Router) + React + TS + Tailwind；vitest（纯函数）。

**设计依据：** `docs/superpowers/specs/2026-06-04-game-settings-board-design.md`

> ⚠️ **依赖**：本计划复用「创建冒险页重设计」（PR #3）落地的看板组件（`web/components/generator/SettingsBoard.tsx` 等 + `web/lib/generatorBoard.ts`）。**必须在 PR #3 合并进 `main` 后，从更新的 `main` 切新分支执行**（如 `feat/game-settings-board`）。若 PR #3 未合并，Task 1 找不到这些组件 → 报 BLOCKED。

---

## 文件结构

**移动（Task 1）**
- `web/components/generator/{SettingsBoard,BoardTabs,BoardBlockGrid,BlockDetailModal,ChangeSummaryBar}.tsx` → `web/components/board/`（这 5 个是「生成」与「已有剧本设定」共用的看板；`ChatDock`/`ChatHistorySheet`/`GenerationProgress` 留在 generator，生成专属）。

**新增**
- `web/app/games/[id]/settings/page.tsx` — 新「设定」页：看板（查看/编辑/删除）+ 三个高级折叠。
- `web/components/settings/SettingsAdvanced.tsx` — 高级折叠区：原始 JSON 编辑 + 导入/导出 + 版本历史（从 `memory/page.tsx` 迁来）。
- `web/components/settings/SettingsOverviewCard.tsx` — 概览页的「设定概览」卡（各分类条数 + 入口）。

**修改**
- `web/lib/generatorBoard.ts` — 导出 `EMPTY_DIFF` 常量（供可选 diff 复用）。
- `web/components/board/SettingsBoard.tsx` — `diff`/`lockedIds`/`onUnlockBlock` 改可选。
- `web/components/board/BlockDetailModal.tsx` — `onUnlock` 改可选，无则不显示「解锁」。
- `web/app/games/new/page.tsx` — 看板 import 路径 generator→board（仅路径）。
- `web/components/GamePageHeader.tsx` — `GameSection` 加 `"settings"`，nav 加「设定」项。
- `web/app/games/[id]/page.tsx` — 概览瘦身：换成 `SettingsOverviewCard`，删 blueprint/素材库/高级诊断。
- `web/app/games/[id]/memory/page.tsx` — 资料瘦身：删 settings/versions tab 内容，保留维护/诊断/摘要。
- `docs/OPTIMIZATION_PLAN.md` — 追加 Round 条目。

---

## Task 1: 看板组件归位 + 可选化生成专属 props

**Files:**
- Move: `web/components/generator/{SettingsBoard,BoardTabs,BoardBlockGrid,BlockDetailModal,ChangeSummaryBar}.tsx` → `web/components/board/`
- Modify: `web/lib/generatorBoard.ts`、`web/components/board/SettingsBoard.tsx`、`web/components/board/BlockDetailModal.tsx`、`web/app/games/new/page.tsx`

- [ ] **Step 1: 移动文件（git mv 保留历史）**

```bash
cd web && mkdir -p components/board
git mv components/generator/SettingsBoard.tsx components/board/SettingsBoard.tsx
git mv components/generator/BoardTabs.tsx components/board/BoardTabs.tsx
git mv components/generator/BoardBlockGrid.tsx components/board/BoardBlockGrid.tsx
git mv components/generator/BlockDetailModal.tsx components/board/BlockDetailModal.tsx
git mv components/generator/ChangeSummaryBar.tsx components/board/ChangeSummaryBar.tsx
```

- [ ] **Step 2: 修内部 import 路径（board 内互相引用 + 生成页）**

`web/components/board/SettingsBoard.tsx` 顶部把 4 个子组件 import 从 `@/components/generator/...` 改成 `@/components/board/...`：

```tsx
import { BoardTabs } from "@/components/board/BoardTabs";
import { BoardBlockGrid } from "@/components/board/BoardBlockGrid";
import { BlockDetailModal } from "@/components/board/BlockDetailModal";
import { ChangeSummaryBar } from "@/components/board/ChangeSummaryBar";
```

`web/app/games/new/page.tsx`：把 `import { SettingsBoard } from "@/components/generator/SettingsBoard";` 改成 `import { SettingsBoard } from "@/components/board/SettingsBoard";`（其余 generator import 不变）。

- [ ] **Step 3: generatorBoard.ts 导出 EMPTY_DIFF**

在 `web/lib/generatorBoard.ts` 的 `diffBoard` 定义之后追加：

```ts
// 「无改动」基线：设定页等不需要改动闪烁的消费方可直接传入。
export const EMPTY_DIFF: BoardDiff = {
  changedCategories: Object.fromEntries(
    BOARD_CATEGORIES.map((c) => [c.id, 0])
  ) as Record<BoardCategoryId, number>,
  changedBlockIds: new Set<string>()
};
```

并把 `web/app/games/new/page.tsx` 里本地定义的 `const EMPTY_DIFF = {...}` 删除，改为从 `@/lib/generatorBoard` import `EMPTY_DIFF`（该文件已 import 其它符号，加进去即可）。

- [ ] **Step 4: 可选化 SettingsBoard 的生成专属 props**

`web/components/board/SettingsBoard.tsx` 的 props 类型把 3 个改可选，并在解构处给默认值。改后 props 段与 body 顶部：

```tsx
import { EMPTY_DIFF } from "@/lib/generatorBoard";
// ...
export function SettingsBoard({
  model,
  diff = EMPTY_DIFF,
  lockedIds = [],
  loading,
  onEditBlock,
  onDeleteBlock,
  onUnlockBlock
}: {
  model: BoardModel;
  diff?: BoardDiff;
  lockedIds?: string[];
  loading: boolean;
  onEditBlock: (block: BoardBlock, fields: BoardField[]) => void;
  onDeleteBlock: (block: BoardBlock) => void;
  onUnlockBlock?: (block: BoardBlock) => void;
}) {
```

把传给 `BlockDetailModal` 的 `onUnlock` 改为条件透传——当 `onUnlockBlock` 存在才传：

```tsx
        <BlockDetailModal
          block={openBlock}
          locked={lockedIds.includes(openBlock.id)}
          onSave={(fields) => { onEditBlock(openBlock, fields); setOpenBlock(null); }}
          onDelete={() => { onDeleteBlock(openBlock); setOpenBlock(null); }}
          onUnlock={
            onUnlockBlock
              ? () => { onUnlockBlock(openBlock); setOpenBlock(null); }
              : undefined
          }
          onClose={() => setOpenBlock(null)}
        />
```

- [ ] **Step 5: BlockDetailModal 的 onUnlock 改可选**

`web/components/board/BlockDetailModal.tsx`：props 里 `onUnlock` 改 `onUnlock?: () => void;`；解锁按钮渲染条件从 `locked ?` 改为 `locked && onUnlock ?`：

```tsx
          {locked && onUnlock ? (
            <button className="app-button" type="button" onClick={onUnlock} title="恢复 AI 最近一次生成的值并解除锁定">
              🔓 解锁 / 恢复 AI 原值
            </button>
          ) : null}
```

- [ ] **Step 6: 验证（生成页不回归）**

Run: `cd web && npm test && npx tsc --noEmit && npm run build`
Expected: vitest 19 passing；tsc 无错；build 通过。生成页功能不变（diff/lock 仍传值，行为同前）。

- [ ] **Step 7: Commit**

```bash
git add -A web/components web/lib/generatorBoard.ts web/app/games/new/page.tsx
git commit -m "refactor(web): 看板组件归位 components/board + 生成专属 props 可选化"
```

---

## Task 2: GamePageHeader 加「设定」导航

**Files:**
- Modify: `web/components/GamePageHeader.tsx:8,21-28`

- [ ] **Step 1: 加 section 类型与 nav 项**

把 `GameSection` 改为：

```tsx
export type GameSection = "overview" | "play" | "settings" | "memory" | "status" | "characters" | "history";
```

在 `gameNavItems` 的 `play` 与 `memory` 之间插入：

```tsx
  { key: "settings", label: "设定", href: (gameId) => `/games/${gameId}/settings` },
```

- [ ] **Step 2: 验证** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/GamePageHeader.tsx && git commit -m "feat(web): 游戏内导航加「设定」项"`

---

## Task 3: SettingsAdvanced 组件（原始 JSON / 导入导出 / 版本历史）

把 `memory/page.tsx` 里的设置子区抽成独立组件，供新设定页使用（资料页随后删除这些）。

**Files:**
- Create: `web/components/settings/SettingsAdvanced.tsx`

- [ ] **Step 1: 写组件（自包含，复用既有 api）**

```tsx
"use client";

import { ChangeEvent, FormEvent, ReactNode, useState } from "react";

import { JsonBlock } from "@/components/JsonBlock";
import {
  getGameSettingsExport,
  getGameSettingsGuideExport,
  importGameSettings,
  restoreSettingVersion,
  updateGameConfig
} from "@/lib/api";
import { downloadBlob } from "@/lib/downloads";
import type { GameDetail, GameSettingVersionRead } from "@/lib/types";

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}
function parseRecordJson(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch (caught) {
    throw new Error(`${label} 不是合法 JSON：${caught instanceof Error ? caught.message : "解析失败"}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON object。`);
  }
  return parsed as Record<string, unknown>;
}
function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function Fold({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="surface-panel">
      <summary className="cursor-pointer surface-title">{title}</summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

export function SettingsAdvanced({
  game,
  versions,
  onRefresh
}: {
  game: GameDetail;
  versions: GameSettingVersionRead[];
  onRefresh: () => Promise<void>;
}) {
  return (
    <div className="grid gap-3">
      <Fold title="高级 · 原始 story_settings JSON">
        <RawJsonEditor game={game} onRefresh={onRefresh} />
      </Fold>
      <Fold title="高级 · 导入 / 导出 / 填写说明">
        <ImportExport game={game} onRefresh={onRefresh} />
      </Fold>
      <Fold title="高级 · 版本历史">
        <VersionHistory gameId={game.id} versions={versions} onRefresh={onRefresh} />
      </Fold>
    </div>
  );
}

function RawJsonEditor({ game, onRefresh }: { game: GameDetail; onRefresh: () => Promise<void> }) {
  const current = asRecord(game.config?.story_settings);
  const [draft, setDraft] = useState(() => formatJson(current));
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存 story_settings...");
    setError(null);
    try {
      await updateGameConfig(game.id, { story_settings_json: parseRecordJson(draft, "story_settings") });
      await onRefresh();
      setStatus("story_settings 已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="grid gap-3" onSubmit={handleSubmit}>
      <p className="surface-subtle">直接编辑整份设定。只作用于 story_settings，不改回合历史/状态/摘要/存档。</p>
      <textarea
        className="app-input min-h-[320px] font-mono text-xs"
        onChange={(e) => setDraft(e.target.value)}
        value={draft}
      />
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary" disabled={saving} type="submit">
          {saving ? "保存中..." : "保存 story_settings"}
        </button>
        <button className="app-button" disabled={saving} type="button" onClick={() => { setDraft(formatJson(current)); setError(null); setStatus("已恢复为当前已保存内容。"); }}>
          恢复当前内容
        </button>
      </div>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
    </form>
  );
}

function ImportExport({ game, onRefresh }: { game: GameDetail; onRefresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(kind: "json" | "guide") {
    setBusy(true);
    setError(null);
    setStatus(kind === "json" ? "正在导出 JSON..." : "正在生成填写说明...");
    try {
      const { blob, filename } =
        kind === "json" ? await getGameSettingsExport(game.id) : await getGameSettingsGuideExport(game.id);
      downloadBlob(blob, filename);
      setStatus("已开始下载。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出失败。");
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setStatus("正在导入...");
    try {
      const payload = JSON.parse(await file.text()) as unknown;
      await importGameSettings(game.id, payload);
      await onRefresh();
      setStatus("已导入并保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导入失败。");
      setStatus(null);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary w-fit" disabled={busy} type="button" onClick={() => download("json")}>导出 JSON</button>
        <button className="app-button w-fit" disabled={busy} type="button" onClick={() => download("guide")}>下载填写说明</button>
      </div>
      <label className="grid gap-1 text-sm font-medium">
        <span>导入 story_settings JSON（覆盖设定，不动存档/回合/状态）</span>
        <input accept="application/json,.json" className="app-input" disabled={busy} onChange={handleImport} type="file" />
      </label>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
    </div>
  );
}

function VersionHistory({
  gameId,
  versions,
  onRefresh
}: {
  gameId: string;
  versions: GameSettingVersionRead[];
  onRefresh: () => Promise<void>;
}) {
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRestore(versionId: string) {
    setRestoringId(versionId);
    setStatus("正在恢复该版本...");
    setError(null);
    try {
      await restoreSettingVersion(gameId, versionId);
      await onRefresh();
      setStatus("版本已恢复。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复失败。");
      setStatus(null);
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div className="grid gap-3">
      <p className="surface-subtle">保存/导入/恢复设定时会记录快照；恢复只影响设定，不影响存档进度。</p>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
      {versions.length === 0 ? (
        <p className="text-sm text-[color:var(--muted)]">暂无设置版本。</p>
      ) : (
        versions.map((version) => (
          <article className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3" key={version.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-semibold">{version.scope} · {version.action}</p>
                <p className="text-xs text-[color:var(--muted)]">{new Date(version.created_at).toLocaleString()}</p>
              </div>
              <button className="app-button" disabled={restoringId === version.id} type="button" onClick={() => handleRestore(version.id)}>
                {restoringId === version.id ? "恢复中..." : "恢复"}
              </button>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-[color:var(--muted)]">查看快照</summary>
              <div className="mt-2 max-h-96 overflow-auto rounded border border-[color:var(--border)]">
                <JsonBlock data={version.snapshot_json} />
              </div>
            </details>
          </article>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 2: 验证** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/settings/SettingsAdvanced.tsx && git commit -m "feat(web): SettingsAdvanced 折叠区(原始JSON/导入导出/版本历史)"`

---

## Task 4: 新「设定」页（看板 + 编辑保存 + 409 + 高级折叠）

**Files:**
- Create: `web/app/games/[id]/settings/page.tsx`

- [ ] **Step 1: 写页面**

```tsx
"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { GamePageHeader } from "@/components/GamePageHeader";
import { SettingsBoard } from "@/components/board/SettingsBoard";
import { SettingsAdvanced } from "@/components/settings/SettingsAdvanced";
import { getGame, getSettingVersions, updateGameConfig } from "@/lib/api";
import {
  buildBoardModel,
  deleteBlock,
  writeBlockFields,
  type BoardBlock,
  type BoardField,
  type BoardModel
} from "@/lib/generatorBoard";
import type { GameDetail, GameSettingVersionRead } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; game: GameDetail; versions: GameSettingVersionRead[] }
  | { status: "error"; message: string };

export default function GameSettingsPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [game, versions] = await Promise.all([getGame(params.id), getSettingVersions(params.id)]);
        if (!controller.signal.aborted) setState({ status: "ready", game, versions });
      } catch (error) {
        if (!controller.signal.aborted)
          setState({ status: "error", message: error instanceof Error ? error.message : "Unknown error" });
      }
    }
    load();
    return () => controller.abort();
  }, [params.id]);

  if (state.status === "loading")
    return (
      <AppShell>
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">正在读取设定...</section>
      </AppShell>
    );
  if (state.status === "error")
    return (
      <AppShell>
        <section className="app-alert">{state.message}</section>
      </AppShell>
    );

  return (
    <AppShell>
      <SettingsView
        game={state.game}
        versions={state.versions}
        onChanged={(game, versions) => setState({ status: "ready", game, versions })}
      />
    </AppShell>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function SettingsView({
  game,
  versions,
  onChanged
}: {
  game: GameDetail;
  versions: GameSettingVersionRead[];
  onChanged: (game: GameDetail, versions: GameSettingVersionRead[]) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const settings = asRecord(game.config?.story_settings);
  const model: BoardModel = useMemo(() => buildBoardModel({ source: "settings", settings }), [settings]);

  async function persist(nextSettings: Record<string, unknown>) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateGameConfig(game.id, { story_settings_json: nextSettings });
      const freshVersions = await getSettingVersions(game.id);
      onChanged(updated, freshVersions);
    } catch (caught) {
      // 回合生成中后端返回 409；其余照常报错。
      const msg = caught instanceof Error ? caught.message : "保存失败。";
      setError(/409|生成中|正在生成|editable/i.test(msg) ? "回合生成中，暂时不能修改设定，请稍后再试。" : msg);
    } finally {
      setSaving(false);
    }
  }

  function handleEditBlock(block: BoardBlock, fields: BoardField[]) {
    void persist(writeBlockFields(settings, block.address, fields));
  }
  function handleDeleteBlock(block: BoardBlock) {
    void persist(deleteBlock(settings, block.address));
  }

  async function handleRefresh() {
    const [fresh, freshVersions] = await Promise.all([getGame(game.id), getSettingVersions(game.id)]);
    onChanged(fresh, freshVersions);
  }

  return (
    <div className="grid gap-4 sm:gap-5">
      <GamePageHeader active="settings" eyebrow="设定" gameId={game.id} title={game.title} subtitle="剧本唯一主设定源" />
      <p className="app-status">
        这里是该剧本「唯一主设定源」。修改只影响后续回合，不改写已发生的剧情/状态；回合生成中不可改。
      </p>
      {error ? <p className="app-alert">{error}</p> : null}
      <SettingsBoard
        model={model}
        loading={saving}
        onEditBlock={handleEditBlock}
        onDeleteBlock={handleDeleteBlock}
      />
      <SettingsAdvanced game={game} versions={versions} onRefresh={handleRefresh} />
    </div>
  );
}
```

- [ ] **Step 2: 验证** — Run: `cd web && npx tsc --noEmit && npm run build` — Expected: 无错；新路由 `/games/[id]/settings` 生成。
- [ ] **Step 3: Commit** — `git add web/app/games/\[id\]/settings/page.tsx && git commit -m "feat(web): 新增已有剧本「设定」页(看板可编辑+高级折叠)"`

---

## Task 5: 概览页瘦身（设定概览卡 + 删 blueprint/素材/诊断）

**Files:**
- Create: `web/components/settings/SettingsOverviewCard.tsx`
- Modify: `web/app/games/[id]/page.tsx`

- [ ] **Step 1: 写设定概览卡**

```tsx
"use client";

import Link from "next/link";

import { buildBoardModel } from "@/lib/generatorBoard";

export function SettingsOverviewCard({
  gameId,
  storySettings
}: {
  gameId: string;
  storySettings: Record<string, unknown>;
}) {
  const model = buildBoardModel({ source: "settings", settings: storySettings });
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
```

- [ ] **Step 2: 概览页改动**

在 `web/app/games/[id]/page.tsx`：

1. import 区：删 `import { JsonBlock } from "@/components/JsonBlock";`、`import { buildGameBlueprint, type StoryBlueprintView } from "@/lib/gameExperience";`；新增 `import { SettingsOverviewCard } from "@/components/settings/SettingsOverviewCard";`。
2. `GameDetailView` 内：删 `const blueprint = buildGameBlueprint(game);`、`const storyMaterials = asRecords(...)`、`const actionStyles = asRecords(...)`、`const featuredMaterials = storyMaterials.slice(0, 6);`（`storyMaterials` 若仅 MetricCard 用，保留它的计数即可：把 MetricCard 的 `value={storyMaterials.length}` 改为 `value={asRecords(storySettings.story_material_library).length}`，并删独立的 `storyMaterials`/`actionStyles`/`featuredMaterials` 三个变量）。
3. 渲染区：把 `<ScriptLockSection blueprint={blueprint} />` 整行替换为 `<SettingsOverviewCard gameId={game.id} storySettings={storySettings} />`。
4. 删除整段「剧本素材库」`<section>`（含 featuredMaterials map，约现行 220–254 行）。
5. 删除整段「高级诊断」`<details>`（含 DiagnosticsPanel + 行动风格规则，约现行 256–281 行）。
6. 删除现在无引用的本地组件与 import：`ScriptLockSection`、`BlueprintCard`、`DiagnosticsPanel` 三个函数定义；若 `JsonBlock`/`buildGameBlueprint`/`StoryBlueprintView` 已无引用则其 import 已在 1 删除。`asRecords`/`asList`/`pickString` 若仍被保留代码使用则保留，否则一并删。

> 注：保留 `StatusSnapshot`（运行态，链到 /status）、`ProgressSaveSection`、「旅程记忆」section、「危险操作」。

- [ ] **Step 3: 验证** — Run: `cd web && npx tsc --noEmit && npm run build` — Expected: 无错（无未使用变量/import 报错）。
- [ ] **Step 4: Commit** — `git add web/components/settings/SettingsOverviewCard.tsx web/app/games/\[id\]/page.tsx && git commit -m "feat(web): 概览瘦身——设定概览卡替换蓝图/素材/诊断"`

---

## Task 6: 资料页瘦身（删 settings/versions，保留记忆/维护/诊断）

**Files:**
- Modify: `web/app/games/[id]/memory/page.tsx`

- [ ] **Step 1: 删除 settings/versions 相关内容**

在 `web/app/games/[id]/memory/page.tsx`：

1. 删 `MemoryView` 里的 tab 机制：`const [activeTab, setActiveTab] = useState<MemoryTab>("core");`、`const tabs = [...]`、`<nav ...>设定管理</nav>` 整块、以及三个 `{activeTab === ... ? <X/> : null}` 渲染（`CoreSettingsSection`/`UnifiedSettingsSection`/`VersionHistorySection`）。`type MemoryTab` 定义删除。
2. 删除这些**仅服务于设置**的本地组件定义：`CoreSettingsSection`、`UnifiedSettingsSection`、`StorySettingsOverview`、`StorySettingsEditor`、`StorySettingsStructureGuide`、`SettingsImportExportSection`、`VersionHistorySection`、常量 `STORY_SECTION_GUIDE`、辅助 `emptyValueForSection`、`currentActFromSettings`。
3. 删除随之无用的 import：`getGameSettingsExport`、`getGameSettingsGuideExport`、`importGameSettings`、`restoreSettingVersion`、`updateGameConfig`、`getSettingVersions`（注意 `getSettingVersions` 在 load/refresh 里也用——见第 4 点，改为不再取 versions）。`GameSettingVersionRead` 类型 import 若无引用一并删。
4. `LoadState` / `load` / `refreshMemory` 去掉 `versions`：`Promise.all` 移除 `getSettingVersions(...)`，`state` 不再带 `versions`，`MemoryView` 不再接收/传 `versions` prop。
5. 保留并继续渲染：`<details>维护与运行诊断`（`MaintenancePanel` + `DiagnosticSection`）、`<SummarySection>`、头部、metrics。保留 `FormEvent` 之外仍被引用的 import；删除变成未使用的 import（如 `FormEvent`、`useMemo` 若仍被 `summaryBuckets` 用则保留 `useMemo`）。

> 目标：资料页只剩「记忆/摘要 + 重建摘要 + 运行诊断」。所有 story_settings 展示/编辑/导入导出/版本已迁到设定页。

- [ ] **Step 2: 验证** — Run: `cd web && npx tsc --noEmit && npm run build` — Expected: 无错、无未使用 import/变量报错。
- [ ] **Step 3: Commit** — `git add web/app/games/\[id\]/memory/page.tsx && git commit -m "refactor(web): 资料页瘦身——移除设定展示/编辑/导入导出/版本(迁至设定页)"`

---

## Task 7: 验证、走查、文档

**Files:**
- Modify: `docs/OPTIMIZATION_PLAN.md`

- [ ] **Step 1: 整体验证**

Run: `cd web && npm test && npx tsc --noEmit && npm run build`
Expected: vitest 19 passing；tsc 干净；build 通过（路由含新 `/games/[id]/settings`）。

- [ ] **Step 2: 重建 web 容器（Docker 不挂源码）**

Run: `docker compose up -d --build web`
然后 `docker images | grep rpgforge-web` 确认构建时间是刚刚（核实真的重建，别只信命令输出）。

- [ ] **Step 3: 手动走查**

1. 导航出现「设定」；点进入 `/games/{id}/settings` 看到 6 分类看板。
2. 改一个角色 block 保存 → 看板刷新为新值；高级·版本历史里出现新快照、可恢复。
3. 回合生成中保存 → 提示「回合生成中，暂时不能修改设定」。
4. 高级折叠：原始 JSON 编辑保存、导出 JSON/填写说明、导入 JSON 均工作。
5. 概览页：无蓝图大段/素材前N/高级诊断 JSON；有「设定概览」条数 +「查看/编辑全部设定 →」入口；存档/旅程记忆/危险操作仍在。
6. 资料页：只剩记忆/摘要 + 重建摘要 + 运行诊断；设定编辑/导入导出/版本已不在此。

- [ ] **Step 4: OPTIMIZATION_PLAN 追加 Round 条目**

在 `docs/OPTIMIZATION_PLAN.md` §0/§1 追加 `### Round N (2026-06-04)`：已有剧本「设定」页（看板可编辑，复用 `components/board/`）+ 信息架构去重（概览/资料瘦身、settings 统一到设定页）。不改历史 Round。

- [ ] **Step 5: Commit** — `git add docs/OPTIMIZATION_PLAN.md && git commit -m "docs: OPTIMIZATION_PLAN 追加设定页+信息架构去重 Round 条目"`

---

## 自审（Self-Review）

**Spec 覆盖：**
- §3 IA 三页职责 → Task 4(设定页)/Task 5(概览瘦身)/Task 6(资料瘦身)/Task 2(导航) ✓
- §4 设定页（看板+编辑 updateGameConfig+409+三折叠）→ Task 4 + Task 3 ✓
- §5 组件归位 components/board + 可选化 props → Task 1 ✓
- §6 概览瘦身（设定概览卡+删 blueprint/素材/诊断）→ Task 5 ✓
- §7 资料瘦身（保留记忆/诊断/摘要）→ Task 6 ✓
- §8 API 全既有、后端零改动 → 全程仅前端 ✓
- §10 测试 → Task 7（vitest 复用 + tsc/build + 走查）✓

**Placeholder 扫描：** 新组件/页给完整代码；概览/资料的删改给精确「删哪些函数/import/section 行段、保留哪些」清单（refactor 删除以精确命名表达，非占位）。

**类型一致性：**
- `SettingsBoard` 可选 props（`diff?`/`lockedIds?`/`onUnlockBlock?`）在 Task1 定义、Task4 只传 `model/loading/onEditBlock/onDeleteBlock` 调用——一致。
- `BlockDetailModal.onUnlock?` Task1 定义、SettingsBoard 条件透传——一致。
- `buildBoardModel({source:"settings",settings})` / `writeBlockFields(settings,address,fields)` / `deleteBlock(settings,address)` 与 Phase A 既有签名一致（Task 4 消费）。
- `updateGameConfig(id,{story_settings_json})`、`getSettingVersions`、`restoreSettingVersion`、`getGameSettingsExport`/`Guide`、`importGameSettings` 均为既有 api.ts 函数（memory 页现用同款）——一致。
- `EMPTY_DIFF` 从 generatorBoard 导出、SettingsBoard 默认值引用——一致。

**依赖一致性：** 计划顶部已声明须在 PR #3 合并后执行；Task 1 的 git mv 目标文件来自 PR #3。
