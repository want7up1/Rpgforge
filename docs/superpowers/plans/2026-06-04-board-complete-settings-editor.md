# 看板完整设定编辑面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让设定看板覆盖并可视编辑 story_settings 的**全部**字段（含 home_base / worldview 公开隐藏事实 / act 完成锚点等嵌套结构），并支持在已有剧本里**手动新增数组项**（角色/机制/幕/素材/主线/行动风格）。

**Architecture:** 纯前端。`generatorBoard.ts` 的字段层改为「FIELD_SPEC 配置精修 + 实际数据派生兜底」生成完整 `BoardField[]`，扩展字段类型系统（number/bool/objectList/keyValue/json）；`BlockDetailModal` 用统一 `BoardFieldEditor` 按类型渲染；`writeBlockFields` 无损回写各类型；空块默认折叠（开关显隐）；新增数组项走受控回调 `onAddItem` → 设定页 `updateGameConfig`(+版本快照)。后端零改动。

**Tech Stack:** Next.js + React + TS + Tailwind；vitest（纯函数）。块粒度与 block.id/address 规则保持兼容（保护生成页 diff 与模块提取）。

**设计依据：** `docs/superpowers/specs/2026-06-04-board-complete-settings-editor-design.md`

> 从含特性1/2/修复的当前 `main` 切新分支执行（如 `feat/board-complete-editor`）。

---

## 文件结构

**修改**
- `web/lib/generatorBoard.ts` — 扩字段类型/值；`FIELD_SPECS` 配置 + `deriveFields` 数据派生；`buildFromSettings` 用之补全字段 + 加 home_base 块；扩 `writeBlockFields`；新增 `createEmptyItem`/`appendItem`/`ARRAY_SPECS`
- `web/lib/generatorBoard.test.ts` — 新增覆盖/往返/新增项 用例
- `web/components/board/BlockDetailModal.tsx` — 用 `BoardFieldEditor` + 类型化 drafts + 「新建」空白态
- `web/components/board/BoardBlockGrid.tsx` — 空块过滤 + 「＋新增」入口
- `web/components/board/SettingsBoard.tsx` — `showEmpty` 开关 + `onAddItem` + 新建表单
- `web/app/games/[id]/settings/page.tsx` — 接 `onAddItem`（appendItem→persist）
- `docs/OPTIMIZATION_PLAN.md` — 追加 Round

**新增**
- `web/components/board/BoardFieldEditor.tsx` — 单字段编辑器（按 type 渲染 text/textarea/number/bool/stringList/objectList/keyValue/json）

---

## Phase A — 纯逻辑（generatorBoard.ts，vitest）

### Task 1: 扩展字段类型与值

**Files:** Modify `web/lib/generatorBoard.ts`

- [ ] **Step 1: 改类型定义**

把 `BoardFieldType`/`BoardField` 段替换为：

```ts
export type BoardFieldType =
  | "text" | "textarea" | "number" | "bool"
  | "stringList" | "objectList" | "keyValue" | "json";

// objectList 每个子对象渲染哪些子字段
export type SubFieldSpec = {
  key: string;
  label: string;
  type: "text" | "textarea" | "number" | "bool" | "stringList";
};

export type BoardFieldValue =
  | string | number | boolean | string[]
  | Record<string, unknown> | Record<string, unknown>[];

export type BoardField = {
  key: string;
  label: string;
  value: BoardFieldValue;
  type: BoardFieldType;
  itemFields?: SubFieldSpec[]; // 仅 objectList
};
```

- [ ] **Step 2: 让现有代码编译通过**

现有 `objectFields` 产出的 field（text/textarea/stringList）已是新 union 子集，无需改。`blockFingerprint` 已用 `JSON.stringify`（兼容任意值）。运行 `cd web && npx tsc --noEmit`，若 `writeBlockFields`/其它处因 value 收窄报错，按提示把 `string | string[]` 标注放宽到 `BoardFieldValue`（仅类型，不改逻辑）。

- [ ] **Step 3: 验证**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: vitest 全过（24）、tsc 干净。

- [ ] **Step 4: Commit**

```bash
git checkout -b feat/board-complete-editor
git add web/lib/generatorBoard.ts
git commit -m "feat(web): 扩展 BoardField 类型系统(number/bool/objectList/keyValue/json)"
```

---

### Task 2: 数据派生字段 + 补全所有块（TDD）

**Files:** Modify `web/lib/generatorBoard.ts`、`web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试**

在 `web/lib/generatorBoard.test.ts` 追加：

```ts
describe("全字段覆盖（数据派生）", () => {
  const settings = {
    game_profile: { title: "雁回镇", genre: "武侠", description: "失踪案" },
    worldview: { summary: "雨夜义庄", public_facts: ["镇有义庄"], hidden_facts: ["庄主是凶手"] },
    home_base: { name: "镖局", services: ["休整"] },
    core_characters: [{ name: "主角", role: "protagonist", dramatic_function: "调查者", portrait_prompt: "p" }],
    act_plan: [{
      id: "act_1", title: "序", objective: "查案",
      allowed_reveals: ["红伞"], forbidden_reveals: ["真凶"],
      completion_anchors: [{ id: "act_1_a1", title: "入庄", required: true }]
    }],
    generation_parameters: { target_min: 1200, paragraph_max: 8 }
  };
  function blockById(id: string) {
    return buildBoardModel({ source: "settings", settings })
      .categories.flatMap((c) => c.blocks).find((b) => b.id === id);
  }

  it("game_profile 含 description 字段（数据里有就出）", () => {
    const f = blockById("game_profile")!.fields.map((x) => x.key);
    expect(f).toContain("description");
  });
  it("worldview 含 public_facts/hidden_facts（stringList）", () => {
    const fs = blockById("worldview")!.fields;
    expect(fs.find((x) => x.key === "public_facts")?.type).toBe("stringList");
    expect(fs.find((x) => x.key === "hidden_facts")?.type).toBe("stringList");
  });
  it("home_base 块存在且字段派生", () => {
    const b = blockById("home_base");
    expect(b).toBeTruthy();
    expect(b!.fields.find((x) => x.key === "services")?.type).toBe("stringList");
  });
  it("角色块含 dramatic_function/portrait_prompt 等全字段", () => {
    const keys = blockById("core_characters:主角")!.fields.map((x) => x.key);
    expect(keys).toEqual(expect.arrayContaining(["dramatic_function", "portrait_prompt"]));
  });
  it("act 块含 completion_anchors(objectList) + reveals(stringList)", () => {
    const fs = blockById("act_plan:act_1")!.fields;
    const anchors = fs.find((x) => x.key === "completion_anchors")!;
    expect(anchors.type).toBe("objectList");
    expect(anchors.itemFields!.find((s) => s.key === "required")?.type).toBe("bool");
    expect(fs.find((x) => x.key === "allowed_reveals")?.type).toBe("stringList");
  });
  it("generation_parameters 数值字段为 number", () => {
    expect(blockById("generation_parameters")!.fields.find((x) => x.key === "target_min")?.type).toBe("number");
  });
});
```

- [ ] **Step 2: 运行验证失败**

Run: `cd web && npm test`
Expected: FAIL（缺 home_base 块、缺字段等）。

- [ ] **Step 3: 实现数据派生 + 补全**

在 `web/lib/generatorBoard.ts` 加类型推断 + 派生 + 字段规格，并替换相关块构建：

```ts
// 长文本键（用 textarea）
const TEXTAREA_KEYS = new Set([
  "description", "objective", "rule", "content", "summary", "premise",
  "core_fantasy", "central_mystery", "main_goal", "emotional_arc",
  "narrative_style", "appearance", "relationship_arc", "dramatic_question",
  "usage", "public_info", "gm_secret", "identity", "logline", "completion_signal"
]);
const BOOL_KEYS = new Set(["required", "enabled", "always_on", "optional"]);

function inferType(key: string, value: unknown): BoardFieldType {
  if (BOOL_KEYS.has(key)) return "bool";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "bool";
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v === "string")) return "stringList";
    if (value.length > 0 && value.every((v) => v && typeof v === "object" && !Array.isArray(v))) {
      return "objectList";
    }
    return value.length === 0 ? "stringList" : "json";
  }
  if (value && typeof value === "object") return "keyValue";
  return TEXTAREA_KEYS.has(key) ? "textarea" : "text";
}

function defaultValueFor(type: BoardFieldType): BoardFieldValue {
  switch (type) {
    case "number": return 0;
    case "bool": return false;
    case "stringList": return [];
    case "objectList": return [];
    case "keyValue": return {};
    case "json": return {};
    default: return "";
  }
}

// completion_anchors 子字段规格
const ANCHOR_ITEM_FIELDS: SubFieldSpec[] = [
  { key: "id", label: "id", type: "text" },
  { key: "title", label: "标题", type: "text" },
  { key: "required", label: "必需", type: "bool" },
  { key: "description", label: "描述", type: "textarea" },
  { key: "completion_signal", label: "完成信号", type: "text" }
];

// 按"已知字段规格 + 数据里出现的额外键"派生 BoardField[]
// spec: 有序的已知键（决定 label/type/顺序、空块占位）；data 里多出的键按推断补上（防漏）
function deriveFields(
  data: Record<string, unknown>,
  spec: { key: string; label: string; type?: BoardFieldType; itemFields?: SubFieldSpec[] }[]
): BoardField[] {
  const out: BoardField[] = [];
  const used = new Set<string>();
  for (const s of spec) {
    used.add(s.key);
    const type = s.type ?? inferType(s.key, data[s.key]);
    const raw = data[s.key];
    const value = (raw === undefined || raw === null) ? defaultValueFor(type) : (raw as BoardFieldValue);
    const field: BoardField = { key: s.key, label: s.label, value, type };
    if (type === "objectList") field.itemFields = s.itemFields ?? ANCHOR_ITEM_FIELDS;
    out.push(field);
  }
  // data 里多出的键（规格没覆盖）→ 推断补上，杜绝遗漏（不漂移）
  for (const [k, v] of Object.entries(data)) {
    if (used.has(k) || k === "id") continue;
    const type = inferType(k, v);
    const field: BoardField = { key: k, label: label(k), value: (v as BoardFieldValue) ?? defaultValueFor(type), type };
    if (type === "objectList") field.itemFields = ANCHOR_ITEM_FIELDS;
    out.push(field);
  }
  return out;
}
```

然后改各块构建用 `deriveFields(obj, SPEC)` 替换原 `objectFields(obj, whitelist)`，并补全规格。下面列出每块的 spec（label 用 `label(key)` 习惯；type 省略=按推断）：

- `game_profile` 块：spec `[{key:"title",label:"标题",type:"text"},{key:"genre",label:"类型",type:"text"},{key:"tone",label:"基调",type:"text"},{key:"logline",label:"一句话",type:"textarea"},{key:"description",label:"简介",type:"textarea"}]`，address 不变。
- `worldview` 块：spec `[{key:"summary",label:"概述",type:"textarea"},{key:"public_facts",label:"公开事实",type:"stringList"},{key:"hidden_facts",label:"隐藏真相",type:"stringList"}]`。
- `story_core` 标量逐项块：**不变**（已逐项）。
- `core_characters` 项块：spec 含 name/role/identity/aliases/description/appearance/desire/fear/leverage/relationship_arc/**dramatic_function/public_limit/portrait_prompt/visibility**（label 见 FIELD_LABELS，缺的补）。
- `act_plan` 项块：spec `[{key:"title",...,type:"text"},{key:"objective",...,type:"textarea"},{key:"dramatic_question",...,type:"textarea"},{key:"must_hit_beats",label:"必经节点",type:"stringList"},{key:"allowed_reveals",label:"允许揭示",type:"stringList"},{key:"forbidden_reveals",label:"禁止揭示",type:"stringList"},{key:"completion_anchors",label:"完成锚点",type:"objectList",itemFields:ANCHOR_ITEM_FIELDS},{key:"transition_to_next_act",label:"转场条件",type:"keyValue"}]`。
- `main_quest_path` 项块：补 act_id/player_visible/completion_signal/optional。
- `core_mechanics` 项块：补 visibility。
- `action_style_rules` 项块：补 priority/enabled。
- `story_material_library` 项块：补 type/triggers/priority/always_on/visibility/public_info/gm_secret/enabled。
- `generation_parameters` 块：`deriveFields(gen, [])`（纯数据派生，全 number/text）。
- **新增 `home_base` 块**（放 world 分类末尾）：

```ts
  const home = asRecord(settings.home_base);
  const homeFields = deriveFields(home, []); // 自由对象 → 全数据派生
  if (homeFields.length || true) // 见 §空块：始终建块，空则靠折叠隐藏
    byId.world.push({
      id: "home_base", category: "world", title: "据点 home_base", icon: "🏠",
      summary: firstLine(str(home.name)),
      fields: homeFields,
      address: { kind: "settingsScalar", path: ["home_base"] }, deletable: false
    });
```

> 注：所有固定块（game_profile/worldview/story_core 标量/各红线桶/home_base/generation_parameters）**无条件建块**（即使空），空与否由 §Task 7 的折叠开关在渲染层决定，不再在 build 阶段 `if (fields.length)` 跳过。把现有 `if (...Fields.length) push` 改为无条件 push（数组项块仍按是否有项）。`label()` 缺的键补进 `FIELD_LABELS`（dramatic_function=戏剧功能、public_limit=公开限度、portrait_prompt=立绘提示、visibility=可见性、public_facts=公开事实、hidden_facts=隐藏真相、must_hit_beats=必经节点、allowed_reveals=允许揭示、forbidden_reveals=禁止揭示、transition_to_next_act=转场条件、act_id=所属幕、player_visible=玩家可见、optional=可选、always_on=常驻、gm_secret=GM秘密、public_info=公开信息、services=服务、name=名称）。

- [ ] **Step 4: 运行验证通过**

Run: `cd web && npm test`
Expected: 新增覆盖用例全过；原有用例仍过（block.id/address 未变）。

- [ ] **Step 5: Commit**

```bash
git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts
git commit -m "feat(web): 看板字段数据派生+全字段覆盖(home_base/worldview facts/锚点等)"
```

---

### Task 3: writeBlockFields 无损回写各类型（TDD）

**Files:** Modify `web/lib/generatorBoard.ts`、`web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试**

追加：

```ts
describe("writeBlockFields 各类型无损往返", () => {
  it("number/bool 写回", () => {
    const src = { generation_parameters: { target_min: 1200, x: "keep" } };
    const out = writeBlockFields(src, { kind: "settingsScalar", path: ["generation_parameters"] }, [
      { key: "target_min", label: "x", value: 1600, type: "number" }
    ]);
    expect(out).toEqual({ generation_parameters: { target_min: 1600, x: "keep" } });
  });
  it("objectList 写回 act 的 completion_anchors，其余字段不丢", () => {
    const src = { act_plan: [{ id: "act_1", title: "序", objective: "查案" }] };
    const anchors = [{ id: "act_1_a1", title: "入庄", required: true }];
    const out = writeBlockFields(
      src,
      { kind: "settingsItem", arrayKey: "act_plan", idKey: "id", idValue: "act_1" },
      [{ key: "completion_anchors", label: "锚点", value: anchors, type: "objectList", itemFields: [] }]
    );
    const act = (out as { act_plan: Record<string, unknown>[] }).act_plan[0];
    expect(act.completion_anchors).toEqual(anchors);
    expect(act.objective).toBe("查案"); // 未编辑字段保留
  });
  it("keyValue 写回 home_base 对象", () => {
    const src = { home_base: { name: "旧" } };
    const out = writeBlockFields(src, { kind: "settingsScalar", path: ["home_base"] }, [
      { key: "name", label: "名称", value: "镖局", type: "text" },
      { key: "services", label: "服务", value: ["休整"], type: "stringList" }
    ]);
    expect(out).toEqual({ home_base: { name: "镖局", services: ["休整"] } });
  });
});
```

- [ ] **Step 2: 运行验证**

Run: `cd web && npm test`
Expected: 多半已 PASS（`fieldsToRecord` 按 key 赋值，天然支持任意值）；若 number/bool 因旧 `string | string[]` 类型断言报错或被转字符串，进 Step 3 修。

- [ ] **Step 3: 确认实现**

检查 `web/lib/generatorBoard.ts` 的 `fieldsToRecord`：应为 `for (const f of fields) target[f.key] = f.value;`（直接赋原值，不做字符串转换）。若不是，改成直接赋值。`writeBlockFields` 的 settingsStringList 非 length-1 分支 `node[leaf] = fields[0].value` 保持（stringList 块单字段）。确认深拷贝（`cloneDeep`）在前，保证无损。

- [ ] **Step 4: 运行验证通过**

Run: `cd web && npm test`
Expected: 全过。

- [ ] **Step 5: Commit**

```bash
git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts
git commit -m "test(web): writeBlockFields 各类型无损往返覆盖"
```

---

### Task 4: createEmptyItem + appendItem（TDD）

**Files:** Modify `web/lib/generatorBoard.ts`、`web/lib/generatorBoard.test.ts`

- [ ] **Step 1: 写失败测试**

追加：

```ts
import { createEmptyItem, appendItem, ARRAY_SPECS } from "@/lib/generatorBoard";

describe("新增数组项", () => {
  it("ARRAY_SPECS 覆盖可新增的数组", () => {
    expect(Object.keys(ARRAY_SPECS)).toEqual(expect.arrayContaining([
      "core_characters", "act_plan", "main_quest_path",
      "core_mechanics", "action_style_rules", "story_material_library"
    ]));
  });
  it("createEmptyItem 产出带身份键的空项", () => {
    const item = createEmptyItem("core_characters");
    expect(item).toHaveProperty("name", "");
  });
  it("appendItem 追加到数组（不可变）", () => {
    const src = { core_characters: [{ name: "主角" }] };
    const out = appendItem(src, "core_characters", { name: "红伞客", role: "npc" });
    expect((out as { core_characters: unknown[] }).core_characters).toHaveLength(2);
    expect(out).not.toBe(src);
  });
});
```

- [ ] **Step 2: 运行验证失败** — Run: `cd web && npm test` — Expected: FAIL（未定义）。

- [ ] **Step 3: 实现**

在 `web/lib/generatorBoard.ts` 追加：

```ts
// 可手动新增的数组及其身份键/空项字段
export const ARRAY_SPECS: Record<string, { idKey: string; label: string; keys: string[] }> = {
  core_characters: { idKey: "name", label: "角色", keys: ["name", "role", "description"] },
  act_plan: { idKey: "id", label: "幕", keys: ["id", "title", "objective"] },
  main_quest_path: { idKey: "id", label: "主线节点", keys: ["id", "title", "objective"] },
  core_mechanics: { idKey: "name", label: "机制", keys: ["name", "rule"] },
  action_style_rules: { idKey: "name", label: "行动风格", keys: ["name", "rule"] },
  story_material_library: { idKey: "title", label: "素材", keys: ["title", "content"] }
};

export function createEmptyItem(arrayKey: string): Record<string, unknown> {
  const spec = ARRAY_SPECS[arrayKey];
  if (!spec) return {};
  return Object.fromEntries(spec.keys.map((k) => [k, ""]));
}

export function appendItem(
  source: Record<string, unknown>,
  arrayKey: string,
  item: Record<string, unknown>
): Record<string, unknown> {
  const out = cloneDeep(source);
  const arr = Array.isArray(out[arrayKey]) ? (out[arrayKey] as unknown[]) : [];
  out[arrayKey] = [...arr, item];
  return out;
}
```

- [ ] **Step 4: 运行验证通过** — Run: `cd web && npm test` — Expected: 全过。
- [ ] **Step 5: lint + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/lib/generatorBoard.ts web/lib/generatorBoard.test.ts && git commit -m "feat(web): createEmptyItem/appendItem + ARRAY_SPECS"`

---

## Phase B — 组件（tsc + lint + build 验证）

> 每个 Task 提交前：`cd web && npm run lint && npx tsc --noEmit`（0 error/0 warning，CI 跑 `eslint .`）；Phase 末 `npm run build`。复用既有 CSS 类。

### Task 5: BoardFieldEditor + BlockDetailModal 改类型化编辑

**Files:** Create `web/components/board/BoardFieldEditor.tsx`；Modify `web/components/board/BlockDetailModal.tsx`

- [ ] **Step 1: 写 BoardFieldEditor（按类型渲染）**

```tsx
"use client";

import { useState } from "react";

import type { BoardField, BoardFieldValue, SubFieldSpec } from "@/lib/generatorBoard";

function asStr(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

// objectList 里单个子对象的小型编辑器
function SubItemEditor({
  spec, item, onChange
}: {
  spec: SubFieldSpec[];
  item: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  function set(key: string, value: unknown) {
    onChange({ ...item, [key]: value });
  }
  return (
    <div className="grid gap-2">
      {spec.map((s) => (
        <label key={s.key} className="grid gap-1 text-xs">
          <span className="font-medium">{s.label}</span>
          {s.type === "bool" ? (
            <input type="checkbox" checked={Boolean(item[s.key])} onChange={(e) => set(s.key, e.target.checked)} />
          ) : s.type === "number" ? (
            <input className="app-input" type="number" value={asStr(item[s.key])}
              onChange={(e) => set(s.key, e.target.value === "" ? 0 : Number(e.target.value))} />
          ) : s.type === "stringList" ? (
            <textarea className="app-input min-h-16" value={(Array.isArray(item[s.key]) ? item[s.key] as string[] : []).join("\n")}
              onChange={(e) => set(s.key, e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} />
          ) : s.type === "textarea" ? (
            <textarea className="app-input min-h-16" value={asStr(item[s.key])} onChange={(e) => set(s.key, e.target.value)} />
          ) : (
            <input className="app-input" value={asStr(item[s.key])} onChange={(e) => set(s.key, e.target.value)} />
          )}
        </label>
      ))}
    </div>
  );
}

export function BoardFieldEditor({
  field, value, onChange
}: {
  field: BoardField;
  value: BoardFieldValue;
  onChange: (v: BoardFieldValue) => void;
}) {
  if (field.type === "text") {
    return <input className="app-input" value={asStr(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  if (field.type === "textarea") {
    return <textarea className="app-input min-h-24 resize-y leading-6" value={asStr(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  if (field.type === "number") {
    return <input className="app-input" type="number" value={asStr(value)}
      onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))} />;
  }
  if (field.type === "bool") {
    return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} /> 是</label>;
  }
  if (field.type === "stringList") {
    const list = Array.isArray(value) ? (value as string[]) : [];
    return (
      <div className="grid gap-1">
        {list.map((s, i) => (
          <div key={i} className="flex gap-2">
            <input className="app-input flex-1" value={s}
              onChange={(e) => { const n = [...list]; n[i] = e.target.value; onChange(n); }} />
            <button className="app-button" type="button" onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="app-button w-fit" type="button" onClick={() => onChange([...list, ""])}>＋ 加一条</button>
      </div>
    );
  }
  if (field.type === "objectList") {
    const items = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
    const spec = field.itemFields ?? [];
    return (
      <div className="grid gap-2">
        {items.map((it, i) => (
          <div key={i} className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-2">
            <SubItemEditor spec={spec} item={it}
              onChange={(next) => { const n = [...items]; n[i] = next; onChange(n); }} />
            <button className="app-button mt-2" type="button" onClick={() => onChange(items.filter((_, j) => j !== i))}>删除此项</button>
          </div>
        ))}
        <button className="app-button w-fit" type="button"
          onClick={() => onChange([...items, Object.fromEntries(spec.map((s) => [s.key, s.type === "bool" ? false : s.type === "stringList" ? [] : s.type === "number" ? 0 : ""]))])}>
          ＋ 新增一项
        </button>
      </div>
    );
  }
  if (field.type === "keyValue") {
    const obj = (value && typeof value === "object" && !Array.isArray(value)) ? (value as Record<string, unknown>) : {};
    const entries = Object.entries(obj);
    return (
      <div className="grid gap-1">
        {entries.map(([k, v], i) => (
          <div key={i} className="flex gap-2">
            <input className="app-input w-1/3" value={k}
              onChange={(e) => { const next: Record<string, unknown> = {}; entries.forEach(([kk, vv], j) => { next[j === i ? e.target.value : kk] = vv; }); onChange(next); }} />
            <input className="app-input flex-1" value={asStr(v)}
              onChange={(e) => onChange({ ...obj, [k]: e.target.value })} />
            <button className="app-button" type="button" onClick={() => { const next = { ...obj }; delete next[k]; onChange(next); }}>✕</button>
          </div>
        ))}
        <button className="app-button w-fit" type="button" onClick={() => onChange({ ...obj, "": "" })}>＋ 加一项</button>
      </div>
    );
  }
  // json 兜底
  return <JsonEditor value={value} onChange={onChange} />;
}

function JsonEditor({ value, onChange }: { value: BoardFieldValue; onChange: (v: BoardFieldValue) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="grid gap-1">
      <textarea className="app-input min-h-24 font-mono text-xs" value={text}
        onChange={(e) => {
          setText(e.target.value);
          try { onChange(JSON.parse(e.target.value) as BoardFieldValue); setError(null); }
          catch { setError("JSON 格式有误，暂未保存该字段"); }
        }} />
      {error ? <span className="text-xs text-[color:var(--danger-text)]">{error}</span> : null}
    </div>
  );
}
```

- [ ] **Step 2: 改 BlockDetailModal 用类型化 drafts + BoardFieldEditor**

替换 `web/components/board/BlockDetailModal.tsx` 的 `fieldToText`/`textToFieldValue`/`drafts`/字段渲染段：

```tsx
"use client";

import { useState } from "react";

import { BoardFieldEditor } from "@/components/board/BoardFieldEditor";
import type { BoardBlock, BoardField, BoardFieldValue } from "@/lib/generatorBoard";

export function BlockDetailModal({
  block, locked, onSave, onDelete, onUnlock, onSaveAsModule, onClose
}: {
  block: BoardBlock;
  locked: boolean;
  onSave: (fields: BoardField[]) => void;
  onDelete: () => void;
  onUnlock?: () => void;
  onSaveAsModule?: () => void;
  onClose: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, BoardFieldValue>>(() =>
    Object.fromEntries(block.fields.map((f) => [f.key, f.value]))
  );

  function handleSave() {
    onSave(block.fields.map((f) => ({ ...f, value: drafts[f.key] ?? f.value })));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="surface-panel surface-panel-strong max-h-[85vh] w-full max-w-2xl overflow-auto" onClick={(e) => e.stopPropagation()}>
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
              <span className="text-sm font-semibold">{f.label}</span>
              <BoardFieldEditor field={f} value={drafts[f.key] ?? f.value}
                onChange={(v) => setDrafts((d) => ({ ...d, [f.key]: v }))} />
            </label>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <button className="app-button app-button-primary" type="button" onClick={handleSave}>保存</button>
          {locked && onUnlock ? (
            <button className="app-button" type="button" onClick={onUnlock} title="恢复 AI 最近一次生成的值并解除锁定">🔓 解锁 / 恢复 AI 原值</button>
          ) : null}
          {block.deletable ? <button className="app-button" type="button" onClick={onDelete}>🗑 删除</button> : null}
          {onSaveAsModule ? <button className="app-button" type="button" onClick={onSaveAsModule} title="把这个设定存为可复用模块">⚗ 存为模块</button> : null}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: lint + tsc + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/components/board/BoardFieldEditor.tsx web/components/board/BlockDetailModal.tsx && git commit -m "feat(web): BoardFieldEditor 多类型编辑器 + Modal 类型化 drafts"`

---

### Task 6: BoardBlockGrid 空块折叠 + 「＋新增」入口

**Files:** Modify `web/components/board/BoardBlockGrid.tsx`

- [ ] **Step 1: 加 isEmptyBlock 工具到 generatorBoard.ts**

在 `web/lib/generatorBoard.ts` 追加并导出：

```ts
// 固定块"空"判定：全字段为空字符串/空数组/空对象（数值/布尔不算空，视为已设置）
export function isEmptyBlock(block: BoardBlock): boolean {
  if (block.deletable) return false; // 数组项不算"固定空块"
  return block.fields.every((f) => {
    const v = f.value;
    if (typeof v === "string") return v.trim() === "";
    if (Array.isArray(v)) return v.length === 0;
    if (v && typeof v === "object") return Object.keys(v).length === 0;
    if (typeof v === "number") return false;
    if (typeof v === "boolean") return false;
    return v == null;
  });
}
```

- [ ] **Step 2: 改 BoardBlockGrid（空块过滤 + 新增入口）**

`web/components/board/BoardBlockGrid.tsx` props 增加 `showEmpty: boolean` 与 `onAdd?: (arrayKey: string) => void`，并在该分类有可新增数组时渲染入口。完整改写：

```tsx
"use client";

import { ARRAY_SPECS, isEmptyBlock, type BoardBlock, type BoardCategoryId } from "@/lib/generatorBoard";

// 各分类可新增的数组键
const CATEGORY_ARRAYS: Partial<Record<BoardCategoryId, string[]>> = {
  characters: ["core_characters"],
  plot: ["act_plan", "main_quest_path"],
  mechanics: ["core_mechanics", "action_style_rules"],
  materials: ["story_material_library"]
};

export function BoardBlockGrid({
  category, blocks, changedBlockIds, lockedIds, loading, showEmpty, onOpen, onAdd
}: {
  category: BoardCategoryId;
  blocks: BoardBlock[];
  changedBlockIds: Set<string>;
  lockedIds: string[];
  loading: boolean;
  showEmpty: boolean;
  onOpen: (block: BoardBlock) => void;
  onAdd?: (arrayKey: string) => void;
}) {
  const visible = showEmpty ? blocks : blocks.filter((b) => !isEmptyBlock(b));
  const addArrays = onAdd ? (CATEGORY_ARRAYS[category] ?? []) : [];

  if (loading && visible.length === 0 && addArrays.length === 0) {
    return (
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => <div key={i} className="archive-card h-20 animate-pulse opacity-60" />)}
      </div>
    );
  }

  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {visible.map((block) => {
        const changed = changedBlockIds.has(block.id);
        const locked = lockedIds.includes(block.id);
        const empty = isEmptyBlock(block);
        return (
          <button key={block.id} type="button" onClick={() => onOpen(block)}
            className={["archive-card text-left transition", changed ? "ring-2 ring-[#4a9a6f] animate-[pulse_1s_ease-in-out_3]" : "", empty ? "opacity-50" : ""].join(" ")}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{block.icon} {block.title}</span>
              <span className="flex gap-1">
                {locked ? <span className="app-pill">✏ 已改</span> : null}
                {changed ? <span className="app-pill">刚更新</span> : null}
              </span>
            </div>
            <p className="mt-1 text-xs text-[color:var(--muted)]">{empty ? "未设置 · 点击填写" : block.summary}</p>
          </button>
        );
      })}
      {addArrays.map((arrayKey) => (
        <button key={`add-${arrayKey}`} type="button" onClick={() => onAdd?.(arrayKey)}
          className="archive-card border-dashed text-left text-[color:var(--accent-strong)]">
          ＋ 新增{ARRAY_SPECS[arrayKey]?.label ?? "项"}
        </button>
      ))}
      {visible.length === 0 && addArrays.length === 0 ? (
        <p className="surface-subtle">这一类暂无设定。{!showEmpty ? "（打开「显示空设定项」可填写空项）" : ""}</p>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 3: lint + tsc + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/lib/generatorBoard.ts web/components/board/BoardBlockGrid.tsx && git commit -m "feat(web): 空块折叠 + 分类内「＋新增」入口 + isEmptyBlock"`

---

### Task 7: SettingsBoard 显示空项开关 + 新增表单 + newItemBlock

**Files:** Modify `web/lib/generatorBoard.ts`、`web/components/board/SettingsBoard.tsx`

- [ ] **Step 1: generatorBoard 加 newItemBlock + label 暴露**

在 `web/lib/generatorBoard.ts` 追加并导出（用于「新增」时构造空白块给 Modal 编辑）：

```ts
const CATEGORY_OF_ARRAY: Record<string, BoardCategoryId> = {
  core_characters: "characters", act_plan: "plot", main_quest_path: "plot",
  core_mechanics: "mechanics", action_style_rules: "mechanics", story_material_library: "materials"
};

// 「新增数组项」时的空白合成块（Modal 据此渲染表单；保存后由调用方 appendItem）
export function newItemBlock(arrayKey: string): BoardBlock {
  const spec = ARRAY_SPECS[arrayKey];
  const item = createEmptyItem(arrayKey);
  return {
    id: `__new__:${arrayKey}`,
    category: CATEGORY_OF_ARRAY[arrayKey] ?? "world",
    title: `新增${spec?.label ?? "项"}`,
    icon: "＋",
    summary: "",
    fields: (spec?.keys ?? []).map((k) => ({
      key: k, label: label(k),
      value: (item[k] as BoardFieldValue) ?? "",
      type: TEXTAREA_KEYS.has(k) ? "textarea" : "text"
    })),
    address: { kind: "settingsItem", arrayKey, idKey: spec?.idKey ?? "id", idValue: "" },
    deletable: false
  };
}
```

- [ ] **Step 2: 改 SettingsBoard（开关 + 新增）**

`web/components/board/SettingsBoard.tsx`：加 `showEmpty` 状态与开关、`onAddItem` prop、新增态。关键改动：

```tsx
import { newItemBlock, ARRAY_SPECS, type BoardField } from "@/lib/generatorBoard";
// ... props 增加：
//   onAddItem?: (arrayKey: string, item: Record<string, unknown>) => void;

const [showEmpty, setShowEmpty] = useState(false);
const [addingArray, setAddingArray] = useState<string | null>(null);

// 在 BoardTabs 之后、BoardBlockGrid 之前加开关：
//   <label className="mt-3 flex items-center gap-2 text-xs text-[color:var(--muted)]">
//     <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} /> 显示空设定项
//   </label>

// BoardBlockGrid 传入 category={activeTab} showEmpty={showEmpty}
//   onAdd={onAddItem ? (arrayKey) => setAddingArray(arrayKey) : undefined}

// 新增表单：复用 BlockDetailModal 编辑空白合成块；保存时把 fields → item 后 onAddItem
{addingArray ? (
  <BlockDetailModal
    block={newItemBlock(addingArray)}
    locked={false}
    onSave={(fields: BoardField[]) => {
      const spec = ARRAY_SPECS[addingArray];
      const item = Object.fromEntries(fields.map((f) => [f.key, f.value]));
      const idKey = spec?.idKey ?? "id";
      if (!String(item[idKey] ?? "").trim()) { return; } // 身份必填（Modal 内可加提示，最简先静默拦截）
      onAddItem?.(addingArray, item);
      setAddingArray(null);
    }}
    onDelete={() => setAddingArray(null)}
    onClose={() => setAddingArray(null)}
  />
) : null}
```

> 注：`newItemBlock` 的 `deletable:false` 隐藏删除按钮；不传 onUnlock/onSaveAsModule。身份必填用最简静默拦截即可（重名/合法性由后端 validate 兜底报错）。

- [ ] **Step 3: lint + build + commit** — `cd web && npm run lint && npx tsc --noEmit && npm run build` 后 `git add web/lib/generatorBoard.ts web/components/board/SettingsBoard.tsx && git commit -m "feat(web): 设定看板显示空项开关 + 手动新增数组项(newItemBlock)"`

---

### Task 8: 设定页接 onAddItem

**Files:** Modify `web/app/games/[id]/settings/page.tsx`

- [ ] **Step 1: 接线**

在 `SettingsView` 给 `<SettingsBoard>` 增加 `onAddItem`（复用 appendItem + persist）。import 加 `appendItem`：

```tsx
import { appendItem, /* 其余已有 */ } from "@/lib/generatorBoard";
// ...
      <SettingsBoard
        model={model}
        loading={saving}
        onEditBlock={handleEditBlock}
        onDeleteBlock={handleDeleteBlock}
        onSaveAsModule={(block) => { if (isExtractable(block)) setModuleBlock(block); }}
        onAddItem={(arrayKey, item) => { void persist(appendItem(settings, arrayKey, item)); }}
      />
```

- [ ] **Step 2: lint + build + commit** — `cd web && npm run lint && npx tsc --noEmit && npm run build` 后 `git add web/app/games/\[id\]/settings/page.tsx && git commit -m "feat(web): 设定页接入手动新增数组项"`

---

## Phase C — 验证、部署、文档

### Task 9: 全量验证 + 重建 + 文档

**Files:** Modify `docs/OPTIMIZATION_PLAN.md`

- [ ] **Step 1: 全量验证** — Run: `cd web && npm run lint && npm test && npx tsc --noEmit && npm run build` — Expected: lint 0/0、vitest 全过、tsc 干净、build 通过。
- [ ] **Step 2: 重建 web（Docker 不挂源码）** — Run: `docker compose up -d --build web`，再 `docker images | grep rpgforge-web` 核实构建时间是刚刚。
- [ ] **Step 3: 手动走查（待用户）**：① 设定页各分类块覆盖全字段（角色含戏剧功能/立绘、act 有完成锚点子卡、worldview 有公开/隐藏事实、有 home_base）；② 编辑各类型（number/bool/objectList/keyValue）保存无损、其余字段不丢；③「显示空设定项」开关显隐空块、点空块可填；④「＋新增角色/机制/幕/素材」创建成功、重名被后端拦、版本历史多快照可回滚；⑤ 生成页看板展示/编辑增强正常（不回归）。
- [ ] **Step 4: OPTIMIZATION_PLAN 追加 Round**：§0/§1 加 `### Round N (2026-06-04)`：看板完整设定编辑面——字段数据派生全覆盖 + 字段类型系统(number/bool/objectList/keyValue/json) + 空块折叠开关 + 手动新增数组项；纯前端、后端零改动。不改历史 Round。然后 commit。
- [ ] **Step 5: Commit** — `git add docs/OPTIMIZATION_PLAN.md && git commit -m "docs: OPTIMIZATION_PLAN 追加看板完整编辑面 Round 条目"`

---

## 自审（Self-Review）

**Spec 覆盖：**
- §3 字段类型系统 → Task 1（类型）+ Task 5（BoardFieldEditor 各类型）✓
- §4 数据驱动全覆盖（home_base/worldview facts/锚点/全 item 字段）→ Task 2（deriveFields + 补全 + 无条件建固定块）✓
- §5 无损回写 → Task 3（往返测试，fieldsToRecord 直接赋值）✓
- §6 空块折叠 + 手动新增 → Task 6（isEmptyBlock + 过滤 + 入口）+ Task 7（开关 + newItemBlock + 表单）+ Task 8（onAddItem→appendItem→persist）✓
- §7 组件/接口 → Task 5-8 对应 ✓
- §8 风险（id/address 兼容、无损、身份校验）→ Task 2 保持 id/address、Task 3 无损、Task 7 身份必填 ✓
- §9 测试 → Task 2/3/4 vitest + Task 9 lint/build/走查 ✓
- §10 P1 设定页全做、生成页新增留 P2 → Task 8 仅设定页接 onAddItem；展示/编辑增强两边共享 ✓

**Placeholder 扫描：** 无 TBD/TODO；新组件给完整代码；块构建改写以"逐块 spec 清单 + deriveFields 替换"精确描述（Task 2 列了每块 spec），非占位。

**类型一致性：**
- `BoardFieldType`/`BoardFieldValue`/`SubFieldSpec`/`BoardField.itemFields` 在 Task 1 定义，Task 2(deriveFields)/Task 5(BoardFieldEditor)/Task 7(newItemBlock) 一致引用。
- `deriveFields(data, spec)`、`inferType`、`defaultValueFor`、`ANCHOR_ITEM_FIELDS`、`TEXTAREA_KEYS`/`BOOL_KEYS` Task 2 定义、Task 7 复用 TEXTAREA_KEYS。
- `ARRAY_SPECS`/`createEmptyItem`/`appendItem` Task 4 定义；`newItemBlock` Task 7、`CATEGORY_ARRAYS`/`isEmptyBlock` Task 6、`onAddItem` Task 7/8 一致。
- `BoardFieldEditor(field,value,onChange)`、`BlockDetailModal` 类型化 drafts、`BoardBlockGrid(category,showEmpty,onAdd)` 签名跨任务一致。
- block.id/address 规则未变（保护生成页 diff 与 `buildModulePayload` 提取）。
