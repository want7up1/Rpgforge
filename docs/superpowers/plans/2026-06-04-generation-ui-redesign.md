# 创建冒险页重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「创建冒险」页从「线性对话流 + JSON 蓝图」重设计为「分类 Tab 设定看板 + 底部对话停靠 + 改动闪烁 + 手改锁定」。

**Architecture:** 前端为主——纯函数 `lib/generatorBoard.ts` 把 `confirmed_requirements`（粗）和 `story_settings`（细）映射成统一 BoardModel，组件层渲染 Tab 看板/弹窗/对话停靠/进度。后端仅加一条「锁定字段不得改回」的 interview prompt 规则 + 一个可选 `locked_fields` 字段。无新表、无新 LLM 调用、无新业务端点。

**Tech Stack:** Next.js(App Router) + React + TypeScript + Tailwind；新增 vitest 仅测纯函数；后端 FastAPI + pytest（容器内）。

**设计依据：** `docs/superpowers/specs/2026-06-04-generation-ui-redesign-design.md`

---

## 文件结构

**新增**
- `web/vitest.config.ts` — vitest 配置（仅 node 环境测纯函数）
- `web/lib/generatorBoard.ts` — 纯逻辑：BoardModel 类型、分类定义、`buildBoardModel`、`diffBoard`、锁定与写回工具
- `web/lib/generatorBoard.test.ts` — vitest 单测
- `web/components/generator/BoardTabs.tsx` — Tab 栏（分类 + 数量 + +N 角标）
- `web/components/generator/BoardBlockGrid.tsx` — 某 Tab 的 block 网格 + 卡片（骨架/闪烁/锁定标记）
- `web/components/generator/BlockDetailModal.tsx` — 居中弹窗：查看/编辑/删除/解锁
- `web/components/generator/ChangeSummaryBar.tsx` — 顶部变更摘要条
- `web/components/generator/GenerationProgress.tsx` — Tab 点亮式进度 + 思考流折叠
- `web/components/generator/ChatDock.tsx` — 底部对话停靠条（可拖高）
- `web/components/generator/ChatHistorySheet.tsx` — 上滑历史面板
- `web/components/generator/SettingsBoard.tsx` — 看板容器（组合 tabs+grid+modal+summary）
- `api/tests/test_generator_locked_fields.py` — 后端锁定字段测试

**修改**
- `web/package.json` — 加 vitest devDep + `test` 脚本
- `web/lib/api.ts` — `createGeneratorChatJob` payload 增加可选 `locked_fields`
- `web/app/games/new/page.tsx` — 重写为看板布局，接线全部组件与状态
- `api/app/schemas/generator.py` — `GeneratorChatRequest` 增加可选 `locked_fields: list[str] = []`
- `api/app/prompts/generator_interview.md` — 新增「锁定字段」规则
- `docs/OPTIMIZATION_PLAN.md` — 追加 Round 条目（记 prompt 规则编号）

---

## Phase A — 纯逻辑基础（vitest，TDD）

### Task 1: vitest 设置

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`

- [ ] **Step 1: 安装 vitest**

Run: `cd web && npm install -D vitest@^2`
Expected: `package.json` devDependencies 出现 `vitest`，无报错。

- [ ] **Step 2: 加 test 脚本**

修改 `web/package.json` 的 `scripts`，加入：

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 3: 写 vitest 配置**

Create `web/vitest.config.ts`：

```ts
import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"]
  },
  resolve: {
    alias: { "@": resolve(__dirname, ".") }
  }
});
```

- [ ] **Step 4: 加一个 smoke 测试验证 runner 工作**

Create `web/lib/generatorBoard.test.ts`（临时占位，下一任务替换）：

```ts
import { describe, it, expect } from "vitest";

describe("smoke", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 5: 运行验证**

Run: `cd web && npm test`
Expected: 1 passed。

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/lib/generatorBoard.test.ts
git commit -m "chore(web): 引入 vitest 用于纯函数单测"
```

---

### Task 2: BoardModel 类型 + 分类定义 + 从 story_settings 构建

**Files:**
- Create: `web/lib/generatorBoard.ts`
- Test: `web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试（从 story_settings 构建 6 分类）**

替换 `web/lib/generatorBoard.test.ts` 顶部，加入：

```ts
import { describe, it, expect } from "vitest";
import { buildBoardModel, BOARD_CATEGORIES } from "@/lib/generatorBoard";

describe("buildBoardModel from story_settings", () => {
  const settings = {
    game_profile: { title: "雁回镇旧案", genre: "黑暗武侠", tone: "阴郁" },
    worldview: { summary: "雨夜义庄" },
    story_core: {
      central_mystery: "镖队为何失踪",
      must_preserve: ["雨夜义庄"],
      must_not_become: ["修仙飞升"],
      canon_terms: ["红伞"]
    },
    core_characters: [
      { name: "失忆镖师", role: "protagonist", description: "主角" },
      { name: "红伞女人", role: "npc", description: "神秘" }
    ],
    act_plan: [{ id: "act_1", title: "雨夜义庄", objective: "查失踪" }],
    main_quest_path: [{ id: "mq_1", title: "找镖队" }],
    core_mechanics: [{ name: "检定", rule: "d20" }],
    action_style_rules: [{ name: "战斗描写", rule: "详细" }],
    story_material_library: [{ title: "红伞传说", content: "..." }],
    hard_rules: { must_follow: ["完整描写"], must_not: ["剧透身世"], reveal_rules: [], continuity_rules: [] }
  };

  it("产出 7 个分类（含高级）", () => {
    const model = buildBoardModel({ source: "settings", settings });
    expect(model.categories.map((c) => c.id)).toEqual(
      BOARD_CATEGORIES.map((c) => c.id)
    );
  });

  it("角色分类含 2 个 block，title 为角色名", () => {
    const model = buildBoardModel({ source: "settings", settings });
    const chars = model.categories.find((c) => c.id === "characters")!;
    expect(chars.blocks.map((b) => b.title)).toEqual(["失忆镖师", "红伞女人"]);
  });

  it("约束分类带 danger 配色且含 hard_rules + story_core 红线", () => {
    const model = buildBoardModel({ source: "settings", settings });
    const con = model.categories.find((c) => c.id === "constraints")!;
    expect(con.tone).toBe("danger");
    const titles = con.blocks.map((b) => b.title);
    expect(titles).toContain("必须遵守");
    expect(titles).toContain("禁止变成");
    expect(titles).toContain("专名表");
  });

  it("每个角色 block 的 address 能定位回数组项", () => {
    const model = buildBoardModel({ source: "settings", settings });
    const hong = model.categories
      .find((c) => c.id === "characters")!
      .blocks.find((b) => b.title === "红伞女人")!;
    expect(hong.address).toEqual({
      kind: "settingsItem",
      arrayKey: "core_characters",
      idKey: "name",
      idValue: "红伞女人"
    });
  });
});
```

- [ ] **Step 2: 运行验证失败**

Run: `cd web && npm test`
Expected: FAIL（`buildBoardModel`/`BOARD_CATEGORIES` 未定义）。

- [ ] **Step 3: 实现 generatorBoard.ts（类型 + 分类 + settings 构建）**

Create `web/lib/generatorBoard.ts`：

```ts
// 看板纯逻辑：把 confirmed_requirements（粗）与 story_settings（细）映射成统一 BoardModel。
// 不依赖 React，便于 vitest 单测。

export type BoardCategoryId =
  | "world"
  | "characters"
  | "plot"
  | "mechanics"
  | "constraints"
  | "materials"
  | "advanced";

export type BoardCategoryDef = {
  id: BoardCategoryId;
  label: string;
  icon: string;
  tone?: "danger";
};

// 分类顺序即 Tab 顺序。约束类单独 danger 配色。
export const BOARD_CATEGORIES: BoardCategoryDef[] = [
  { id: "world", label: "世界与基调", icon: "🌍" },
  { id: "characters", label: "角色", icon: "👤" },
  { id: "plot", label: "剧情结构", icon: "🎬" },
  { id: "mechanics", label: "玩法机制", icon: "⚙" },
  { id: "constraints", label: "约束与红线", icon: "📜", tone: "danger" },
  { id: "materials", label: "素材库", icon: "📦" },
  { id: "advanced", label: "高级", icon: "🔧" }
];

export type BoardFieldType = "text" | "textarea" | "stringList";

export type BoardField = {
  key: string;
  label: string;
  value: string | string[];
  type: BoardFieldType;
};

// address 决定编辑/删除时写回 source 的位置。
export type BoardAddress =
  | { kind: "confirmedField"; field: string }
  | { kind: "settingsScalar"; path: string[] } // 写回 story_core.central_mystery 等单值
  | { kind: "settingsStringList"; path: string[] } // 写回 hard_rules.must_follow 等字符串数组
  | { kind: "settingsItem"; arrayKey: string; idKey: string; idValue: string }; // 数组项（角色/机制…）

export type BoardBlock = {
  id: string; // 稳定 id。confirmed 阶段 = 字段名；settings 阶段 = `${arrayKey}:${idValue}` 或路径
  category: BoardCategoryId;
  title: string;
  icon: string;
  summary: string; // 卡片副标题（一行预览）
  fields: BoardField[];
  address: BoardAddress;
  deletable: boolean; // 数组项可删；单值/字符串列表块不可删
};

export type BoardCategory = BoardCategoryDef & { blocks: BoardBlock[] };

export type BoardModel = {
  source: "confirmed" | "settings";
  categories: BoardCategory[];
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map((v) => asRecord(v)) : [];
}
function str(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}
function strList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(str).filter(Boolean) : [];
}
function firstLine(text: string, max = 40): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

function iconFor(id: BoardCategoryId): string {
  return BOARD_CATEGORIES.find((c) => c.id === id)!.icon;
}

// 把字段名映射成中文标签（兜底用 key 本身）。
const FIELD_LABELS: Record<string, string> = {
  title: "标题", genre: "类型", tone: "基调", logline: "一句话",
  summary: "概述", premise: "前提", core_fantasy: "核心爽点",
  central_mystery: "核心悬念", main_goal: "主目标", emotional_arc: "情感弧",
  narrative_style: "叙事风格", name: "名称", role: "定位", identity: "身份",
  description: "描述", appearance: "外貌", desire: "欲望", fear: "恐惧",
  leverage: "把柄", relationship_arc: "关系弧", aliases: "别名",
  objective: "目标", dramatic_question: "戏剧问题", rule: "规则",
  content: "内容", usage: "用法", keywords: "关键词", triggers: "触发词"
};
function label(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

// 从一个对象按白名单字段顺序产出 BoardField[]（空值跳过，列表用 stringList）。
function objectFields(
  obj: Record<string, unknown>,
  keys: { key: string; type: BoardFieldType }[]
): BoardField[] {
  const out: BoardField[] = [];
  for (const { key, type } of keys) {
    const raw = obj[key];
    if (type === "stringList") {
      const v = strList(raw);
      if (v.length) out.push({ key, label: label(key), value: v, type });
    } else {
      const v = str(raw);
      if (v) out.push({ key, label: label(key), value: v, type });
    }
  }
  return out;
}

function buildFromSettings(settings: Record<string, unknown>): BoardCategory[] {
  const profile = asRecord(settings.game_profile);
  const worldview = asRecord(settings.worldview);
  const core = asRecord(settings.story_core);
  const hard = asRecord(settings.hard_rules);

  const byId: Record<BoardCategoryId, BoardBlock[]> = {
    world: [], characters: [], plot: [], mechanics: [],
    constraints: [], materials: [], advanced: []
  };

  // ① 世界与基调
  const profileFields = objectFields(profile, [
    { key: "title", type: "text" }, { key: "genre", type: "text" },
    { key: "tone", type: "text" }, { key: "logline", type: "textarea" }
  ]);
  if (profileFields.length)
    byId.world.push({
      id: "game_profile", category: "world", title: "作品信息", icon: "🪪",
      summary: firstLine(str(profile.title)), fields: profileFields,
      address: { kind: "settingsScalar", path: ["game_profile"] }, deletable: false
    });
  const worldviewFields = objectFields(worldview, [
    { key: "summary", type: "textarea" }
  ]);
  if (worldviewFields.length)
    byId.world.push({
      id: "worldview", category: "world", title: "世界观", icon: "🌍",
      summary: firstLine(str(worldview.summary)), fields: worldviewFields,
      address: { kind: "settingsScalar", path: ["worldview"] }, deletable: false
    });
  for (const k of ["premise", "core_fantasy", "central_mystery", "main_goal", "emotional_arc", "narrative_style"]) {
    const v = str(core[k]);
    if (!v) continue;
    byId.world.push({
      id: `story_core.${k}`, category: "world", title: label(k), icon: "🎯",
      summary: firstLine(v), fields: [{ key: k, label: label(k), value: v, type: "textarea" }],
      address: { kind: "settingsScalar", path: ["story_core", k] }, deletable: false
    });
  }

  // ② 角色
  for (const ch of asList(settings.core_characters)) {
    const name = str(ch.name);
    if (!name) continue;
    byId.characters.push({
      id: `core_characters:${name}`, category: "characters", title: name, icon: "👤",
      summary: [str(ch.role), firstLine(str(ch.description))].filter(Boolean).join(" · "),
      fields: objectFields(ch, [
        { key: "name", type: "text" }, { key: "role", type: "text" },
        { key: "identity", type: "text" }, { key: "aliases", type: "stringList" },
        { key: "description", type: "textarea" }, { key: "appearance", type: "textarea" },
        { key: "desire", type: "text" }, { key: "fear", type: "text" },
        { key: "leverage", type: "text" }, { key: "relationship_arc", type: "textarea" }
      ]),
      address: { kind: "settingsItem", arrayKey: "core_characters", idKey: "name", idValue: name },
      deletable: true
    });
  }

  // ③ 剧情结构
  for (const act of asList(settings.act_plan)) {
    const id = str(act.id) || str(act.title);
    if (!id) continue;
    byId.plot.push({
      id: `act_plan:${id}`, category: "plot", title: str(act.title) || id, icon: "🎬",
      summary: firstLine(str(act.objective)),
      fields: objectFields(act, [
        { key: "title", type: "text" }, { key: "objective", type: "textarea" },
        { key: "dramatic_question", type: "textarea" }
      ]),
      address: { kind: "settingsItem", arrayKey: "act_plan", idKey: "id", idValue: str(act.id) },
      deletable: true
    });
  }
  for (const q of asList(settings.main_quest_path)) {
    const id = str(q.id) || str(q.title);
    if (!id) continue;
    byId.plot.push({
      id: `main_quest_path:${id}`, category: "plot", title: str(q.title) || id, icon: "🧭",
      summary: firstLine(str(q.objective)),
      fields: objectFields(q, [
        { key: "title", type: "text" }, { key: "objective", type: "textarea" }
      ]),
      address: { kind: "settingsItem", arrayKey: "main_quest_path", idKey: "id", idValue: str(q.id) },
      deletable: true
    });
  }

  // ④ 玩法机制
  for (const m of asList(settings.core_mechanics)) {
    const name = str(m.name);
    if (!name) continue;
    byId.mechanics.push({
      id: `core_mechanics:${name}`, category: "mechanics", title: name, icon: "⚙",
      summary: firstLine(str(m.rule)),
      fields: objectFields(m, [{ key: "name", type: "text" }, { key: "rule", type: "textarea" }]),
      address: { kind: "settingsItem", arrayKey: "core_mechanics", idKey: "name", idValue: name },
      deletable: true
    });
  }
  for (const s of asList(settings.action_style_rules)) {
    const name = str(s.name);
    if (!name) continue;
    byId.mechanics.push({
      id: `action_style_rules:${name}`, category: "mechanics", title: name, icon: "🖋",
      summary: firstLine(str(s.rule)),
      fields: objectFields(s, [
        { key: "name", type: "text" }, { key: "triggers", type: "stringList" },
        { key: "rule", type: "textarea" }
      ]),
      address: { kind: "settingsItem", arrayKey: "action_style_rules", idKey: "name", idValue: name },
      deletable: true
    });
  }

  // ⑤ 约束与红线（hard_rules 各桶 + story_core 红线）
  const constraintBuckets: { key: string; title: string }[] = [
    { key: "must_follow", title: "必须遵守" },
    { key: "must_not", title: "禁止行为" },
    { key: "reveal_rules", title: "揭示规则" },
    { key: "continuity_rules", title: "连续性规则" }
  ];
  for (const { key, title } of constraintBuckets) {
    const v = strList(hard[key]);
    if (!v.length) continue;
    byId.constraints.push({
      id: `hard_rules.${key}`, category: "constraints", title, icon: "📜",
      summary: `${v.length} 条`,
      fields: [{ key, label: title, value: v, type: "stringList" }],
      address: { kind: "settingsStringList", path: ["hard_rules", key] }, deletable: false
    });
  }
  const coreBuckets: { key: string; title: string }[] = [
    { key: "must_preserve", title: "必须保留" },
    { key: "must_not_become", title: "禁止变成" },
    { key: "forbidden_drift", title: "禁止漂移" },
    { key: "canon_terms", title: "专名表" }
  ];
  for (const { key, title } of coreBuckets) {
    const v = strList(core[key]);
    if (!v.length) continue;
    byId.constraints.push({
      id: `story_core.${key}`, category: "constraints", title, icon: "🚫",
      summary: `${v.length} 条`,
      fields: [{ key, label: title, value: v, type: "stringList" }],
      address: { kind: "settingsStringList", path: ["story_core", key] }, deletable: false
    });
  }

  // ⑥ 素材库
  for (const mat of asList(settings.story_material_library)) {
    const title = str(mat.title) || str(mat.id);
    if (!title) continue;
    byId.materials.push({
      id: `story_material_library:${title}`, category: "materials", title, icon: "📦",
      summary: firstLine(str(mat.content)),
      fields: objectFields(mat, [
        { key: "title", type: "text" }, { key: "keywords", type: "stringList" },
        { key: "content", type: "textarea" }, { key: "usage", type: "textarea" }
      ]),
      address: {
        kind: "settingsItem", arrayKey: "story_material_library",
        idKey: str(mat.id) ? "id" : "title", idValue: str(mat.id) || title
      },
      deletable: true
    });
  }

  // ⑦ 高级：篇幅参数（只读展示，单块）
  const gen = asRecord(settings.generation_parameters);
  const genFields = Object.entries(gen)
    .filter(([, v]) => typeof v === "number" || typeof v === "string")
    .map(([k, v]) => ({ key: k, label: label(k), value: String(v), type: "text" as const }));
  if (genFields.length)
    byId.advanced.push({
      id: "generation_parameters", category: "advanced", title: "篇幅参数", icon: "🔧",
      summary: `${genFields.length} 项`, fields: genFields,
      address: { kind: "settingsScalar", path: ["generation_parameters"] }, deletable: false
    });

  return BOARD_CATEGORIES.map((def) => ({ ...def, blocks: byId[def.id] }));
}

export function buildBoardModel(
  input:
    | { source: "settings"; settings: Record<string, unknown> }
    | { source: "confirmed"; confirmed: Record<string, unknown> }
): BoardModel {
  if (input.source === "settings") {
    return { source: "settings", categories: buildFromSettings(input.settings) };
  }
  return { source: "confirmed", categories: buildFromConfirmed(input.confirmed) };
}

// 占位：下个任务实现。先抛错以便 settings 测试先过。
function buildFromConfirmed(_confirmed: Record<string, unknown>): BoardCategory[] {
  return BOARD_CATEGORIES.map((def) => ({ ...def, blocks: [] }));
}
```

- [ ] **Step 4: 运行验证通过**

Run: `cd web && npm test`
Expected: settings 相关 4 个测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts
git commit -m "feat(web): BoardModel 类型+分类+从 story_settings 构建看板"
```

---

### Task 3: 从 confirmed_requirements 构建（粗粒度）

**Files:**
- Modify: `web/lib/generatorBoard.ts`
- Test: `web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试**

在 `web/lib/generatorBoard.test.ts` 追加：

```ts
describe("buildBoardModel from confirmed_requirements", () => {
  const confirmed = {
    story_background: "黑暗武侠·雁回镇义庄",
    core_premise: "失忆镖师查失踪镖队",
    must_include: ["雨夜义庄", "红伞女人"],
    forbidden_content: ["修仙飞升"],
    playstyle_preferences: ["调查为主"],
    tone_preferences: ["阴郁"],
    raw_user_input: "..."
  };

  it("block id 等于 confirmed 字段名（便于锁定透传后端）", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed });
    const world = model.categories.find((c) => c.id === "world")!;
    expect(world.blocks.map((b) => b.id)).toContain("story_background");
    expect(world.blocks.map((b) => b.id)).toContain("core_premise");
    expect(world.blocks.map((b) => b.id)).toContain("tone_preferences");
  });

  it("must_include/forbidden_content 落约束类", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed });
    const con = model.categories.find((c) => c.id === "constraints")!;
    expect(con.blocks.map((b) => b.id)).toEqual(["must_include", "forbidden_content"]);
  });

  it("playstyle_preferences 落机制类，address 为 confirmedField", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed });
    const mech = model.categories.find((c) => c.id === "mechanics")!;
    const block = mech.blocks.find((b) => b.id === "playstyle_preferences")!;
    expect(block.address).toEqual({ kind: "confirmedField", field: "playstyle_preferences" });
  });

  it("空字段不产 block", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed: { story_background: "x" } });
    const world = model.categories.find((c) => c.id === "world")!;
    expect(world.blocks.map((b) => b.id)).toEqual(["story_background"]);
  });
});
```

- [ ] **Step 2: 运行验证失败**

Run: `cd web && npm test`
Expected: FAIL（confirmed 块为空）。

- [ ] **Step 3: 实现 buildFromConfirmed**

替换 `web/lib/generatorBoard.ts` 末尾的占位 `buildFromConfirmed`：

```ts
// confirmed_requirements → BoardModel。block id 刻意等于字段名，使锁定 id 可直接当 locked_fields 发后端。
type ConfirmedSpec = {
  field: string;
  category: BoardCategoryId;
  title: string;
  type: BoardFieldType;
};
const CONFIRMED_SPECS: ConfirmedSpec[] = [
  { field: "story_background", category: "world", title: "故事背景", type: "textarea" },
  { field: "core_premise", category: "world", title: "核心设定", type: "textarea" },
  { field: "tone_preferences", category: "world", title: "风格偏好", type: "stringList" },
  { field: "playstyle_preferences", category: "mechanics", title: "玩法偏好", type: "stringList" },
  { field: "must_include", category: "constraints", title: "必须出现", type: "stringList" },
  { field: "forbidden_content", category: "constraints", title: "禁止点", type: "stringList" }
];

function buildFromConfirmed(confirmed: Record<string, unknown>): BoardCategory[] {
  const byId: Record<BoardCategoryId, BoardBlock[]> = {
    world: [], characters: [], plot: [], mechanics: [],
    constraints: [], materials: [], advanced: []
  };
  for (const spec of CONFIRMED_SPECS) {
    const raw = confirmed[spec.field];
    const isList = spec.type === "stringList";
    const value = isList ? strList(raw) : str(raw);
    const empty = isList ? (value as string[]).length === 0 : value === "";
    if (empty) continue;
    byId[spec.category].push({
      id: spec.field,
      category: spec.category,
      title: spec.title,
      icon: iconFor(spec.category),
      summary: isList ? `${(value as string[]).length} 条` : firstLine(value as string),
      fields: [{ key: spec.field, label: spec.title, value, type: spec.type }],
      address: { kind: "confirmedField", field: spec.field },
      deletable: false
    });
  }
  return BOARD_CATEGORIES.map((def) => ({ ...def, blocks: byId[def.id] }));
}
```

- [ ] **Step 4: 运行验证通过**

Run: `cd web && npm test`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts
git commit -m "feat(web): 从 confirmed_requirements 构建粗粒度看板"
```

---

### Task 4: diffBoard（改动检测）

**Files:**
- Modify: `web/lib/generatorBoard.ts`
- Test: `web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试**

追加到测试文件：

```ts
import { diffBoard } from "@/lib/generatorBoard";

describe("diffBoard", () => {
  const base = { story_background: "a", must_include: ["x"] };
  const prev = buildBoardModel({ source: "confirmed", confirmed: base });

  it("新增 block 计入对应分类，记录 changedBlockIds", () => {
    const next = buildBoardModel({
      source: "confirmed",
      confirmed: { ...base, core_premise: "b" }
    });
    const diff = diffBoard(prev, next);
    expect(diff.changedCategories.world).toBe(1);
    expect(diff.changedBlockIds.has("core_premise")).toBe(true);
  });

  it("内容变化算改动", () => {
    const next = buildBoardModel({
      source: "confirmed",
      confirmed: { ...base, story_background: "a2" }
    });
    const diff = diffBoard(prev, next);
    expect(diff.changedBlockIds.has("story_background")).toBe(true);
  });

  it("无变化时计数为 0", () => {
    const next = buildBoardModel({ source: "confirmed", confirmed: base });
    const diff = diffBoard(prev, next);
    expect(diff.changedBlockIds.size).toBe(0);
    expect(Object.values(diff.changedCategories).every((n) => n === 0)).toBe(true);
  });

  it("prev 为 null（首次生成）时所有 block 算新", () => {
    const next = buildBoardModel({ source: "confirmed", confirmed: base });
    const diff = diffBoard(null, next);
    expect(diff.changedBlockIds.has("story_background")).toBe(true);
    expect(diff.changedBlockIds.has("must_include")).toBe(true);
  });
});
```

- [ ] **Step 2: 运行验证失败**

Run: `cd web && npm test`
Expected: FAIL（`diffBoard` 未定义）。

- [ ] **Step 3: 实现 diffBoard**

在 `web/lib/generatorBoard.ts` 追加：

```ts
export type BoardDiff = {
  changedCategories: Record<BoardCategoryId, number>;
  changedBlockIds: Set<string>;
};

// block 内容指纹：用 fields 的值拼成字符串，变化即视为改动。
function blockFingerprint(block: BoardBlock): string {
  return block.fields
    .map((f) => `${f.key}=${Array.isArray(f.value) ? f.value.join("¦") : f.value}`)
    .join("|");
}

export function diffBoard(prev: BoardModel | null, next: BoardModel): BoardDiff {
  const prevPrints = new Map<string, string>();
  if (prev) {
    for (const cat of prev.categories)
      for (const b of cat.blocks) prevPrints.set(b.id, blockFingerprint(b));
  }
  const changedCategories = Object.fromEntries(
    BOARD_CATEGORIES.map((c) => [c.id, 0])
  ) as Record<BoardCategoryId, number>;
  const changedBlockIds = new Set<string>();
  for (const cat of next.categories) {
    for (const b of cat.blocks) {
      const before = prevPrints.get(b.id);
      if (before === undefined || before !== blockFingerprint(b)) {
        changedBlockIds.add(b.id);
        changedCategories[cat.id] += 1;
      }
    }
  }
  return { changedCategories, changedBlockIds };
}
```

- [ ] **Step 4: 运行验证通过**

Run: `cd web && npm test`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts
git commit -m "feat(web): diffBoard 改动检测（分类计数+变更块集合）"
```

---

### Task 5: 锁定与写回工具

**Files:**
- Modify: `web/lib/generatorBoard.ts`
- Test: `web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试**

追加到测试文件：

```ts
import { isLocked, lockBlock, unlockBlock, writeBlockFields } from "@/lib/generatorBoard";

describe("锁定工具", () => {
  it("lock/unlock/isLocked", () => {
    let locked: string[] = [];
    locked = lockBlock(locked, "core_characters:红伞女人");
    expect(isLocked(locked, "core_characters:红伞女人")).toBe(true);
    locked = lockBlock(locked, "core_characters:红伞女人"); // 幂等
    expect(locked.length).toBe(1);
    locked = unlockBlock(locked, "core_characters:红伞女人");
    expect(isLocked(locked, "core_characters:红伞女人")).toBe(false);
  });
});

describe("writeBlockFields 写回 source", () => {
  it("confirmedField：写回字符串/列表字段", () => {
    const src = { story_background: "old", must_include: ["x"] };
    const out = writeBlockFields(src, { kind: "confirmedField", field: "story_background" }, [
      { key: "story_background", label: "故事背景", value: "new", type: "textarea" }
    ]);
    expect((out as any).story_background).toBe("new");
    expect(out).not.toBe(src); // 不可变
  });

  it("settingsScalar：写回 story_core.central_mystery", () => {
    const src = { story_core: { central_mystery: "old", main_goal: "g" } };
    const out = writeBlockFields(src, { kind: "settingsScalar", path: ["story_core", "central_mystery"] }, [
      { key: "central_mystery", label: "核心悬念", value: "new", type: "textarea" }
    ]);
    expect((out as any).story_core.central_mystery).toBe("new");
    expect((out as any).story_core.main_goal).toBe("g"); // 同级不丢
  });

  it("settingsStringList：写回 hard_rules.must_follow", () => {
    const src = { hard_rules: { must_follow: ["a"], must_not: ["b"] } };
    const out = writeBlockFields(src, { kind: "settingsStringList", path: ["hard_rules", "must_follow"] }, [
      { key: "must_follow", label: "必须遵守", value: ["a", "c"], type: "stringList" }
    ]);
    expect((out as any).hard_rules.must_follow).toEqual(["a", "c"]);
    expect((out as any).hard_rules.must_not).toEqual(["b"]);
  });

  it("settingsItem：按 idKey 定位数组项写回多字段", () => {
    const src = {
      core_characters: [
        { name: "主角", description: "d1" },
        { name: "红伞女人", description: "d2", role: "npc" }
      ]
    };
    const out = writeBlockFields(
      src,
      { kind: "settingsItem", arrayKey: "core_characters", idKey: "name", idValue: "红伞女人" },
      [
        { key: "name", label: "名称", value: "黑伞女人", type: "text" },
        { key: "description", label: "描述", value: "改了", type: "textarea" }
      ]
    );
    const arr = (out as any).core_characters;
    expect(arr[0]).toEqual({ name: "主角", description: "d1" }); // 其它项不动
    expect(arr[1]).toEqual({ name: "黑伞女人", description: "改了", role: "npc" }); // 未列字段保留
  });

  it("deleteBlock：settingsItem 删除数组项", () => {
    const src = { core_characters: [{ name: "a" }, { name: "b" }] };
    const out = deleteBlock(src, {
      kind: "settingsItem", arrayKey: "core_characters", idKey: "name", idValue: "a"
    });
    expect((out as any).core_characters).toEqual([{ name: "b" }]);
  });
});
```

注意：测试顶部 import 需补 `deleteBlock`：把该 import 行改为
`import { isLocked, lockBlock, unlockBlock, writeBlockFields, deleteBlock } from "@/lib/generatorBoard";`

- [ ] **Step 2: 运行验证失败**

Run: `cd web && npm test`
Expected: FAIL（这些函数未定义）。

- [ ] **Step 3: 实现锁定与写回工具**

在 `web/lib/generatorBoard.ts` 追加：

```ts
export function isLocked(locked: string[], blockId: string): boolean {
  return locked.includes(blockId);
}
export function lockBlock(locked: string[], blockId: string): string[] {
  return locked.includes(blockId) ? locked : [...locked, blockId];
}
export function unlockBlock(locked: string[], blockId: string): string[] {
  return locked.filter((id) => id !== blockId);
}

function cloneDeep<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

// 把 fields 的值塞进 record（confirmed 或 settings 块的字段集合）。
function fieldsToRecord(target: Record<string, unknown>, fields: BoardField[]): void {
  for (const f of fields) target[f.key] = f.value;
}

export function writeBlockFields(
  source: Record<string, unknown>,
  address: BoardAddress,
  fields: BoardField[]
): Record<string, unknown> {
  const out = cloneDeep(source);
  if (address.kind === "confirmedField") {
    const f = fields.find((x) => x.key === address.field);
    if (f) out[address.field] = f.value;
    return out;
  }
  if (address.kind === "settingsScalar" || address.kind === "settingsStringList") {
    // path 最后一段是叶子；逐级 setdefault 对象后写叶子值
    const path = address.path;
    let node = out as Record<string, unknown>;
    for (let i = 0; i < path.length - 1; i += 1) {
      const seg = path[i];
      if (typeof node[seg] !== "object" || node[seg] === null) node[seg] = {};
      node = node[seg] as Record<string, unknown>;
    }
    const leaf = path[path.length - 1];
    if (address.path.length === 1 && address.kind === "settingsScalar") {
      // 整对象块（game_profile/worldview/generation_parameters）：把 fields 合并进该对象
      const obj = (typeof node[leaf] === "object" && node[leaf] !== null
        ? (node[leaf] as Record<string, unknown>)
        : {}) as Record<string, unknown>;
      fieldsToRecord(obj, fields);
      node[leaf] = obj;
    } else {
      const f = fields[0];
      node[leaf] = f ? f.value : node[leaf];
    }
    return out;
  }
  // settingsItem：定位数组项，合并字段
  const arr = Array.isArray(out[address.arrayKey])
    ? (out[address.arrayKey] as Record<string, unknown>[])
    : [];
  const idx = arr.findIndex((item) => str(item[address.idKey]) === address.idValue);
  if (idx >= 0) {
    const merged = { ...arr[idx] };
    fieldsToRecord(merged, fields);
    arr[idx] = merged;
    out[address.arrayKey] = arr;
  }
  return out;
}

export function deleteBlock(
  source: Record<string, unknown>,
  address: BoardAddress
): Record<string, unknown> {
  if (address.kind !== "settingsItem") return source; // 仅数组项可删
  const out = cloneDeep(source);
  const arr = Array.isArray(out[address.arrayKey])
    ? (out[address.arrayKey] as Record<string, unknown>[])
    : [];
  out[address.arrayKey] = arr.filter((item) => str(item[address.idKey]) !== address.idValue);
  return out;
}
```

注意上面 `writeBlockFields` 里 `str()` 已在文件前部定义，复用即可。

- [ ] **Step 4: 运行验证通过**

Run: `cd web && npm test`
Expected: 全部 PASS。

- [ ] **Step 5: 类型检查**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误。

- [ ] **Step 6: Commit**

```bash
git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts
git commit -m "feat(web): 锁定工具 + 按 address 写回/删除 block"
```

---

## Phase B — 组件（tsc + next build 验证，无单测）

> 本项目前端无组件测试框架，组件任务以「写代码 → `npx tsc --noEmit` 通过 → commit」为节奏；Phase 末尾跑一次 `next build`。组件全部复用既有 CSS 类（`app-button`/`surface-panel`/`archive-card`/`app-input`/`app-pill` 等）。

### Task 6: BoardTabs（Tab 栏 + +N 角标）

**Files:**
- Create: `web/components/generator/BoardTabs.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

import type { BoardCategory, BoardCategoryId } from "@/lib/generatorBoard";

export function BoardTabs({
  categories,
  activeTab,
  changedCategories,
  onSelect
}: {
  categories: BoardCategory[];
  activeTab: BoardCategoryId;
  changedCategories: Record<BoardCategoryId, number>;
  onSelect: (id: BoardCategoryId) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 border-b border-[color:var(--border)] pb-3">
      {categories.map((cat) => {
        const changed = changedCategories[cat.id] ?? 0;
        const isActive = cat.id === activeTab;
        const danger = cat.tone === "danger";
        return (
          <button
            key={cat.id}
            type="button"
            onClick={() => onSelect(cat.id)}
            className={[
              "relative rounded-full border px-3 py-1 text-sm transition",
              isActive
                ? "bg-[color:var(--foreground)] text-[color:var(--background)] border-transparent"
                : danger
                  ? "border-[#e0a23d] text-[#b5701f]"
                  : "border-[color:var(--border)]"
            ].join(" ")}
          >
            <span className="mr-1">{cat.icon}</span>
            {cat.label}
            <span className="ml-1 opacity-60">{cat.blocks.length}</span>
            {changed > 0 ? (
              <span className="absolute -right-2 -top-2 animate-pulse rounded-full bg-[#e0533d] px-1.5 py-0.5 text-[10px] font-semibold text-white">
                +{changed}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/generator/BoardTabs.tsx && git commit -m "feat(web): BoardTabs Tab栏+改动角标"`

---

### Task 7: BoardBlockGrid（block 网格 + 卡片）

**Files:**
- Create: `web/components/generator/BoardBlockGrid.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

import type { BoardBlock } from "@/lib/generatorBoard";

export function BoardBlockGrid({
  blocks,
  changedBlockIds,
  lockedIds,
  loading,
  onOpen
}: {
  blocks: BoardBlock[];
  changedBlockIds: Set<string>;
  lockedIds: string[];
  loading: boolean;
  onOpen: (block: BoardBlock) => void;
}) {
  if (loading && blocks.length === 0) {
    return (
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="archive-card h-20 animate-pulse opacity-60" />
        ))}
      </div>
    );
  }
  if (blocks.length === 0) {
    return (
      <p className="surface-panel surface-subtle mt-4">
        这一类还没有设定，确认方向 / 生成世界后会自动补全。
      </p>
    );
  }
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {blocks.map((block) => {
        const changed = changedBlockIds.has(block.id);
        const locked = lockedIds.includes(block.id);
        return (
          <button
            key={block.id}
            type="button"
            onClick={() => onOpen(block)}
            className={[
              "archive-card text-left transition",
              changed ? "ring-2 ring-[#4a9a6f] animate-[pulse_1s_ease-in-out_3]" : ""
            ].join(" ")}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{block.icon} {block.title}</span>
              <span className="flex gap-1">
                {locked ? <span className="app-pill">✏ 已改</span> : null}
                {changed ? <span className="app-pill">刚更新</span> : null}
              </span>
            </div>
            {block.summary ? (
              <p className="mt-1 text-xs text-[color:var(--muted)]">{block.summary}</p>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/generator/BoardBlockGrid.tsx && git commit -m "feat(web): BoardBlockGrid 网格+卡片(骨架/闪烁/锁定标记)"`

---

### Task 8: BlockDetailModal（查看/编辑/删除/解锁）

**Files:**
- Create: `web/components/generator/BlockDetailModal.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

import { useState } from "react";

import type { BoardBlock, BoardField } from "@/lib/generatorBoard";

function fieldToText(field: BoardField): string {
  return Array.isArray(field.value) ? field.value.join("\n") : field.value;
}
function textToFieldValue(field: BoardField, text: string): string | string[] {
  return field.type === "stringList"
    ? text.split("\n").map((s) => s.trim()).filter(Boolean)
    : text;
}

export function BlockDetailModal({
  block,
  locked,
  onSave,
  onDelete,
  onUnlock,
  onClose
}: {
  block: BoardBlock;
  locked: boolean;
  onSave: (fields: BoardField[]) => void;
  onDelete: () => void;
  onUnlock: () => void;
  onClose: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(block.fields.map((f) => [f.key, fieldToText(f)]))
  );

  function handleSave() {
    const next = block.fields.map((f) => ({
      ...f,
      value: textToFieldValue(f, drafts[f.key] ?? fieldToText(f))
    }));
    onSave(next);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="surface-panel surface-panel-strong max-h-[85vh] w-full max-w-2xl overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="surface-title">
            {block.icon} {block.title}
            {locked ? <span className="app-pill ml-2">✏ 已手动修改</span> : null}
          </h3>
          <button className="app-button" type="button" onClick={onClose}>关闭</button>
        </div>

        <div className="mt-4 grid gap-4">
          {block.fields.map((f) => (
            <label key={f.key} className="grid gap-1">
              <span className="text-sm font-semibold">
                {f.label}
                {f.type === "stringList" ? (
                  <span className="ml-2 text-xs text-[color:var(--muted)]">每行一条</span>
                ) : null}
              </span>
              {f.type === "text" ? (
                <input
                  className="app-input"
                  value={drafts[f.key] ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [f.key]: e.target.value }))}
                />
              ) : (
                <textarea
                  className="app-input min-h-24 resize-y leading-6"
                  value={drafts[f.key] ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [f.key]: e.target.value }))}
                />
              )}
            </label>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <button className="app-button app-button-primary" type="button" onClick={handleSave}>保存</button>
          {locked ? (
            <button className="app-button" type="button" onClick={onUnlock} title="恢复 AI 最近一次生成的值并解除锁定">
              🔓 解锁 / 恢复 AI 原值
            </button>
          ) : null}
          {block.deletable ? (
            <button className="app-button" type="button" onClick={onDelete}>🗑 删除</button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/generator/BlockDetailModal.tsx && git commit -m "feat(web): BlockDetailModal 查看/编辑/删除/解锁"`

---

### Task 9: ChangeSummaryBar（顶部变更摘要条）

**Files:**
- Create: `web/components/generator/ChangeSummaryBar.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

import type { BoardModel, BoardCategoryId, BoardDiff } from "@/lib/generatorBoard";

export function ChangeSummaryBar({
  model,
  diff,
  onJump
}: {
  model: BoardModel;
  diff: BoardDiff;
  onJump: (id: BoardCategoryId) => void;
}) {
  const changed = model.categories.filter((c) => (diff.changedCategories[c.id] ?? 0) > 0);
  if (changed.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded border border-[#f0c9c0] bg-[#fff7f5] px-3 py-2 text-sm">
      <span>🔔 本次更新了：</span>
      {changed.map((c) => (
        <button key={c.id} type="button" className="app-pill" onClick={() => onJump(c.id)}>
          {c.label} +{diff.changedCategories[c.id]}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/generator/ChangeSummaryBar.tsx && git commit -m "feat(web): ChangeSummaryBar 变更摘要条"`

---

### Task 10: GenerationProgress（Tab 点亮式进度 + 思考收起）

**Files:**
- Create: `web/components/generator/GenerationProgress.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

export type ProgressItem = {
  id: string;
  label: string;
  status: "pending" | "running" | "done";
};

export function GenerationProgress({
  items,
  reasoning,
  content
}: {
  items: ProgressItem[];
  reasoning: string;
  content: string;
}) {
  const done = items.filter((i) => i.status === "done").length;
  return (
    <div className="surface-panel">
      <div className="flex flex-wrap items-center gap-2">
        {items.map((i) => (
          <span
            key={i.id}
            className={[
              "rounded-full border px-2 py-1 text-xs",
              i.status === "done"
                ? "border-[#4a9a6f] text-[#2b7a4b]"
                : i.status === "running"
                  ? "border-[#e0a23d] bg-[#fff7e8]"
                  : "border-[color:var(--border)] text-[color:var(--muted)]"
            ].join(" ")}
          >
            {i.status === "done" ? "✓ " : i.status === "running" ? "⏳ " : ""}
            {i.label}
          </span>
        ))}
      </div>
      <p className="mt-2 text-xs text-[color:var(--muted)]">已生成 {done}/{items.length} 类</p>
      {reasoning || content ? (
        <details className="mt-2 rounded border border-[color:var(--border)]">
          <summary className="cursor-pointer px-3 py-2 text-xs text-[color:var(--muted)]">
            🧠 查看 AI 思考过程
          </summary>
          <pre className="app-wrap-text max-h-64 overflow-auto whitespace-pre-wrap border-t border-[color:var(--border)] p-3 text-xs leading-5 text-[color:var(--muted)]">
            {reasoning || "（无思考流）"}
            {content ? `\n\n—— 正文 ——\n${content}` : ""}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/generator/GenerationProgress.tsx && git commit -m "feat(web): GenerationProgress 进度点亮+思考收起"`

---

### Task 11: ChatDock + ChatHistorySheet（底部对话停靠 + 上滑历史）

**Files:**
- Create: `web/components/generator/ChatHistorySheet.tsx`
- Create: `web/components/generator/ChatDock.tsx`

- [ ] **Step 1: 写 ChatHistorySheet**

```tsx
"use client";

import type { GeneratorMessage } from "@/lib/types";

export function ChatHistorySheet({
  open,
  history,
  onClose
}: {
  open: boolean;
  history: GeneratorMessage[];
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/30" onClick={onClose}>
      <div className="surface-panel max-h-[60vh] w-full overflow-auto rounded-b-none" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="surface-title">对话历史</h3>
          <button className="app-button" type="button" onClick={onClose}>收起</button>
        </div>
        <div className="mt-3 grid gap-2">
          {history.length === 0 ? (
            <p className="surface-subtle">暂无对话。</p>
          ) : (
            history.map((m, i) => (
              <div
                key={`${m.role}-${i}`}
                className={
                  m.role === "user"
                    ? "archive-card archive-card-green text-sm leading-6"
                    : "archive-card archive-card-accent text-sm leading-6"
                }
              >
                <span className="font-semibold">{m.role === "user" ? "你" : "冒险引导"}</span>
                <p className="mt-1 text-[color:var(--muted)]">{m.content}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 写 ChatDock（桌面可拖高）**

```tsx
"use client";

import { useRef, useState } from "react";

export function ChatDock({
  latestReply,
  input,
  disabled,
  onInput,
  onSend,
  onToggleHistory
}: {
  latestReply: string;
  input: string;
  disabled: boolean;
  onInput: (value: string) => void;
  onSend: () => void;
  onToggleHistory: () => void;
}) {
  const [height, setHeight] = useState(150);
  const dragging = useRef(false);

  function onHandleDown(e: React.PointerEvent) {
    dragging.current = true;
    (e.target as Element).setPointerCapture(e.pointerId);
  }
  function onHandleMove(e: React.PointerEvent) {
    if (!dragging.current) return;
    setHeight((h) => Math.min(420, Math.max(100, h - e.movementY)));
  }
  function onHandleUp() {
    dragging.current = false;
  }

  return (
    <div className="sticky bottom-0 z-20 border-t border-[color:var(--border)] bg-[color:var(--background)]">
      <div
        className="mx-auto h-2 w-16 cursor-row-resize rounded-full bg-[color:var(--border)]"
        onPointerDown={onHandleDown}
        onPointerMove={onHandleMove}
        onPointerUp={onHandleUp}
        title="拖动调整高度"
      />
      <div className="px-1 py-2" style={{ height }}>
        {latestReply ? (
          <p className="mb-2 line-clamp-2 text-xs text-[color:var(--muted)]">💬 引导：{latestReply}</p>
        ) : null}
        <div className="flex h-[calc(100%-2rem)] gap-2">
          <textarea
            className="app-input flex-1 resize-none leading-6"
            placeholder="追加要求 / 修正方向…"
            value={input}
            onChange={(e) => onInput(e.target.value)}
          />
          <div className="flex flex-col gap-2">
            <button className="app-button app-button-primary" type="button" disabled={disabled || !input.trim()} onClick={onSend}>发送</button>
            <button className="app-button" type="button" onClick={onToggleHistory}>⌃ 历史</button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 4: Commit** — `git add web/components/generator/ChatDock.tsx web/components/generator/ChatHistorySheet.tsx && git commit -m "feat(web): ChatDock 底部对话停靠(可拖高)+ChatHistorySheet"`

---

### Task 12: SettingsBoard（看板容器，组合所有子组件）

**Files:**
- Create: `web/components/generator/SettingsBoard.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

import { useState } from "react";

import { BoardTabs } from "@/components/generator/BoardTabs";
import { BoardBlockGrid } from "@/components/generator/BoardBlockGrid";
import { BlockDetailModal } from "@/components/generator/BlockDetailModal";
import { ChangeSummaryBar } from "@/components/generator/ChangeSummaryBar";
import type {
  BoardBlock,
  BoardCategoryId,
  BoardDiff,
  BoardField,
  BoardModel
} from "@/lib/generatorBoard";

export function SettingsBoard({
  model,
  diff,
  lockedIds,
  loading,
  onEditBlock,
  onDeleteBlock,
  onUnlockBlock
}: {
  model: BoardModel;
  diff: BoardDiff;
  lockedIds: string[];
  loading: boolean;
  onEditBlock: (block: BoardBlock, fields: BoardField[]) => void;
  onDeleteBlock: (block: BoardBlock) => void;
  onUnlockBlock: (block: BoardBlock) => void;
}) {
  const [activeTab, setActiveTab] = useState<BoardCategoryId>("world");
  const [openBlock, setOpenBlock] = useState<BoardBlock | null>(null);

  const current = model.categories.find((c) => c.id === activeTab) ?? model.categories[0];

  return (
    <section className="surface-panel surface-panel-strong">
      <ChangeSummaryBar model={model} diff={diff} onJump={setActiveTab} />
      <BoardTabs
        categories={model.categories}
        activeTab={activeTab}
        changedCategories={diff.changedCategories}
        onSelect={setActiveTab}
      />
      <BoardBlockGrid
        blocks={current.blocks}
        changedBlockIds={diff.changedBlockIds}
        lockedIds={lockedIds}
        loading={loading}
        onOpen={setOpenBlock}
      />
      {openBlock ? (
        <BlockDetailModal
          block={openBlock}
          locked={lockedIds.includes(openBlock.id)}
          onSave={(fields) => { onEditBlock(openBlock, fields); setOpenBlock(null); }}
          onDelete={() => { onDeleteBlock(openBlock); setOpenBlock(null); }}
          onUnlock={() => { onUnlockBlock(openBlock); setOpenBlock(null); }}
          onClose={() => setOpenBlock(null)}
        />
      ) : null}
    </section>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/components/generator/SettingsBoard.tsx && git commit -m "feat(web): SettingsBoard 看板容器"`

---

- [ ] **Phase B 收尾：整体构建** — Run: `cd web && npm run build` — Expected: tsc + lint 通过（组件此时未被页面引用也应编译通过）。

---

## Phase C — 页面集成

### Task 13: api.ts 增加 locked_fields

**Files:**
- Modify: `web/lib/api.ts:436-445`（`createGeneratorChatJob`）

- [ ] **Step 1: 改签名透传 locked_fields**

把 `createGeneratorChatJob` 改为：

```ts
export async function createGeneratorChatJob(payload: {
  user_input: string;
  history: GeneratorMessage[];
  confirmed_requirements: Record<string, unknown>;
  locked_fields?: string[];
}): Promise<GeneratorChatJobCreateResponse> {
  return requestJson<GeneratorChatJobCreateResponse>("/api/generator/chat-jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: Commit** — `git add web/lib/api.ts && git commit -m "feat(web): createGeneratorChatJob 透传 locked_fields"`

---

### Task 14: 重写 page.tsx 为看板布局

**Files:**
- Modify（整体替换）: `web/app/games/new/page.tsx`

- [ ] **Step 1: 替换整个文件**

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ChatDock } from "@/components/generator/ChatDock";
import { ChatHistorySheet } from "@/components/generator/ChatHistorySheet";
import { GenerationProgress, type ProgressItem } from "@/components/generator/GenerationProgress";
import { SettingsBoard } from "@/components/generator/SettingsBoard";
import {
  createGeneratedGame,
  createGeneratorChatJob,
  createGeneratorFinalizeJob,
  getActiveGeneratorChatJob,
  getActiveGeneratorFinalizeJob
} from "@/lib/api";
import {
  BOARD_CATEGORIES,
  buildBoardModel,
  deleteBlock,
  diffBoard,
  lockBlock,
  unlockBlock,
  writeBlockFields,
  type BoardBlock,
  type BoardDiff,
  type BoardField,
  type BoardModel
} from "@/lib/generatorBoard";
import {
  createInitialChatProcess,
  createInitialFinalizeProcess,
  waitForChatJobWithStream,
  waitForFinalizeJobWithStream
} from "@/lib/generatorJobStream";
import type {
  GeneratedGameConfig,
  GeneratorChatJobRead,
  GeneratorFinalizeJobRead,
  GeneratorMessage
} from "@/lib/types";

// confirmed 阶段的 block id 恰为 confirmed_requirements 字段名，用于过滤出可发后端的 locked_fields。
const CONFIRMED_FIELD_IDS = [
  "story_background", "core_premise", "tone_preferences",
  "playstyle_preferences", "must_include", "forbidden_content"
];

const EMPTY_DIFF: BoardDiff = {
  changedCategories: Object.fromEntries(
    BOARD_CATEGORIES.map((c) => [c.id, 0])
  ) as BoardDiff["changedCategories"],
  changedBlockIds: new Set<string>()
};

const sampleIdea =
  "黑暗武侠，故事发生在雁回镇义庄。主角是失忆镖师，必须出现雨夜义庄、红伞女人和失踪镖队。不要变成修仙飞升，也不要太快揭露主角身世。";

export default function NewGamePage() {
  const router = useRouter();
  const [chatInput, setChatInput] = useState(sampleIdea);
  const [history, setHistory] = useState<GeneratorMessage[]>([]);
  const [confirmed, setConfirmed] = useState<Record<string, unknown>>({});
  const [stage, setStage] = useState<string | null>(null);
  const [generatedConfig, setGeneratedConfig] = useState<GeneratedGameConfig | null>(null);
  const [lockedIds, setLockedIds] = useState<string[]>([]);
  const [lastDiff, setLastDiff] = useState<BoardDiff>(EMPTY_DIFF);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [chatProcess, setChatProcess] = useState<GeneratorChatJobRead | null>(null);
  const [finalizeProcess, setFinalizeProcess] = useState<GeneratorFinalizeJobRead | null>(null);

  // 解锁时恢复 AI 原值用：最近一次 AI 产出的快照。
  const aiConfirmedRef = useRef<Record<string, unknown>>({});
  const aiSettingsRef = useRef<Record<string, unknown>>({});
  // 每轮开始前的看板基线，用于 diff。
  const baselineRef = useRef<BoardModel | null>(null);

  const model: BoardModel = useMemo(() => {
    if (generatedConfig) {
      return buildBoardModel({ source: "settings", settings: generatedConfig.story_settings });
    }
    return buildBoardModel({ source: "confirmed", confirmed });
  }, [generatedConfig, confirmed]);

  function currentModel(): BoardModel {
    if (generatedConfig) {
      return buildBoardModel({ source: "settings", settings: generatedConfig.story_settings });
    }
    return buildBoardModel({ source: "confirmed", confirmed });
  }

  // 恢复进行中任务（沿用原逻辑，简化为只接管结果）。
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const [fin, chat] = await Promise.all([
          getActiveGeneratorFinalizeJob(),
          getActiveGeneratorChatJob()
        ]);
        if (cancelled) return;
        if (fin) {
          setPendingAction("finalize");
          setFinalizeProcess(fin);
          const done = await waitForFinalizeJobWithStream(fin.id, () => {}, setFinalizeProcess, fin);
          if (cancelled || !done.config) return;
          aiSettingsRef.current = done.config.story_settings;
          setGeneratedConfig(done.config);
          setPendingAction(null);
          return;
        }
        if (chat) {
          setPendingAction("chat");
          setChatProcess(chat);
          const done = await waitForChatJobWithStream(chat.id, () => {}, setChatProcess, chat);
          if (cancelled || !done.response) return;
          aiConfirmedRef.current = done.response.confirmed_requirements;
          setConfirmed(done.response.confirmed_requirements);
          setStage(done.response.stage);
          setPendingAction(null);
        }
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "恢复生成任务失败。");
        setPendingAction(null);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleChat() {
    if (!chatInput.trim()) return;
    setError(null);
    baselineRef.current = currentModel();
    setPendingAction("chat");
    const lockedConfirmed = lockedIds.filter((id) => CONFIRMED_FIELD_IDS.includes(id));
    try {
      const job = await createGeneratorChatJob({
        user_input: chatInput,
        history,
        confirmed_requirements: confirmed,
        locked_fields: lockedConfirmed
      });
      setChatProcess(createInitialChatProcess(job.id, job.status));
      const done = await waitForChatJobWithStream(job.id, () => {}, setChatProcess);
      if (!done.response) throw new Error("设定确认任务已完成，但没有返回内容。");
      const aiConfirmed = done.response.confirmed_requirements;
      aiConfirmedRef.current = aiConfirmed;
      // 客户端兜底强制锁定：把用户锁定字段的旧值覆盖回 AI 结果，防被改回。
      const merged = { ...aiConfirmed };
      for (const id of lockedConfirmed) merged[id] = confirmed[id];
      setConfirmed(merged);
      setStage(done.response.stage);
      setHistory((cur) => [
        ...cur,
        { role: "user", content: chatInput },
        { role: "assistant", content: done.response.assistant_reply }
      ]);
      setChatInput("");
      const next = buildBoardModel({ source: "confirmed", confirmed: merged });
      setLastDiff(diffBoard(baselineRef.current, next));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "冒险设定确认失败。");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleFinalize() {
    setError(null);
    baselineRef.current = currentModel();
    setPendingAction("finalize");
    try {
      const job = await createGeneratorFinalizeJob({
        concept: confirmed.story_background ? String(confirmed.story_background) : sampleIdea,
        history,
        confirmed_requirements: confirmed
      });
      setFinalizeProcess(createInitialFinalizeProcess(job.id, job.status));
      const done = await waitForFinalizeJobWithStream(job.id, () => {}, setFinalizeProcess);
      if (!done.config) throw new Error("生成任务已完成，但没有返回冒险世界。");
      aiSettingsRef.current = done.config.story_settings;
      setLockedIds([]); // 进入 settings 阶段，confirmed 阶段的锁定 id 不再适用
      setGeneratedConfig(done.config);
      const next = buildBoardModel({ source: "settings", settings: done.config.story_settings });
      setLastDiff(diffBoard(baselineRef.current, next));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "冒险世界生成失败。");
    } finally {
      setPendingAction(null);
    }
  }

  function handleEditBlock(block: BoardBlock, fields: BoardField[]) {
    if (generatedConfig) {
      const settings = writeBlockFields(generatedConfig.story_settings, block.address, fields);
      setGeneratedConfig({ ...generatedConfig, story_settings: settings });
    } else {
      setConfirmed((cur) => writeBlockFields(cur, block.address, fields));
    }
    setLockedIds((ids) => lockBlock(ids, block.id));
  }

  function handleDeleteBlock(block: BoardBlock) {
    if (generatedConfig) {
      const settings = deleteBlock(generatedConfig.story_settings, block.address);
      setGeneratedConfig({ ...generatedConfig, story_settings: settings });
    } else {
      setConfirmed((cur) => deleteBlock(cur, block.address));
    }
    setLockedIds((ids) => unlockBlock(ids, block.id));
  }

  function handleUnlockBlock(block: BoardBlock) {
    // 恢复 AI 原值：从最近 AI 快照里按 address 取该 block 的字段值写回。
    const aiSource = generatedConfig ? aiSettingsRef.current : aiConfirmedRef.current;
    const aiModel = buildBoardModel(
      generatedConfig
        ? { source: "settings", settings: aiSource }
        : { source: "confirmed", confirmed: aiSource }
    );
    const aiBlock = aiModel.categories.flatMap((c) => c.blocks).find((b) => b.id === block.id);
    if (aiBlock) {
      handleEditBlockRaw(block, aiBlock.fields);
    }
    setLockedIds((ids) => unlockBlock(ids, block.id));
  }

  // 与 handleEditBlock 相同的写回，但不加锁（供解锁恢复用）。
  function handleEditBlockRaw(block: BoardBlock, fields: BoardField[]) {
    if (generatedConfig) {
      const settings = writeBlockFields(generatedConfig.story_settings, block.address, fields);
      setGeneratedConfig({ ...generatedConfig, story_settings: settings });
    } else {
      setConfirmed((cur) => writeBlockFields(cur, block.address, fields));
    }
  }

  async function handleCreateGenerated() {
    if (!generatedConfig) return;
    setError(null);
    setPendingAction("create-generated");
    try {
      const response = await createGeneratedGame(generatedConfig);
      router.push(`/games/${response.game.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建冒险失败。");
    } finally {
      setPendingAction(null);
    }
  }

  const canFinalize = stage === "ready_to_generate" && !generatedConfig;
  const progressItems: ProgressItem[] = BOARD_CATEGORIES.filter((c) => c.id !== "advanced").map(
    (c) => ({
      id: c.id,
      label: c.label,
      status: generatedConfig ? "done" : pendingAction === "finalize" ? "running" : "pending"
    })
  );
  const reasoning = (generatedConfig ? finalizeProcess : chatProcess)?.reasoning_content ?? "";
  const content = (generatedConfig ? finalizeProcess : chatProcess)?.content_buffer ?? "";

  return (
    <AppShell>
      <section className="game-page-hero">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Link className="app-button mb-4 w-fit" href="/games">返回存档</Link>
            <p className="game-page-eyebrow">Adventure Forge</p>
            <h1 className="game-page-title">创建冒险</h1>
          </div>
          <div className="flex gap-2">
            {canFinalize ? (
              <button
                className="app-button app-button-primary"
                disabled={pendingAction !== null}
                onClick={handleFinalize}
                type="button"
              >
                {pendingAction === "finalize" ? "生成世界中..." : "生成冒险世界"}
              </button>
            ) : null}
            {generatedConfig ? (
              <>
                <button
                  className="app-button app-button-primary"
                  disabled={pendingAction !== null}
                  onClick={handleCreateGenerated}
                  type="button"
                >
                  {pendingAction === "create-generated" ? "创建中..." : "确认并开始冒险"}
                </button>
                <button
                  className="app-button"
                  disabled={pendingAction !== null}
                  onClick={handleFinalize}
                  title="复用已确认设定重新生成一个世界"
                  type="button"
                >
                  重新生成
                </button>
              </>
            ) : null}
          </div>
        </div>
      </section>

      {error ? <section className="app-alert">{error}</section> : null}

      {pendingAction === "finalize" || (generatedConfig && content) ? (
        <GenerationProgress items={progressItems} reasoning={reasoning} content={content} />
      ) : null}

      <SettingsBoard
        model={model}
        diff={lastDiff}
        lockedIds={lockedIds}
        loading={pendingAction === "chat" || pendingAction === "finalize"}
        onEditBlock={handleEditBlock}
        onDeleteBlock={handleDeleteBlock}
        onUnlockBlock={handleUnlockBlock}
      />

      <ChatDock
        latestReply={history.length ? history[history.length - 1].content : ""}
        input={chatInput}
        disabled={pendingAction !== null}
        onInput={setChatInput}
        onSend={handleChat}
        onToggleHistory={() => setHistoryOpen((v) => !v)}
      />
      <ChatHistorySheet open={historyOpen} history={history} onClose={() => setHistoryOpen(false)} />
    </AppShell>
  );
}
```

- [ ] **Step 2: 类型检查** — Run: `cd web && npx tsc --noEmit` — Expected: 无错误。
- [ ] **Step 3: 构建** — Run: `cd web && npm run build` — Expected: 构建通过。
- [ ] **Step 4: Commit** — `git add web/app/games/new/page.tsx && git commit -m "feat(web): 创建冒险页重写为分类看板+对话停靠+改动闪烁+手改锁定"`

> 备注：P1 进度为「粗粒度」（生成中全部 running，完成全部 done）。把 finalize 分段事件（`section_update_callback` 的 key/label）精确映射到各 Tab 的「逐类点亮」留作 P2 增强，不阻塞本期。

---

## Phase D — 后端锁定支持

### Task 15: locked_fields schema + interview 注入 + prompt 规则

**Files:**
- Modify: `api/app/schemas/generator.py:17-20`（`GeneratorChatRequest`）
- Modify: `api/app/services/game_generator.py`（`_build_interview_messages`）
- Modify: `api/app/prompts/generator_interview.md`
- Test: `api/tests/test_generator_locked_fields.py`

- [ ] **Step 1: 写失败测试**

Create `api/tests/test_generator_locked_fields.py`：

```python
from app.schemas.generator import GeneratorChatRequest
from app.services.game_generator import GameGenerator


def test_request_accepts_locked_fields():
    req = GeneratorChatRequest(
        user_input="测试",
        confirmed_requirements={"story_background": "占位背景"},
        locked_fields=["story_background"],
    )
    assert req.locked_fields == ["story_background"]


def test_request_locked_fields_defaults_empty():
    req = GeneratorChatRequest(user_input="测试")
    assert req.locked_fields == []


def test_interview_messages_include_locked_instruction():
    req = GeneratorChatRequest(
        user_input="测试",
        confirmed_requirements={"story_background": "占位背景"},
        locked_fields=["story_background"],
    )
    messages = GameGenerator._build_interview_messages("PROMPT", req)
    joined = "\n".join(m["content"] for m in messages)
    assert "锁定" in joined
    assert "story_background" in joined


def test_interview_messages_no_locked_section_when_empty():
    req = GeneratorChatRequest(user_input="测试", confirmed_requirements={})
    messages = GameGenerator._build_interview_messages("PROMPT", req)
    joined = "\n".join(m["content"] for m in messages)
    assert "用户已锁定" not in joined
```

- [ ] **Step 2: 运行验证失败**

Run: `docker compose exec api pytest tests/test_generator_locked_fields.py -v`
Expected: FAIL（`locked_fields` 字段不存在）。

- [ ] **Step 3: schema 加字段**

`api/app/schemas/generator.py` 的 `GeneratorChatRequest` 改为：

```python
class GeneratorChatRequest(BaseModel):
    user_input: str = Field(min_length=1)
    history: list[GeneratorMessage] = Field(default_factory=list)
    confirmed_requirements: dict[str, Any] = Field(default_factory=dict)
    locked_fields: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: _build_interview_messages 注入锁定指令**

在 `api/app/services/game_generator.py` 的 `_build_interview_messages` 中，紧接「当前已确认需求」那段 `if request.confirmed_requirements:` 块之后、`messages.extend(... history ...)` 之前，插入：

```python
        if request.locked_fields:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "用户已锁定以下字段（手动修改过），必须原样保留其值、"
                        "不得改写或还原成旧值；但仍要读取这些值作为上下文，"
                        "让新生成的内容与之保持联动一致："
                        f"{json.dumps(request.locked_fields, ensure_ascii=False)}"
                    ),
                }
            )
```

- [ ] **Step 5: prompt 加规则**

在 `api/app/prompts/generator_interview.md` 的编号规则列表末尾（第 6 条后）追加：

```
7. 若系统消息标注了「用户已锁定」的字段，对这些字段必须原样输出用户给定的值，禁止改写、补充或还原为更早的版本；其它字段照常抽取，并保证与锁定字段在设定上一致、不矛盾。
```

- [ ] **Step 6: 运行验证通过**

Run: `docker compose exec api pytest tests/test_generator_locked_fields.py -v`
Expected: 4 passed。

- [ ] **Step 7: 全量回归**

Run: `docker compose exec api pytest tests/`
Expected: 既有全部通过 + 新增 4 个。

- [ ] **Step 8: Commit**

```bash
git add api/app/schemas/generator.py api/app/services/game_generator.py api/app/prompts/generator_interview.md api/tests/test_generator_locked_fields.py
git commit -m "feat(api): interview 支持 locked_fields（锁定字段不得改回，仍作上下文）"
```

---

### Task 16: 部署、端到端验证、文档

**Files:**
- Modify: `docs/OPTIMIZATION_PLAN.md`

- [ ] **Step 1: 重建并重启（Docker 不挂源码，必须重建镜像）**

Run: `docker compose up -d --build api worker web`
Expected: 容器更新无报错。

- [ ] **Step 2: 前端纯函数测试 + 构建**

Run: `cd web && npm test && npm run build`
Expected: vitest 全过；构建通过。

- [ ] **Step 3: 手动端到端走查**

按以下清单在浏览器逐项确认（创建冒险页）：
1. 输入想法 → 发送 → 看板 ① 世界与基调 / ⑤ 约束出现 block，对应 Tab 出现 +N 角标、block 闪烁。
2. 追加一句修正 → 摘要条与角标按本轮 diff 刷新（上一轮指示被替换）。
3. 点开某 block 编辑保存 → 卡片标「✏ 已改」；再发一轮对话，确认该值不被改回。
4. 点该 block →「🔓 解锁/恢复 AI 原值」→ 值恢复、标记消失。
5. 「生成冒险世界」→ 进度条 6 类；完成后角色/剧情/机制/素材 Tab 填满。
6. 编辑一个角色 block 保存 →「确认并开始冒险」→ 进存档后该角色为编辑后的值。
7. 桌面拖动对话停靠条把手可调高；「⌃ 历史」上滑显示完整对话。

- [ ] **Step 4: OPTIMIZATION_PLAN 追加 Round 条目**

在 `docs/OPTIMIZATION_PLAN.md` §1 顶部新增 `### Round N (2026-06-04)` 条目，记录：创建冒险页重设计（看板/Tab/改动闪烁/手改锁定）、新增前端 vitest、`generator_interview.md` 新增规则 7、`GeneratorChatRequest.locked_fields`。**不修改历史 Round。**

- [ ] **Step 5: Commit**

```bash
git add docs/OPTIMIZATION_PLAN.md
git commit -m "docs: OPTIMIZATION_PLAN 追加创建冒险页重设计 Round 条目"
```

---

## 自审（Self-Review）

**Spec 覆盖核对：**
- §3 布局 A → Task 14 页面（看板主体 + 底部 ChatDock）✓
- §4 六分类 Tab + 字段映射 → Task 2/3（buildBoardModel）+ Task 6（BoardTabs）✓
- §5 改动指示（diff/+N/闪烁/摘要条/当次常驻下次重算）→ Task 4（diffBoard）+ Task 6/7/9 + Task 14（每轮 setLastDiff，baselineRef 重算）✓
- §6 block 详情弹窗（查看/编辑/删除/解锁）→ Task 8（BlockDetailModal）✓
- §7 锁定语义（不改回 + AI 借鉴联动 + 解锁恢复）→ Task 5（锁定工具）+ Task 14（客户端兜底 + 解锁恢复）+ Task 15（后端 prompt 规则 7 + 注入）✓
- §8 进度点亮 + 思考收起 → Task 10（GenerationProgress）+ Task 14（progressItems）✓（P1 粗粒度，已注明）
- §11 后端最小改动 → Task 15（schema + 注入 + 规则）✓
- §12 测试 → Task 2-5 vitest + Task 15 pytest + Task 16 构建/走查 ✓
- §13 分期：P1 不做「单独重生成」→ 计划无此任务 ✓

**Placeholder 扫描：** 无 TBD/TODO；每个改码步骤含完整代码或完整命令。P1 进度粗粒度已显式标注为有意取舍（非占位）。

**类型一致性核对：**
- `buildBoardModel` 入参联合类型 `{source:"settings",settings}` / `{source:"confirmed",confirmed}` 在 Task 2/3/14 一致。
- `BoardField.value: string | string[]`、`writeBlockFields(source,address,fields)`、`deleteBlock(source,address)`、`lockBlock/unlockBlock/isLocked(ids,id)` 签名在 Task 5/8/12/14 一致。
- `BoardDiff{changedCategories,changedBlockIds}`、`diffBoard(prev|null,next)` 在 Task 4/6/7/9/14 一致。
- `ProgressItem{id,label,status}` 在 Task 10/14 一致。
- 后端 `locked_fields` 在 schema / `_build_interview_messages` / api.ts / page 四处命名一致。
