import type { GameDetail } from "@/lib/types";

export type ProgressionState = {
  level: number;
  xp: number;
  next_level_xp: number;
  total_xp: number;
  xp_log: Record<string, unknown>[];
};

export type ProtagonistSheet = {
  name: string;
  identity: string;
  level: number;
  xp: number;
  next_level_xp: number;
  total_xp: number;
  attributes: Record<string, unknown>;
};

export type SkillState = {
  name: string;
  level: number;
  xp: number;
  next_level_xp: number;
  mastery: number;
  visibility: string;
  recent_events: Record<string, unknown>[];
};

export type AbilityState = {
  name: string;
  level: number;
  visibility: string;
  description: string;
  status: string;
  resource_cost: string;
  cooldown: string;
  usage_note: string;
};

export type ConditionState = {
  name: string;
  status: string;
  severity: string;
  duration: string;
  source: string;
  visibility: string;
};

export type ActiveSceneState = {
  turn: number;
  time: string;
  location: string;
  pressure: string;
  present_npcs: string[];
};

export type NpcRegistryItem = {
  id: string;
  name: string;
  identity: string;
  status: string;
  location: string;
  relationship: string;
  attitude: string;
};

export type QuestItem = {
  name: string;
  status: string;
  objective: string;
};

export type QuestLog = {
  active: QuestItem[];
  completed: QuestItem[];
  failed: QuestItem[];
  hidden: QuestItem[];
};

export type ThreadItem = {
  title: string;
  status: string;
  source: string;
};

export type ThreadLog = {
  active: ThreadItem[];
  resolved: ThreadItem[];
};

export type StoryProgressState = {
  current_act: string;
  completed_acts: string[];
  completed_anchors: string[];
  ready_for_next_act: boolean;
  last_advance_turn: number | null;
  last_advance_reason: string;
  last_anchor_update_turn: number | null;
  next_act: string;
  current_act_anchor_progress: { done: number; total: number };
  current_act_title: string;
  current_act_objective: string;
  campaign_complete: boolean;
  epilogue: string;
  act_history: {
    turn: number | null;
    from_act: string;
    to_act: string;
    reason: string;
  }[];
  anchor_history: {
    turn: number | null;
    act: string;
    anchor_id: string;
    reason: string;
  }[];
};

export type RelationshipAxis =
  | "trust"
  | "affection"
  | "respect"
  | "fear"
  | "loyalty"
  | "conflict";

export type RelationshipTrack = {
  npc: string;
  stage: string;
  visibility: string;
  trust: number | null;
  affection: number | null;
  respect: number | null;
  fear: number | null;
  loyalty: number | null;
  conflict: number | null;
  relationship: string;
  attitude: string;
  recent_interaction: string;
  recent_events: Record<string, unknown>[];
};

export type CrisisState = {
  value: number;
  max: number;
};

export type PressureClockState = {
  value: number;
  threshold: number;
  triggers: number;
};

export type StateV2 = {
  version: number;
  active_scene: ActiveSceneState;
  protagonist_sheet: ProtagonistSheet;
  progression: ProgressionState;
  skills: SkillState[];
  abilities: AbilityState[];
  conditions: ConditionState[];
  party: string[];
  npc_registry: NpcRegistryItem[];
  quest_log: QuestLog;
  open_threads: ThreadLog;
  story_progress: StoryProgressState;
  relationship_tracks: RelationshipTrack[];
  crisis: CrisisState;
  pressure_clock: PressureClockState;
};

export const relationshipAxes: { key: RelationshipAxis; label: string }[] = [
  { key: "trust", label: "信任" },
  { key: "affection", label: "亲密" },
  { key: "respect", label: "尊重" },
  { key: "fear", label: "畏惧" },
  { key: "loyalty", label: "忠诚" },
  { key: "conflict", label: "冲突" }
];

export function getStateV2FromGame(game: GameDetail): StateV2 {
  return getStateV2(game.state?.state_json);
}

export function getStateV2(stateJson: Record<string, unknown> | null | undefined): StateV2 {
  const root = asRecord(stateJson);
  const rawV2 = asRecord(root.v2);
  const progression = normalizeProgression(rawV2.progression, root.progression);
  const protagonist = normalizeProtagonist(rawV2.protagonist_sheet, root.protagonist, progression);

  return {
    version: asNumber(rawV2.version, 1),
    active_scene: normalizeActiveScene(rawV2.active_scene, root),
    protagonist_sheet: protagonist,
    progression,
    skills: normalizeSkills(rawV2.skills ?? root.skills),
    abilities: normalizeAbilities(rawV2.abilities ?? root.abilities),
    conditions: normalizeConditions(rawV2.conditions ?? root.conditions),
    party: asStringList(rawV2.party ?? root.party),
    npc_registry: normalizeNpcRegistry(rawV2.npc_registry ?? root.npcs),
    quest_log: normalizeQuestLog(rawV2.quest_log, root.quests),
    open_threads: normalizeThreadLog(rawV2.open_threads, root.open_threads),
    story_progress: normalizeStoryProgress(
      firstRecord([rawV2.story_progress, root.story_progress])
    ),
    relationship_tracks: normalizeRelationships(rawV2.relationship_tracks ?? root.relationships),
    crisis: normalizeCrisis(rawV2.crisis ?? root.crisis),
    pressure_clock: normalizePressureClock(rawV2.pressure_clock ?? root.pressure_clock)
  };
}

function normalizeCrisis(value: unknown): CrisisState {
  const data = asRecord(value);
  const max = positiveNumber(data.max, 100);
  const raw = optionalNumber(data.value);
  const current = raw === null ? max : raw;
  return { value: clamp(current, 0, max), max };
}

function normalizePressureClock(value: unknown): PressureClockState {
  const data = asRecord(value);
  const threshold = positiveNumber(data.threshold, 10);
  return {
    value: clamp(optionalNumber(data.value) ?? 0, 0, threshold),
    threshold,
    triggers: Math.max(0, optionalNumber(data.triggers) ?? 0)
  };
}

export function ratioPercent(value: number, max: number): number {
  if (max <= 0) {
    return 0;
  }
  return clamp(Math.round((value / max) * 100), 0, 100);
}

export function formatLogEntry(entry: Record<string, unknown>): string {
  const reason = asString(entry.reason) || asString(entry.description);
  const amount = entry.amount ?? entry.change;
  const axis = asString(entry.axis);
  const pieces = [reason, axis ? axisLabel(axis) : "", amount !== undefined ? `${amount}` : ""]
    .filter(Boolean);
  return pieces.join(" · ") || JSON.stringify(entry);
}

function normalizeProgression(...values: unknown[]): ProgressionState {
  const source = firstRecord(values);
  const level = positiveNumber(source.level, 1);
  const xp = Math.max(0, asNumber(source.xp, 0));
  const nextLevelXp = positiveNumber(source.next_level_xp, 100 + (level - 1) * 75);
  return {
    level,
    xp,
    next_level_xp: nextLevelXp,
    total_xp: Math.max(xp, asNumber(source.total_xp, xp)),
    xp_log: asRecordList(source.xp_log).slice(-20)
  };
}

function normalizeProtagonist(
  rawSheet: unknown,
  rawProtagonist: unknown,
  progression: ProgressionState
): ProtagonistSheet {
  const sheet = asRecord(rawSheet);
  const protagonist = asRecord(rawProtagonist);
  return {
    name: asString(sheet.name) || asString(protagonist.name),
    identity: asString(sheet.identity) || asString(protagonist.identity),
    level: positiveNumber(sheet.level, progression.level),
    xp: Math.max(0, asNumber(sheet.xp, progression.xp)),
    next_level_xp: positiveNumber(sheet.next_level_xp, progression.next_level_xp),
    total_xp: Math.max(0, asNumber(sheet.total_xp, progression.total_xp)),
    attributes: firstRecord([sheet.attributes, protagonist.attributes])
  };
}

function normalizeActiveScene(rawScene: unknown, root: Record<string, unknown>): ActiveSceneState {
  const scene = asRecord(rawScene);
  const time = asRecord(root.time);
  const location = asRecord(root.location);
  return {
    turn: Math.max(0, asNumber(scene.turn, asNumber(root.current_turn, 0))),
    time: asString(scene.time) || asString(time.current) || asString(time.last_delta),
    location: asString(scene.location) || asString(location.current) || asString(location.name),
    pressure:
      asString(scene.pressure) ||
      asString(location.pressure) ||
      asString(time.pressure) ||
      asString(root.pressure),
    present_npcs: asStringList(scene.present_npcs)
  };
}

function normalizeSkills(value: unknown): SkillState[] {
  return asRecordList(value)
    .map((item) => {
      const level = positiveNumber(item.level, 1);
      const xp = Math.max(0, asNumber(item.xp, 0));
      const nextLevelXp = positiveNumber(item.next_level_xp, 80 + (level - 1) * 40);
      return {
        name: identity(item),
        level,
        xp,
        next_level_xp: nextLevelXp,
        mastery: clamp(asNumber(item.mastery, ratioPercent(xp, nextLevelXp)), 0, 100),
        visibility: asString(item.visibility) || "known",
        recent_events: asRecordList(item.recent_events).slice(-8)
      };
    })
    .filter((skill) => skill.name);
}

function normalizeAbilities(value: unknown): AbilityState[] {
  return asRecordList(value)
    .map((item) => ({
      name: identity(item),
      level: positiveNumber(item.level, 1),
      visibility: asString(item.visibility) || "known",
      description: asString(item.description),
      status: asString(item.status) || "active",
      resource_cost: asString(item.resource_cost),
      cooldown: asString(item.cooldown),
      usage_note: asString(item.usage_note)
    }))
    .filter((ability) => ability.name);
}

function normalizeConditions(value: unknown): ConditionState[] {
  return asRecordList(value)
    .map((item) => ({
      name: identity(item),
      status: asString(item.status) || "active",
      severity: asString(item.severity) || "medium",
      duration: asString(item.duration),
      source: asString(item.source),
      visibility: asString(item.visibility) || "known"
    }))
    .filter((condition) => condition.name);
}

function normalizeNpcRegistry(value: unknown): NpcRegistryItem[] {
  return asRecordList(value)
    .map((item) => {
      const name = identity(item);
      return {
        id: asString(item.id) || name,
        name,
        identity: asString(item.identity),
        status: asString(item.status) || asString(item.state),
        location: asString(item.location) || asString(item.current_location),
        relationship: asString(item.relationship),
        attitude: asString(item.attitude)
      };
    })
    .filter((npc) => npc.name);
}

function normalizeQuestLog(rawLog: unknown, rawQuests: unknown): QuestLog {
  const log = asRecord(rawLog);
  if (Object.keys(log).length > 0) {
    return {
      active: normalizeQuestItems(log.active),
      completed: normalizeQuestItems(log.completed),
      failed: normalizeQuestItems(log.failed),
      hidden: normalizeQuestItems(log.hidden)
    };
  }
  return {
    active: normalizeQuestItems(rawQuests),
    completed: [],
    failed: [],
    hidden: []
  };
}

function normalizeQuestItems(value: unknown): QuestItem[] {
  return asRecordList(value)
    .map((item) => ({
      name: identity(item),
      status: asString(item.status) || asString(item.state) || "active",
      objective: asString(item.objective) || asString(item.current) || asString(item.description)
    }))
    .filter((quest) => quest.name);
}

function normalizeThreadLog(rawLog: unknown, rawThreads: unknown): ThreadLog {
  const log = asRecord(rawLog);
  if (Object.keys(log).length > 0) {
    return {
      active: normalizeThreadItems(log.active),
      resolved: normalizeThreadItems(log.resolved)
    };
  }
  return {
    active: normalizeThreadItems(rawThreads),
    resolved: []
  };
}

function normalizeThreadItems(value: unknown): ThreadItem[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") {
          return { title: item, status: "active", source: "" };
        }
        const record = asRecord(item);
        return {
          title: asString(record.title) || asString(record.name) || asString(record.description),
          status: asString(record.status) || asString(record.state) || "active",
          source: asString(record.source)
        };
      })
      .filter((thread) => thread.title);
  }
  return [];
}

function normalizeAnchorProgress(value: unknown): { done: number; total: number } {
  const p = asRecord(value);
  return {
    done: Math.max(0, optionalNumber(p.done) ?? 0),
    total: Math.max(0, optionalNumber(p.total) ?? 0),
  };
}

function normalizeStoryProgress(value: unknown): StoryProgressState {
  const progress = asRecord(value);
  return {
    current_act: asString(progress.current_act) || asString(progress.act),
    completed_acts: asStringList(progress.completed_acts),
    completed_anchors: asStringList(progress.completed_anchors),
    ready_for_next_act: asBoolean(progress.ready_for_next_act, false),
    last_advance_turn: optionalNumber(progress.last_advance_turn),
    last_advance_reason: asString(progress.last_advance_reason),
    last_anchor_update_turn: optionalNumber(progress.last_anchor_update_turn),
    next_act: asString(progress.next_act),
    current_act_anchor_progress: normalizeAnchorProgress(progress.current_act_anchor_progress),
    current_act_title: asString(progress.current_act_title),
    current_act_objective: asString(progress.current_act_objective),
    campaign_complete: asBoolean(progress.campaign_complete, false),
    epilogue: asString(progress.epilogue),
    act_history: asRecordList(progress.act_history)
      .map((item) => ({
        turn: optionalNumber(item.turn),
        from_act: asString(item.from_act),
        to_act: asString(item.to_act),
        reason: asString(item.reason)
      }))
      .filter((item) => item.from_act || item.to_act || item.reason)
      .slice(-20),
    anchor_history: asRecordList(progress.anchor_history)
      .map((item) => ({
        turn: optionalNumber(item.turn),
        act: asString(item.act),
        anchor_id: asString(item.anchor_id) || asString(item.id),
        reason: asString(item.reason)
      }))
      .filter((item) => item.anchor_id)
      .slice(-30)
  };
}

function normalizeRelationships(value: unknown): RelationshipTrack[] {
  return asRecordList(value)
    .map((item) => ({
      npc: asString(item.npc) || identity(item),
      stage: asString(item.stage),
      visibility: asString(item.visibility) || "known",
      trust: axisValue(item.trust),
      affection: axisValue(item.affection),
      respect: axisValue(item.respect),
      fear: axisValue(item.fear),
      loyalty: axisValue(item.loyalty),
      conflict: axisValue(item.conflict),
      relationship: asString(item.relationship),
      attitude: asString(item.attitude),
      recent_interaction: asString(item.recent_interaction),
      recent_events: asRecordList(item.recent_events).slice(-8)
    }))
    .filter((track) => track.npc);
}

function axisValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return clamp(Math.round(value), 0, 100);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return clamp(Math.round(parsed), 0, 100);
    }
  }
  return null;
}

function axisLabel(axis: string): string {
  return relationshipAxes.find((item) => item.key === axis)?.label || axis;
}

// 线索 status 的中文映射。后端可能写入英文枚举（active/resolved…），直显会泄露原始值。
// 命中已知枚举返回中文；未知/无实义值返回空串，由 UI 决定回退展示（如只显示来源）。
const threadStatusLabels: Record<string, string> = {
  active: "进行中",
  open: "进行中",
  pending: "进行中",
  ongoing: "进行中",
  dormant: "搁置",
  resolved: "已了结",
  closed: "已了结",
  completed: "已了结",
  done: "已了结",
  finished: "已了结"
};

export function threadStatusLabel(status: string): string {
  const normalized = status.trim();
  if (!normalized) {
    return "";
  }
  return threadStatusLabels[normalized.toLowerCase()] || normalized;
}

function identity(item: Record<string, unknown>): string {
  return asString(item.name) || asString(item.id) || asString(item.title) || asString(item.npc);
}

function firstRecord(values: unknown[]): Record<string, unknown> {
  for (const value of values) {
    const record = asRecord(value);
    if (Object.keys(record).length > 0) {
      return record;
    }
  }
  return {};
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(asRecord).filter((item) => Object.keys(item).length > 0);
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(asString).filter(Boolean);
}

function asString(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = asNumber(value, Number.NaN);
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : null;
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "y"].includes(normalized)) {
      return true;
    }
    if (["false", "0", "no", "n"].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function positiveNumber(value: unknown, fallback: number): number {
  return Math.max(1, asNumber(value, fallback));
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
