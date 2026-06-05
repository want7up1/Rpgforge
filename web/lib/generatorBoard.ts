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
  content: "内容", usage: "用法", keywords: "关键词", triggers: "触发词",
  dramatic_function: "戏剧功能", public_limit: "公开限度", portrait_prompt: "立绘提示",
  visibility: "可见性", public_facts: "公开事实", hidden_facts: "隐藏真相",
  must_hit_beats: "必经节点", allowed_reveals: "允许揭示", forbidden_reveals: "禁止揭示",
  transition_to_next_act: "转场条件", act_id: "所属幕", player_visible: "玩家可见",
  optional: "可选", always_on: "常驻", gm_secret: "GM秘密", public_info: "公开信息",
  services: "服务", type: "类型", priority: "优先级", enabled: "启用",
  completion_signal: "完成信号", completion_anchors: "完成锚点"
};
function label(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

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

type FieldSpec = { key: string; label?: string; type?: BoardFieldType; itemFields?: SubFieldSpec[] };

// 按「已知字段规格 + 数据里出现的额外键」派生 BoardField[]：
// spec 决定 label/type/顺序与空块占位；data 里多出的键按推断补上（防漏不漂移）。
function deriveFields(data: Record<string, unknown>, spec: FieldSpec[]): BoardField[] {
  const out: BoardField[] = [];
  const used = new Set<string>();
  for (const s of spec) {
    used.add(s.key);
    const type = s.type ?? inferType(s.key, data[s.key]);
    const raw = data[s.key];
    const value = raw === undefined || raw === null ? defaultValueFor(type) : (raw as BoardFieldValue);
    const field: BoardField = { key: s.key, label: s.label ?? label(s.key), value, type };
    if (type === "objectList") field.itemFields = s.itemFields ?? ANCHOR_ITEM_FIELDS;
    out.push(field);
  }
  for (const [k, v] of Object.entries(data)) {
    if (used.has(k) || k === "id") continue;
    const type = inferType(k, v);
    const field: BoardField = {
      key: k, label: label(k),
      value: (v as BoardFieldValue) ?? defaultValueFor(type), type
    };
    if (type === "objectList") field.itemFields = ANCHOR_ITEM_FIELDS;
    out.push(field);
  }
  return out;
}

// 各可新增数组项的「完整字段规格」——新增表单与编辑面共用同一份，避免两套定义漂移。
// 注意：不含 id（id 是被引用的稳定键，编辑隐藏、新增自动生成 → 见 generateItemId）。
const ITEM_FIELD_SPECS: Record<string, FieldSpec[]> = {
  core_characters: [
    { key: "name", type: "text" }, { key: "role", type: "text" },
    { key: "identity", type: "text" }, { key: "aliases", type: "stringList" },
    { key: "description", type: "textarea" }, { key: "appearance", type: "textarea" },
    { key: "desire", type: "text" }, { key: "fear", type: "text" },
    { key: "leverage", type: "text" }, { key: "relationship_arc", type: "textarea" },
    { key: "dramatic_function", type: "textarea" }, { key: "public_limit", type: "text" },
    { key: "portrait_prompt", type: "textarea" }, { key: "visibility", type: "text" }
  ],
  act_plan: [
    { key: "title", type: "text" }, { key: "objective", type: "textarea" },
    { key: "dramatic_question", type: "textarea" },
    { key: "must_hit_beats", type: "stringList" },
    { key: "allowed_reveals", type: "stringList" },
    { key: "forbidden_reveals", type: "stringList" },
    { key: "completion_anchors", type: "objectList", itemFields: ANCHOR_ITEM_FIELDS },
    { key: "transition_to_next_act", type: "keyValue" }
  ],
  main_quest_path: [
    { key: "title", type: "text" }, { key: "objective", type: "textarea" },
    { key: "act_id", type: "text" }, { key: "player_visible", type: "text" },
    { key: "completion_signal", type: "text" }, { key: "optional", type: "bool" }
  ],
  core_mechanics: [
    { key: "name", type: "text" }, { key: "rule", type: "textarea" },
    { key: "visibility", type: "text" }
  ],
  action_style_rules: [
    { key: "name", type: "text" }, { key: "triggers", type: "stringList" },
    { key: "rule", type: "textarea" }, { key: "priority", type: "text" },
    { key: "enabled", type: "bool" }
  ],
  story_material_library: [
    { key: "title", type: "text" }, { key: "type", type: "text" },
    { key: "keywords", type: "stringList" }, { key: "triggers", type: "stringList" },
    { key: "priority", type: "text" }, { key: "always_on", type: "bool" },
    { key: "visibility", type: "text" }, { key: "public_info", type: "textarea" },
    { key: "gm_secret", type: "textarea" }, { key: "content", type: "textarea" },
    { key: "usage", type: "textarea" }, { key: "enabled", type: "bool" }
  ]
};

function buildFromSettings(settings: Record<string, unknown>): BoardCategory[] {
  const profile = asRecord(settings.game_profile);
  const worldview = asRecord(settings.worldview);
  const core = asRecord(settings.story_core);
  const hard = asRecord(settings.hard_rules);

  const byId: Record<BoardCategoryId, BoardBlock[]> = {
    world: [], characters: [], plot: [], mechanics: [],
    constraints: [], materials: [], advanced: []
  };

  const home = asRecord(settings.home_base);
  const gen = asRecord(settings.generation_parameters);

  // ① 世界与基调（固定块无条件建，空与否由渲染层折叠决定）
  byId.world.push({
    id: "game_profile", category: "world", title: "作品信息", icon: "🪪",
    summary: firstLine(str(profile.title)),
    fields: deriveFields(profile, [
      { key: "title", type: "text" }, { key: "genre", type: "text" },
      { key: "tone", type: "text" }, { key: "logline", type: "textarea" },
      { key: "description", type: "textarea" }
    ]),
    address: { kind: "settingsScalar", path: ["game_profile"] }, deletable: false
  });
  byId.world.push({
    id: "worldview", category: "world", title: "世界观", icon: "🌍",
    summary: firstLine(str(worldview.summary)),
    fields: deriveFields(worldview, [
      { key: "summary", type: "textarea" },
      { key: "public_facts", type: "stringList" },
      { key: "hidden_facts", type: "stringList" }
    ]),
    address: { kind: "settingsScalar", path: ["worldview"] }, deletable: false
  });
  for (const k of ["premise", "core_fantasy", "central_mystery", "main_goal", "emotional_arc", "narrative_style"]) {
    byId.world.push({
      id: `story_core.${k}`, category: "world", title: label(k), icon: "🎯",
      summary: firstLine(str(core[k])),
      fields: [{ key: k, label: label(k), value: str(core[k]), type: "textarea" }],
      address: { kind: "settingsScalar", path: ["story_core", k] }, deletable: false
    });
  }
  byId.world.push({
    id: "home_base", category: "world", title: "据点 home_base", icon: "🏠",
    summary: firstLine(str(home.name)),
    fields: deriveFields(home, []),
    address: { kind: "settingsScalar", path: ["home_base"] }, deletable: false
  });

  // ② 角色
  for (const ch of asList(settings.core_characters)) {
    const name = str(ch.name);
    if (!name) continue;
    byId.characters.push({
      id: `core_characters:${name}`, category: "characters", title: name, icon: "👤",
      summary: [str(ch.role), firstLine(str(ch.description))].filter(Boolean).join(" · "),
      fields: deriveFields(ch, ITEM_FIELD_SPECS.core_characters),
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
      fields: deriveFields(act, ITEM_FIELD_SPECS.act_plan),
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
      fields: deriveFields(q, ITEM_FIELD_SPECS.main_quest_path),
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
      fields: deriveFields(m, ITEM_FIELD_SPECS.core_mechanics),
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
      fields: deriveFields(s, ITEM_FIELD_SPECS.action_style_rules),
      address: { kind: "settingsItem", arrayKey: "action_style_rules", idKey: "name", idValue: name },
      deletable: true
    });
  }

  // ⑤ 约束与红线（hard_rules 各桶 + story_core 红线，无条件建块）
  const constraintBuckets: { key: string; title: string }[] = [
    { key: "must_follow", title: "必须遵守" },
    { key: "must_not", title: "禁止行为" },
    { key: "reveal_rules", title: "揭示规则" },
    { key: "continuity_rules", title: "连续性规则" }
  ];
  for (const { key, title } of constraintBuckets) {
    const v = strList(hard[key]);
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
      fields: deriveFields(mat, ITEM_FIELD_SPECS.story_material_library),
      address: {
        kind: "settingsItem", arrayKey: "story_material_library",
        idKey: str(mat.id) ? "id" : "title", idValue: str(mat.id) || title
      },
      deletable: true
    });
  }

  // ⑦ 高级：篇幅参数（无条件建块，数据派生）
  byId.advanced.push({
    id: "generation_parameters", category: "advanced", title: "篇幅参数", icon: "🔧",
    summary: `${Object.keys(gen).length} 项`,
    fields: deriveFields(gen, []),
    address: { kind: "settingsScalar", path: ["generation_parameters"] }, deletable: false
  });

  // 保证每个分类内 block.id 唯一：同名机制/行动风格/素材等会撞 id → React key 重复
  // → DOM 复用错位、内容串台（尤其「玩法机制」= core_mechanics ∪ action_style_rules，
  // 名字无唯一性校验，最易撞）。撞了就追加 #2/#3，唯一 id 保持不变（不影响 diff）。
  for (const blocks of Object.values(byId)) {
    const seen = new Set<string>();
    for (const block of blocks) {
      let uniqueId = block.id;
      let counter = 2;
      while (seen.has(uniqueId)) {
        uniqueId = `${block.id}#${counter}`;
        counter += 1;
      }
      seen.add(uniqueId);
      block.id = uniqueId;
    }
  }

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

// 「无改动」基线：设定页等不需要改动闪烁的消费方可直接传入。
export const EMPTY_DIFF: BoardDiff = {
  changedCategories: Object.fromEntries(
    BOARD_CATEGORIES.map((c) => [c.id, 0])
  ) as Record<BoardCategoryId, number>,
  changedBlockIds: new Set<string>()
};

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

// ====== 手动新增数组项 ======

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

const CATEGORY_OF_ARRAY: Record<string, BoardCategoryId> = {
  core_characters: "characters", act_plan: "plot", main_quest_path: "plot",
  core_mechanics: "mechanics", action_style_rules: "mechanics", story_material_library: "materials"
};

// 「新增数组项」时的空白合成块（Modal 据此渲染表单；保存后由调用方 appendItem）。
// 字段来自与编辑面共用的 ITEM_FIELD_SPECS（完整、不含 id）；id 由 generateItemId 自动生成。
export function newItemBlock(arrayKey: string): BoardBlock {
  const spec = ARRAY_SPECS[arrayKey];
  return {
    id: `__new__:${arrayKey}`,
    category: CATEGORY_OF_ARRAY[arrayKey] ?? "world",
    title: `新增${spec?.label ?? "项"}`,
    icon: "＋",
    summary: "",
    fields: deriveFields({}, ITEM_FIELD_SPECS[arrayKey] ?? []),
    address: { kind: "settingsItem", arrayKey, idKey: spec?.idKey ?? "id", idValue: "" },
    deletable: false
  };
}

// 为 idKey="id" 的数组（act_plan/main_quest_path）生成不与现有冲突的唯一 id。
export function generateItemId(arrayKey: string, existingIds: string[]): string {
  const prefix = arrayKey === "act_plan" ? "act" : arrayKey === "main_quest_path" ? "quest" : "item";
  const set = new Set(existingIds);
  let n = 1;
  while (set.has(`${prefix}_${n}`)) n += 1;
  return `${prefix}_${n}`;
}

// 从 BoardModel 提取某数组所有现有项的 idValue（供 generateItemId 去重）。
export function itemIdsOf(model: BoardModel, arrayKey: string): string[] {
  const ids: string[] = [];
  for (const cat of model.categories) {
    for (const b of cat.blocks) {
      if (b.address.kind === "settingsItem" && b.address.arrayKey === arrayKey) {
        ids.push(b.address.idValue);
      }
    }
  }
  return ids;
}

// 固定块"空"判定：全字段为空字符串/空数组/空对象（数值/布尔不算空）
export function isEmptyBlock(block: BoardBlock): boolean {
  if (block.deletable) return false;
  return block.fields.every((f) => {
    const v = f.value;
    if (typeof v === "string") return v.trim() === "";
    if (Array.isArray(v)) return v.length === 0;
    if (v && typeof v === "object") return Object.keys(v).length === 0;
    return v == null;
  });
}
