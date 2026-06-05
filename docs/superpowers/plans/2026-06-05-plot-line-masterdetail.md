# 剧情线主从视图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把看板「剧情结构」标签页从通用卡片网格升级为「纲领总览 + 幕大纲 + 幕详情」主从视图，支持字段编辑与增删幕/节点。

**Architecture:** 新增纯函数 `derivePlotView`（从现有 `BoardModel` 派生纲领/幕/节点分组）+ 新组件 `PlotMasterDetail`（布局与交互，复用 `BlockDetailModal` 弹窗）。`SettingsBoard` 在 `activeTab === "plot"` 时用新组件替换 `BoardBlockGrid`，所有写操作复用既有 `onEditBlock / onDeleteBlock / onAddItem` 回调，不碰 diff/写回/后端。

**Tech Stack:** Next.js + React（client component）、TypeScript、Tailwind、vitest（仅纯函数单测，项目无 React 测试库）。

参考设计文档：`docs/superpowers/specs/2026-06-05-plot-line-masterdetail-design.md`

**全局约定（实现者必读）：**
- 所有命令在 `web/` 目录下执行。
- `deriveFields` 会跳过 `id` key，因此幕/节点 block 的 `fields` **不含 id**；幕的稳定标识取自 `block.address.idValue`（= 数据里的 `act.id`，无则 `title`）。节点的 `act_id` 是普通 field（key=`act_id`）。
- 纲领标量块在 **world 分类**，地址 `{ kind: "settingsScalar", path: ["story_core", k] }`（k ∈ premise/core_fantasy/central_mystery/main_goal/emotional_arc/narrative_style），且**无条件建块**（值空也存在）。约束页的 story_core 是 `settingsStringList`，靠 `kind` 区分。

---

## File Structure

- **Create** `web/lib/plotView.ts` —— 纯函数 `derivePlotView` + 辅助 `actKeyOf`，把 `BoardModel` 派生成 `{ overview, acts, unassignedNodes }`。无 React 依赖。
- **Create** `web/lib/plotView.test.ts` —— `derivePlotView` 的 vitest 单测。
- **Create** `web/components/board/PlotMasterDetail.tsx` —— 主从视图组件，复用 `BlockDetailModal`。
- **Modify** `web/components/board/SettingsBoard.tsx` —— `activeTab === "plot"` 时渲染 `PlotMasterDetail`。
- **Modify** `docs/OPTIMIZATION_PLAN.md` —— §1 追加 Round 条目（项目约定）。

---

## Task 1: derivePlotView 纯函数 + 单测

**Files:**
- Create: `web/lib/plotView.ts`
- Test: `web/lib/plotView.test.ts`

- [ ] **Step 1: 写失败测试**

Create `web/lib/plotView.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { buildBoardModel } from "@/lib/generatorBoard";
import { derivePlotView, actKeyOf } from "@/lib/plotView";

const settings = {
  story_core: {
    premise: "占位前提",
    central_mystery: "占位悬念",
    must_preserve: ["占位红线"] // 这是 constraints 的 stringList，不应进 overview
  },
  act_plan: [
    { id: "act_1", title: "第一幕", objective: "目标一" },
    { id: "act_2", title: "第二幕", objective: "目标二" }
  ],
  main_quest_path: [
    { id: "q1", title: "节点一", objective: "o1", act_id: "act_1" },
    { id: "q2", title: "节点二", objective: "o2", act_id: "act_2" },
    { id: "q3", title: "孤儿", objective: "o3", act_id: "act_X" }
  ]
};

function view(s: Record<string, unknown>) {
  return derivePlotView(buildBoardModel({ source: "settings", settings: s }));
}

describe("derivePlotView", () => {
  it("纲领总览只含 story_core 标量（6 个），不含约束的 stringList", () => {
    const v = view(settings);
    expect(v.overview).toHaveLength(6); // 6 个标量块无条件建块
    const premise = v.overview.find((b) => b.fields[0]?.key === "premise");
    expect(premise?.fields[0]?.value).toBe("占位前提");
    // must_preserve 是 settingsStringList，不应出现
    expect(v.overview.some((b) => b.fields[0]?.key === "must_preserve")).toBe(false);
  });

  it("节点按 act_id 分组到对应幕", () => {
    const v = view(settings);
    expect(v.acts).toHaveLength(2);
    expect(actKeyOf(v.acts[0].actBlock)).toBe("act_1");
    expect(v.acts[0].nodes.map((n) => n.title)).toEqual(["节点一"]);
    expect(v.acts[1].nodes.map((n) => n.title)).toEqual(["节点二"]);
  });

  it("act_id 指向不存在的幕 → 进 unassignedNodes", () => {
    const v = view(settings);
    expect(v.unassignedNodes.map((n) => n.title)).toEqual(["孤儿"]);
  });

  it("空 settings：无幕无节点，纲领仍为 6 个占位空块", () => {
    const v = view({});
    expect(v.acts).toEqual([]);
    expect(v.unassignedNodes).toEqual([]);
    expect(v.overview).toHaveLength(6);
  });
});
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `npm run test -- plotView`
Expected: FAIL（`derivePlotView` / `actKeyOf` 未定义，模块不存在）

- [ ] **Step 3: 实现 plotView.ts**

Create `web/lib/plotView.ts`:

```ts
// 剧情线主从视图的纯逻辑：把 BoardModel 派生成「纲领 / 幕(含节点) / 未分配节点」。
// 不依赖 React，便于 vitest 单测（与 generatorBoard.ts 同风格）。
import type { BoardBlock, BoardModel } from "@/lib/generatorBoard";

export type PlotAct = { actBlock: BoardBlock; nodes: BoardBlock[] };
export type PlotView = {
  overview: BoardBlock[];        // 纲领标量块（world 分类的 story_core.*）
  acts: PlotAct[];               // 幕，按 model 顺序，各自挂归属节点
  unassignedNodes: BoardBlock[]; // act_id 为空或指向不存在幕的孤儿节点
};

function fieldValue(block: BoardBlock, key: string): string {
  const f = block.fields.find((x) => x.key === key);
  if (f == null) return "";
  return typeof f.value === "string" ? f.value : f.value == null ? "" : String(f.value);
}

// 幕的稳定标识：settingsItem 地址的 idValue（= act.id 或 title）。
export function actKeyOf(actBlock: BoardBlock): string {
  return actBlock.address.kind === "settingsItem" ? actBlock.address.idValue : actBlock.id;
}

export function derivePlotView(model: BoardModel): PlotView {
  const world = model.categories.find((c) => c.id === "world");
  const plot = model.categories.find((c) => c.id === "plot");

  const overview = (world?.blocks ?? []).filter(
    (b) =>
      b.address.kind === "settingsScalar" &&
      b.address.path.length === 2 &&
      b.address.path[0] === "story_core"
  );

  const actBlocks = (plot?.blocks ?? []).filter(
    (b) => b.address.kind === "settingsItem" && b.address.arrayKey === "act_plan"
  );
  const nodeBlocks = (plot?.blocks ?? []).filter(
    (b) => b.address.kind === "settingsItem" && b.address.arrayKey === "main_quest_path"
  );

  const actKeys = new Set(actBlocks.map(actKeyOf));
  const acts: PlotAct[] = actBlocks.map((actBlock) => {
    const key = actKeyOf(actBlock);
    return {
      actBlock,
      nodes: nodeBlocks.filter((n) => fieldValue(n, "act_id") === key)
    };
  });
  const unassignedNodes = nodeBlocks.filter((n) => {
    const a = fieldValue(n, "act_id");
    return a === "" || !actKeys.has(a);
  });

  return { overview, acts, unassignedNodes };
}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `npm run test -- plotView`
Expected: PASS（4 个测试全绿）

- [ ] **Step 5: Lint**

Run: `npm run lint`
Expected: 无错误

- [ ] **Step 6: Commit**

```bash
git add web/lib/plotView.ts web/lib/plotView.test.ts
git commit -m "feat(plot): derivePlotView 派生纲领/幕/节点分组（含孤儿归类）"
```

---

## Task 2: PlotMasterDetail 组件

**Files:**
- Create: `web/components/board/PlotMasterDetail.tsx`

> 项目无 React 测试库（无 @testing-library），组件不写单测；逻辑已由 Task 1 覆盖。验证靠类型检查 + lint + 手动。

- [ ] **Step 1: 实现组件**

Create `web/components/board/PlotMasterDetail.tsx`:

```tsx
"use client";

import { useState } from "react";

import { BlockDetailModal } from "@/components/board/BlockDetailModal";
import { newItemBlock } from "@/lib/generatorBoard";
import type { BoardBlock, BoardField, BoardModel } from "@/lib/generatorBoard";
import { actKeyOf, derivePlotView } from "@/lib/plotView";

type Adding = "act" | "node" | null;

export function PlotMasterDetail({
  model,
  lockedIds = [],
  changedBlockIds,
  onEditBlock,
  onDeleteBlock,
  onAddItem,
  onUnlockBlock
}: {
  model: BoardModel;
  lockedIds?: string[];
  changedBlockIds?: Set<string>;
  onEditBlock: (block: BoardBlock, fields: BoardField[]) => void;
  onDeleteBlock: (block: BoardBlock) => void;
  onAddItem?: (arrayKey: string, item: Record<string, unknown>) => void;
  onUnlockBlock?: (block: BoardBlock) => void;
}) {
  const { overview, acts, unassignedNodes } = derivePlotView(model);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [openBlock, setOpenBlock] = useState<BoardBlock | null>(null);
  const [adding, setAdding] = useState<Adding>(null);

  const selectedAct = acts.find((a) => actKeyOf(a.actBlock) === selectedKey) ?? acts[0] ?? null;
  const changed = (id: string) => changedBlockIds?.has(id) ?? false;

  function preview(block: BoardBlock, key: string): string {
    const f = block.fields.find((x) => x.key === key);
    return typeof f?.value === "string" ? f.value : "";
  }

  // 新增弹窗用的合成块：新增节点时把 act_id 预填为当前选中幕。
  const addingBlock: BoardBlock | null =
    adding === "act"
      ? newItemBlock("act_plan")
      : adding === "node"
        ? (() => {
            const base = newItemBlock("main_quest_path");
            return {
              ...base,
              fields: [
                ...base.fields,
                {
                  key: "act_id",
                  label: "所属幕",
                  value: selectedAct ? actKeyOf(selectedAct.actBlock) : "",
                  type: "text" as const
                }
              ]
            };
          })()
        : null;

  return (
    <div className="mt-3">
      {/* 顶部：剧情纲领总览 */}
      <section className="surface-panel mb-4">
        <h4 className="surface-title mb-2">🎯 剧情纲领总览</h4>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {overview.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => setOpenBlock(b)}
              className={[
                "rounded-lg border p-3 text-left transition hover:border-[color:var(--foreground)]",
                changed(b.id) ? "border-[#e0533d]" : "border-[color:var(--border)]"
              ].join(" ")}
            >
              <div className="text-xs opacity-60">{b.title}</div>
              <div className="mt-1 text-sm">
                {preview(b, b.fields[0]?.key ?? "") || <span className="opacity-40">（空，点击填写）</span>}
              </div>
            </button>
          ))}
        </div>
      </section>

      <div className="flex flex-col gap-4 md:flex-row md:items-start">
        {/* 左：幕大纲 */}
        <div className="md:w-1/3">
          <div className="mb-2 text-sm font-semibold">幕大纲</div>
          <div className="grid gap-2">
            {acts.map((a) => {
              const key = actKeyOf(a.actBlock);
              const isSel = selectedAct ? actKeyOf(selectedAct.actBlock) === key : false;
              return (
                <button
                  key={a.actBlock.id}
                  type="button"
                  onClick={() => setSelectedKey(key)}
                  className={[
                    "rounded-lg border p-3 text-left transition",
                    isSel ? "border-[#e0a23d] bg-[#e0a23d]/10" : "border-[color:var(--border)]",
                    changed(a.actBlock.id) ? "ring-1 ring-[#e0533d]" : ""
                  ].join(" ")}
                >
                  <div className="font-semibold">{a.actBlock.title}</div>
                  <div className="mt-1 text-xs opacity-60">{a.nodes.length} 节点</div>
                </button>
              );
            })}
            {acts.length === 0 ? <p className="text-sm opacity-60">还没有幕，点下方新增。</p> : null}
            {onAddItem ? (
              <button
                type="button"
                onClick={() => setAdding("act")}
                className="rounded-lg border border-dashed border-[color:var(--border)] p-2 text-sm opacity-70 hover:opacity-100"
              >
                ＋ 新增幕
              </button>
            ) : null}
          </div>
        </div>

        {/* 右：选中幕详情 */}
        <div className="flex-1">
          {selectedAct ? (
            <div className="surface-panel">
              <div className="flex items-center justify-between gap-2">
                <h4 className="surface-title">{selectedAct.actBlock.title}</h4>
                <button className="app-button" type="button" onClick={() => setOpenBlock(selectedAct.actBlock)}>
                  编辑此幕
                </button>
              </div>
              <p className="mt-1 text-sm opacity-70">
                {preview(selectedAct.actBlock, "objective") || "（未填目标）"}
              </p>

              <div className="mb-2 mt-4 text-sm font-semibold">主线节点（{selectedAct.nodes.length}）</div>
              <div className="grid gap-2">
                {selectedAct.nodes.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => setOpenBlock(n)}
                    className={[
                      "rounded-lg border p-3 text-left transition hover:border-[color:var(--foreground)]",
                      changed(n.id) ? "border-[#e0533d]" : "border-[color:var(--border)]"
                    ].join(" ")}
                  >
                    <div className="font-semibold">{n.title}</div>
                    <div className="mt-1 text-xs opacity-60">{preview(n, "objective")}</div>
                  </button>
                ))}
                {selectedAct.nodes.length === 0 ? (
                  <p className="text-sm opacity-60">这一幕还没有主线节点。</p>
                ) : null}
                {onAddItem ? (
                  <button
                    type="button"
                    onClick={() => setAdding("node")}
                    className="rounded-lg border border-dashed border-[color:var(--border)] p-2 text-sm opacity-70 hover:opacity-100"
                  >
                    ＋ 新增主线节点
                  </button>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-sm opacity-60">左侧选择或新增一幕开始编辑。</p>
          )}

          {/* 未分配节点 */}
          {unassignedNodes.length > 0 ? (
            <div className="surface-panel mt-4 border-[#e0a23d]">
              <div className="mb-2 text-sm font-semibold">⚠ 未分配节点（act_id 无对应幕）</div>
              <div className="grid gap-2">
                {unassignedNodes.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => setOpenBlock(n)}
                    className="rounded-lg border border-[color:var(--border)] p-3 text-left"
                  >
                    <div className="font-semibold">{n.title}</div>
                    <div className="mt-1 text-xs opacity-60">act_id: {preview(n, "act_id") || "（空）"}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* 编辑现有块 */}
      {openBlock ? (
        <BlockDetailModal
          block={openBlock}
          locked={lockedIds.includes(openBlock.id)}
          onSave={(fields) => {
            onEditBlock(openBlock, fields);
            setOpenBlock(null);
          }}
          onDelete={() => {
            onDeleteBlock(openBlock);
            setOpenBlock(null);
          }}
          onUnlock={onUnlockBlock ? () => { onUnlockBlock(openBlock); setOpenBlock(null); } : undefined}
          onClose={() => setOpenBlock(null)}
        />
      ) : null}

      {/* 新增幕 / 节点 */}
      {adding && addingBlock && onAddItem ? (
        <BlockDetailModal
          block={addingBlock}
          locked={false}
          onSave={(fields) => {
            const item = Object.fromEntries(fields.map((f) => [f.key, f.value]));
            if (!String(item.id ?? "").trim()) return; // 身份必填，重名/合法性由后端 validate 兜底
            onAddItem(adding === "node" ? "main_quest_path" : "act_plan", item);
            setAdding(null);
          }}
          onDelete={() => setAdding(null)}
          onClose={() => setAdding(null)}
        />
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit`
Expected: 无错误（若项目无 `tsc` 别名，用 `npx tsc --noEmit -p tsconfig.json`）

- [ ] **Step 3: Lint**

Run: `npm run lint`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add web/components/board/PlotMasterDetail.tsx
git commit -m "feat(plot): PlotMasterDetail 主从视图组件（纲领/幕/节点 + 增删）"
```

---

## Task 3: SettingsBoard 接入

**Files:**
- Modify: `web/components/board/SettingsBoard.tsx`

- [ ] **Step 1: 引入组件**

在 import 区（`BlockDetailModal` 那一行附近）新增：

```tsx
import { PlotMasterDetail } from "@/components/board/PlotMasterDetail";
```

- [ ] **Step 2: plot tab 隐藏「显示空设定项」勾选框**

把现有这段：

```tsx
      <label className="mt-3 flex w-fit items-center gap-2 text-xs text-[color:var(--muted)]">
        <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} />
        显示空设定项
      </label>
```

改为（plot 视图自管空态，不需要该开关）：

```tsx
      {activeTab !== "plot" ? (
        <label className="mt-3 flex w-fit items-center gap-2 text-xs text-[color:var(--muted)]">
          <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} />
          显示空设定项
        </label>
      ) : null}
```

- [ ] **Step 3: plot tab 渲染主从视图，替换网格**

把现有这段：

```tsx
      <BoardBlockGrid
        category={activeTab}
        blocks={current.blocks}
        changedBlockIds={diff.changedBlockIds}
        lockedIds={lockedIds}
        loading={loading}
        showEmpty={showEmpty}
        onOpen={setOpenBlock}
        onAdd={onAddItem ? (arrayKey) => setAddingArray(arrayKey) : undefined}
      />
```

改为：

```tsx
      {activeTab === "plot" ? (
        <PlotMasterDetail
          model={model}
          lockedIds={lockedIds}
          changedBlockIds={diff.changedBlockIds}
          onEditBlock={onEditBlock}
          onDeleteBlock={onDeleteBlock}
          onAddItem={onAddItem}
          onUnlockBlock={onUnlockBlock}
        />
      ) : (
        <BoardBlockGrid
          category={activeTab}
          blocks={current.blocks}
          changedBlockIds={diff.changedBlockIds}
          lockedIds={lockedIds}
          loading={loading}
          showEmpty={showEmpty}
          onOpen={setOpenBlock}
          onAdd={onAddItem ? (arrayKey) => setAddingArray(arrayKey) : undefined}
        />
      )}
```

> 说明：`PlotMasterDetail` 自带编辑/新增弹窗，plot tab 下不使用 `SettingsBoard` 自身的 `openBlock`/`addingArray` 弹窗；这两个 state 与其余 tab 的弹窗保持不变。

- [ ] **Step 4: 类型检查 + Lint**

Run: `npx tsc --noEmit && npm run lint`
Expected: 无错误

- [ ] **Step 5: 构建确认**

Run: `npm run build`
Expected: 构建成功（Next 编译 + 类型检查通过）

- [ ] **Step 6: 手动验证**

```bash
npm run dev
```
打开任一已有游戏的设定页 `/games/<id>/settings` → 点「剧情结构」标签页，确认：
1. 顶部出现「剧情纲领总览」，6 个标量项可点开编辑、保存后值回写
2. 左侧幕大纲可选中，右侧显示该幕目标与其主线节点
3. 「＋新增幕」「＋新增主线节点」能新增（新增节点的 act_id 预填为当前幕）
4. 节点/幕可在弹窗里删除
5. act_id 指向不存在幕的节点出现在「未分配节点」区
6. 切到其它标签页（世界观/角色等）仍是原通用网格，未受影响

- [ ] **Step 7: Commit**

```bash
git add web/components/board/SettingsBoard.tsx
git commit -m "feat(plot): 看板「剧情结构」标签页切换为主从视图"
```

---

## Task 4: 记录 Round（项目约定）

**Files:**
- Modify: `docs/OPTIMIZATION_PLAN.md`

- [ ] **Step 1: 在 §1 追加 Round 条目**

在 `docs/OPTIMIZATION_PLAN.md` 的 §1（Round 列表）末尾，按现有 Round 格式追加一条 `### Round N (2026-06-05)`，内容概述：
- 新增 `lib/plotView.ts` + 单测：从 BoardModel 派生剧情线主从结构
- 新增 `components/board/PlotMasterDetail.tsx`：看板「剧情结构」升级为纲领总览 + 幕大纲 + 幕详情主从视图，支持增删幕/节点
- 复用 SettingsBoard 既有读写/diff 回调，未改后端
- 设计与计划文档：`docs/superpowers/specs|plans/2026-06-05-plot-line-masterdetail*`

（N = 当前最大 Round 号 + 1，照抄文件里已有 Round 的标题与缩进格式，不要修改历史 Round。）

- [ ] **Step 2: Commit**

```bash
git add docs/OPTIMIZATION_PLAN.md
git commit -m "docs: OPTIMIZATION_PLAN 追加 Round N（剧情线主从视图）"
```

---

## 验收清单（全部任务完成后）

- [ ] `npm run test` 全绿（含新增 plotView 测试）
- [ ] `npm run lint` 无错误
- [ ] `npm run build` 成功
- [ ] 手动验证 6 项全部通过
- [ ] `docs/OPTIMIZATION_PLAN.md` 已追加本轮 Round
