import type { GameDetail } from "@/lib/types";

// 纯叙事改造：主角档案只剩姓名/身份/处境文字，删除等级/经验/属性/技能/能力。
export type ProtagonistSheet = {
  name: string;
  identity: string;
  conditions: ConditionState[];
};

// 处境：全部文字，无 severity/duration 数字。
export type ConditionState = {
  name: string;
  status: string;
  note: string;
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
  defeat?: boolean;
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

// 关系：纯文字。status 是一句叙述（如"从猜忌转为并肩"），note 是可选补充。
export type RelationshipTrack = {
  npc: string;
  status: string;
  note: string;
  visibility: string;
};

export type StateV2 = {
  version: number;
  active_scene: ActiveSceneState;
  protagonist_sheet: ProtagonistSheet;
  conditions: ConditionState[];
  party: string[];
  npc_registry: NpcRegistryItem[];
  quest_log: QuestLog;
  open_threads: ThreadLog;
  story_progress: StoryProgressState;
  relationship_tracks: RelationshipTrack[];
};

export function getStateV2FromGame(game: GameDetail): StateV2 {
  return getStateV2(game.state?.state_json);
}

export function getStateV2(stateJson: Record<string, unknown> | null | undefined): StateV2 {
  const root = asRecord(stateJson);
  const rawV2 = asRecord(root.v2);
  const conditions = normalizeConditions(rawV2.conditions ?? root.conditions);
  const protagonist = normalizeProtagonist(rawV2.protagonist_sheet, root.protagonist, conditions);

  return {
    version: asNumber(rawV2.version, 1),
    active_scene: normalizeActiveScene(rawV2.active_scene, root),
    protagonist_sheet: protagonist,
    conditions,
    party: asStringList(rawV2.party ?? root.party),
    npc_registry: normalizeNpcRegistry(rawV2.npc_registry ?? root.npcs),
    quest_log: normalizeQuestLog(rawV2.quest_log, root.quests),
    open_threads: normalizeThreadLog(rawV2.open_threads, root.open_threads),
    story_progress: normalizeStoryProgress(
      firstRecord([rawV2.story_progress, root.story_progress])
    ),
    relationship_tracks: normalizeRelationships(rawV2.relationship_tracks ?? root.relationships)
  };
}

function normalizeProtagonist(
  rawSheet: unknown,
  rawProtagonist: unknown,
  conditions: ConditionState[]
): ProtagonistSheet {
  const sheet = asRecord(rawSheet);
  const protagonist = asRecord(rawProtagonist);
  return {
    name: asString(sheet.name) || asString(protagonist.name),
    identity: asString(sheet.identity) || asString(protagonist.identity),
    conditions: conditions.length > 0 ? conditions : normalizeConditions(sheet.conditions)
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

function normalizeConditions(value: unknown): ConditionState[] {
  return asRecordList(value)
    .map((item) => ({
      name: identity(item),
      status: asString(item.status) || "active",
      note: asString(item.note),
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
    defeat: asBoolean(progress.defeat, false),
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
      // status 是一句叙述文字；兼容旧字段名（relationship/stage/attitude）作回退。
      status:
        asString(item.status) ||
        asString(item.relationship) ||
        asString(item.stage) ||
        asString(item.attitude),
      note: asString(item.note) || asString(item.recent_interaction),
      visibility: asString(item.visibility) || "known"
    }))
    .filter((track) => track.npc);
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
