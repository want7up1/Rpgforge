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
      address: {
        kind: "settingsItem", arrayKey: "act_plan",
        idKey: str(act.id) ? "id" : "title", idValue: str(act.id) || str(act.title)
      },
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
      address: {
        kind: "settingsItem", arrayKey: "main_quest_path",
        idKey: str(q.id) ? "id" : "title", idValue: str(q.id) || str(q.title)
      },
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

export type BoardDiff = {
  changedCategories: Record<BoardCategoryId, number>;
  changedBlockIds: Set<string>;
};

// block 内容指纹：用 fields 的 [key, value] 对序列化，变化即视为改动。
// 使用 JSON.stringify 消除 ¦/| 分隔符碰撞风险。
function blockFingerprint(block: BoardBlock): string {
  return JSON.stringify(block.fields.map((f) => [f.key, f.value]));
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

// 注意：重命名 idKey 字段后，原 BoardBlock.address.idValue 会过期；
// 调用方需在编辑后用新 source 重建 BoardModel 再操作，否则定位会失效。
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
      // 注意：排除数组，避免数组被错误当对象合并而损坏数据
      const obj = (typeof node[leaf] === "object" && node[leaf] !== null && !Array.isArray(node[leaf])
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
