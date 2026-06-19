import type {
  ConfirmedRequirements,
  GameDetail,
  GeneratedGameConfig,
  SummaryRead,
  TurnRead
} from "@/lib/types";

export type TurnSettlementSection = {
  key: string;
  label: string;
  items: string[];
};

export type ActionOutcomeTone = "great" | "good" | "partial" | "fail" | "neutral";

export type ActionOutcomeView = {
  label: string;
  tone: ActionOutcomeTone;
  action: string;
  roll: number | null;
  modifier: number;
  dc: number | null;
};

export type TurnSettlementView = {
  hasChanges: boolean;
  summary: string[];
  sections: TurnSettlementSection[];
  outcome: ActionOutcomeView | null;
};

export type ContractSectionView = {
  key: string;
  label: string;
  items: string[];
};

export type ContractView = {
  hasContent: boolean;
  sections: ContractSectionView[];
};

export type ChapterView = {
  id: string;
  title: string;
  rangeLabel: string;
  startTurn: number | null;
  endTurn: number | null;
  content: string;
  importantFacts: string[];
  turns: TurnRead[];
};

export type StoryBlueprintView = {
  title: string;
  description: string;
  centralQuestion: string;
  openingStage: string;
  currentAct: string;
  currentActGoal: string;
  mustPreserve: string[];
  mustNotBecome: string[];
  pressureClock: string[];
};

export function normalizeConfirmedRequirements(
  value: unknown,
  rawUserInput = ""
): ConfirmedRequirements {
  const record = asRecord(value);
  const storyBackground =
    pickString(record, ["story_background", "background", "setting"]) ||
    compactList([
      pickString(record, ["genre"]),
      pickString(record, ["world_style"])
    ]).join("；");
  const corePremise =
    pickString(record, ["core_premise", "premise"]) ||
    compactList([
      pickString(record, ["player_fantasy"]),
      pickString(record, ["protagonist_identity"]),
      pickString(record, ["core_gameplay"])
    ]).join("；");

  return {
    story_background: storyBackground,
    core_premise: corePremise,
    must_include: unique([
      ...pickList(record, ["must_include"]),
      ...pickList(record, ["must_hit_beats"]),
      ...pickList(record, ["relationship_focus"])
    ]),
    forbidden_content: unique([
      ...pickList(record, ["forbidden_content"]),
      ...pickList(record, ["forbidden_elements"]),
      ...pickList(record, ["forbidden_drift"])
    ]),
    playstyle_preferences: unique([
      ...pickList(record, ["playstyle_preferences"]),
      ...pickList(record, ["rule_complexity"]),
      ...pickList(record, ["failure_cost"]),
      ...pickList(record, ["core_gameplay"])
    ]),
    tone_preferences: unique([
      ...pickList(record, ["tone_preferences"]),
      ...pickList(record, ["world_style"]),
      ...pickList(record, ["pacing_preference"])
    ]),
    raw_user_input: pickString(record, ["raw_user_input"]) || rawUserInput
  };
}

export function buildGeneratedConfigBlueprint(config: GeneratedGameConfig): StoryBlueprintView {
  const storySettings = asRecord(config.story_settings);
  return buildBlueprintFromParts({
    title: config.title,
    description: config.description ?? "",
    storySettings,
    loreCount: asList(storySettings.story_material_library).length,
    modeCount: asList(storySettings.action_style_rules).length
  });
}

export function buildGameBlueprint(game: GameDetail): StoryBlueprintView {
  const storySettings = asRecord(game.config?.story_settings);
  return buildBlueprintFromParts({
    title: game.title,
    description: game.description ?? "",
    storySettings,
    stateJson: game.state?.state_json,
    loreCount: asList(storySettings.story_material_library).length,
    modeCount: asList(storySettings.action_style_rules).length
  });
}

function buildBlueprintFromParts({
  title,
  description,
  storySettings,
  stateJson
}: {
  title: string;
  description: string;
  storySettings: Record<string, unknown>;
  stateJson?: Record<string, unknown>;
  loreCount: number;
  modeCount: number;
}): StoryBlueprintView {
  const worldview = asRecord(storySettings.worldview);
  const core = asRecord(storySettings.story_core);
  const acts = asList(storySettings.act_plan);
  const stateRoot = asRecord(stateJson);
  const runtimeProgress = firstRecord([
    stateRoot.story_progress,
    asRecord(stateRoot.v2).story_progress
  ]);
  const currentActId =
    pickString(runtimeProgress, ["current_act", "act"]) ||
    pickString(core, ["current_act", "act", "stage", "phase"]);
  const currentAct = findAct(acts, currentActId);
  const firstAct = asRecord(acts[0]);

  return {
    title,
    description,
    centralQuestion:
      pickString(core, ["central_mystery", "central_question"]) ||
      pickString(currentAct, ["dramatic_question"]),
    openingStage: pickString(worldview, ["setting", "opening_stage", "summary"]),
    currentAct: compactList([
      currentActId,
      pickString(currentAct, ["name", "title"])
    ]).join(" · "),
    currentActGoal:
      pickString(currentAct, ["objective", "goal"]) ||
      pickString(firstAct, ["objective", "goal"]) ||
      pickString(core, ["main_goal", "premise"]),
    mustPreserve: unique([
      ...pickList(core, ["must_preserve"])
    ]),
    mustNotBecome: unique([
      ...pickList(core, ["must_not_become"]),
      ...pickList(core, ["forbidden_drift"])
    ]),
    pressureClock: readableLines(storySettings.main_quest_path).slice(0, 4)
  };
}

export function buildTurnSettlement(turn: TurnRead): TurnSettlementView {
  const delta = asRecord(turn.state_delta_json);
  const sections: TurnSettlementSection[] = [];

  pushSection(sections, "xp", "经验", formatEventList(delta.xp_events));
  pushSection(sections, "skills", "技能熟练度", [
    ...formatEventList(delta.skill_events),
    ...formatEventList(delta.ability_events)
  ]);
  pushSection(sections, "relationships", "NPC 关系", formatEventList(delta.relationship_events));
  pushSection(sections, "conditions", "条件与状态", [
    ...formatEventList(delta.condition_events),
    ...formatEventList(delta.protagonist_updates)
  ]);
  pushSection(sections, "inventory", "物品", [
    ...formatEventList(delta.inventory_add, "获得"),
    ...formatEventList(delta.inventory_remove, "失去")
  ]);
  pushSection(sections, "threads", "线索与任务", [
    ...formatEventList(delta.new_known_facts),
    ...formatEventList(delta.open_thread_updates),
    ...formatEventList(delta.quest_updates)
  ]);
  pushSection(sections, "scene", "局面", [
    ...formatEventList(delta.location_change),
    ...formatEventList(delta.time_delta),
    ...formatEventList(delta.time_current)
  ]);

  const summary = sections.flatMap((section) =>
    section.items.slice(0, 2).map((item) => `${section.label}：${item}`)
  );

  return {
    hasChanges: sections.length > 0,
    summary: summary.slice(0, 4),
    sections,
    outcome: extractActionOutcome(delta.action_outcome)
  };
}

const OUTCOME_TONE: Record<string, ActionOutcomeTone> = {
  critical: "great",
  success: "good",
  partial: "partial",
  failure: "fail"
};

// 从 state_delta_json.action_outcome 取本回合判定结果（仅掷骰回合有；无判定返回 null，不伪造）。
function extractActionOutcome(value: unknown): ActionOutcomeView | null {
  const record = asRecord(value);
  const outcomeKey = pickString(record, ["outcome"]);
  const label = pickString(record, ["outcome_label"]) || outcomeKey;
  if (!label) {
    return null;
  }
  return {
    label,
    tone: OUTCOME_TONE[outcomeKey] ?? "neutral",
    action: pickString(record, ["action"]),
    roll: typeof record.roll === "number" ? record.roll : null,
    modifier: typeof record.modifier === "number" ? record.modifier : 0,
    dc: typeof record.dc === "number" ? record.dc : null
  };
}

export function buildContractView(game: GameDetail): ContractView {
  const storySettings = asRecord(game.config?.story_settings);
  const profile = asRecord(storySettings.game_profile);
  const worldview = asRecord(storySettings.worldview);
  const storyCore = asRecord(storySettings.story_core);
  const hardRules = asRecord(storySettings.hard_rules);
  const acts = asList(storySettings.act_plan);
  const stateRoot = asRecord(game.state?.state_json);
  const runtimeProgress = firstRecord([
    stateRoot.story_progress,
    asRecord(stateRoot.v2).story_progress
  ]);
  const currentActId =
    pickString(runtimeProgress, ["current_act", "act"]) ||
    pickString(storyCore, ["current_act", "act", "stage", "phase"]);
  const currentAct = findAct(acts, currentActId);
  const firstAct = asRecord(acts[0]);

  const sections: ContractSectionView[] = [
    {
      key: "brief",
      label: "故事种子",
      items: compactList([
        pickString(storyCore, ["premise"]),
        pickString(storyCore, ["core_fantasy"]),
        pickString(profile, ["genre"]),
        pickString(profile, ["description"]) || game.description
      ])
    },
    {
      key: "question",
      label: "核心悬念",
      items: compactList([
        pickString(storyCore, ["central_mystery", "central_question"]),
        pickString(currentAct, ["dramatic_question"]),
      ])
    },
    {
      key: "goal",
      label: "主线目标",
      items: compactList([
        pickString(storyCore, ["main_goal", "core_goal", "objective", "goal", "campaign_goal"]),
        pickString(currentAct, ["objective", "goal"]),
        pickString(firstAct, ["objective", "goal"]),
        pickString(storyCore, ["premise"])
      ])
    },
    {
      key: "act",
      label: "当前幕",
      items: compactList([
        currentActId,
        pickString(currentAct, ["name", "title"]),
        pickString(currentAct, ["objective", "goal"])
      ])
    },
    {
      key: "must",
      label: "必须保留",
      items: compactList([
        ...pickList(storyCore, ["must_preserve"]),
        ...pickList(hardRules, ["must_follow"]),
        ...pickList(currentAct, ["must_hit_beats"])
      ])
    },
    {
      key: "guardrails",
      label: "禁止变成",
      items: compactList([
        ...pickList(storyCore, ["must_not_become"]),
        ...pickList(storyCore, [
          "forbidden_drift",
          "forbidden_deviations",
          "forbidden_points",
          "avoid",
          "must_not"
        ]),
        ...pickList(hardRules, ["must_not"])
      ])
    },
    {
      key: "style",
      label: "叙事风格",
      items: compactList([
        pickString(worldview, ["tone", "mood"]),
        pickString(profile, ["tone"]),
        pickString(storyCore, ["narrative_style", "style", "voice", "pacing"]),
        ...pickList(storyCore, ["tone_do"]),
        ...pickList(storyCore, ["tone_dont"]),
        ...pickList(storyCore, ["pacing_rules"])
      ])
    },
    {
      key: "conflict",
      label: "关键 NPC / 关键冲突",
      items: compactList([
        ...pickList(storyCore, ["key_npcs", "important_npcs"]),
        ...namesFromRelationshipArcs(pickList(storyCore, ["relationship_arcs"])),
        ...pickList(storyCore, ["key_conflicts", "main_conflict"]),
        ...pickList(worldview, ["key_npcs", "factions", "conflicts", "core_conflicts", "main_conflict"])
      ])
    }
  ];
  const normalizedSections = sections.map((section) => ({
    ...section,
    items: unique(compactList(section.items))
  }));

  return {
    hasContent: normalizedSections.some((section) => section.items.length > 0),
    sections: normalizedSections
  };
}

export function buildChapterViews(summaries: SummaryRead[], turns: TurnRead[]): ChapterView[] {
  const sortedTurns = [...turns].sort((a, b) => a.turn_number - b.turn_number);
  const chapterSummaries = summaries
    .filter((summary) => summary.type === "chapter")
    .sort((a, b) => (a.range_start_turn ?? 0) - (b.range_start_turn ?? 0));
  const sourceSummaries =
    chapterSummaries.length > 0
      ? chapterSummaries
      : summaries
          .filter((summary) => summary.type === "long_term")
          .sort((a, b) => (a.range_start_turn ?? 0) - (b.range_start_turn ?? 0));

  if (sourceSummaries.length > 0) {
    return sourceSummaries.map((summary, index) => {
      const relatedTurns = turnsForSummary(summary, sortedTurns);
      return {
        id: summary.id,
        title: chapterTitle(summary, index),
        rangeLabel: summaryRange(summary),
        startTurn: summary.range_start_turn,
        endTurn: summary.range_end_turn,
        content: summary.content,
        importantFacts: factsToList(summary.important_facts).slice(0, 8),
        turns: relatedTurns
      };
    });
  }

  if (sortedTurns.length === 0) {
    return [];
  }

  return chunkTurns(sortedTurns, 5).map((group, index) => ({
    id: `fallback-${index}`,
    title: `章节 ${index + 1}`,
    rangeLabel: `第 ${group[0].turn_number}-${group[group.length - 1].turn_number} 回`,
    startTurn: group[0].turn_number,
    endTurn: group[group.length - 1].turn_number,
    content: group
      .map((turn) => turn.visible_summary || firstSentence(turn.gm_output) || turn.player_input)
      .filter(Boolean)
      .join("\n\n"),
    importantFacts: [],
    turns: group
  }));
}

function pushSection(
  sections: TurnSettlementSection[],
  key: string,
  label: string,
  items: string[]
) {
  const uniqueItems = unique(compactList(items)).slice(0, 8);
  if (uniqueItems.length === 0) {
    return;
  }
  sections.push({ key, label, items: uniqueItems });
}

function formatEventList(value: unknown, prefix = ""): string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => formatEventList(item, prefix));
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return [`${prefix ? `${prefix}：` : ""}${String(value)}`];
  }
  const record = asRecord(value);
  if (Object.keys(record).length === 0) {
    return [];
  }

  const name = pickString(record, [
    "name",
    "item",
    "skill",
    "ability",
    "npc",
    "target",
    "condition",
    "quest",
    "title",
    "fact"
  ]);
  const amount = record.amount ?? record.change ?? record.delta ?? record.value;
  const axis = pickString(record, ["axis", "track", "type"]);
  const status = pickString(record, ["status", "stage", "relationship", "attitude"]);
  const reason = pickString(record, ["reason", "description", "detail", "summary", "note"]);
  const pieces = compactList([
    prefix,
    name,
    axis,
    amount === undefined ? "" : String(amount),
    status,
    reason
  ]);

  if (pieces.length > 0) {
    return [pieces.join(" · ")];
  }
  return [compactRecord(record)];
}

function pickString(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
  }
  return "";
}

function pickList(record: Record<string, unknown>, keys: string[]): string[] {
  for (const key of keys) {
    const value = record[key];
    const list = valueToList(value);
    if (list.length > 0) {
      return list;
    }
  }
  return [];
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function findAct(acts: unknown[], currentActId: string): Record<string, unknown> {
  if (!currentActId) {
    return asRecord(acts[0]);
  }
  return asRecord(
    acts.find((item) => {
      const act = asRecord(item);
      return ["id", "key", "name", "title"].some((key) => pickString(act, [key]) === currentActId);
    })
  );
}

function namesFromRelationshipArcs(arcs: string[]): string[] {
  return arcs
    .map((arc) => arc.split(/[：:]/)[0]?.trim() ?? "")
    .filter(Boolean);
}

function valueToList(value: unknown): string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap(valueToList);
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return [String(value).trim()].filter(Boolean);
  }
  const record = asRecord(value);
  return Object.values(record)
    .flatMap(valueToList)
    .filter(Boolean);
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

function readableLines(value: unknown): string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap(readableLines);
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return [String(value).trim()].filter(Boolean);
  }
  const record = asRecord(value);
  if (Object.keys(record).length === 0) {
    return [];
  }
  const title = pickString(record, ["name", "title", "stage", "truth", "clue"]);
  const detail = compactList([
    pickString(record, ["tick_condition", "condition"]),
    pickString(record, ["consequence", "points_to", "reveal_condition", "do_not_reveal"]),
    pickString(record, ["visibility"])
  ]).join(" · ");
  return [compactList([title, detail]).join("：") || compactRecord(record)];
}

function factsToList(value: Record<string, unknown>): string[] {
  return Object.entries(value).flatMap(([key, item]) => {
    const list = valueToList(item);
    if (list.length === 0) {
      return [];
    }
    return list.map((entry) => `${key}：${entry}`);
  });
}

function turnsForSummary(summary: SummaryRead, turns: TurnRead[]) {
  const start = summary.range_start_turn;
  const end = summary.range_end_turn;
  if (!start || !end) {
    return [];
  }
  return turns.filter((turn) => turn.turn_number >= start && turn.turn_number <= end);
}

function chapterTitle(summary: SummaryRead, index: number) {
  const facts = asRecord(summary.important_facts);
  const title =
    pickString(facts, ["title", "chapter_title", "name"]) ||
    firstSentence(summary.content) ||
    `章节 ${index + 1}`;
  return title.length > 28 ? `${title.slice(0, 28)}...` : title;
}

function summaryRange(summary: SummaryRead) {
  if (!summary.range_start_turn || !summary.range_end_turn) {
    return "暂无回合范围";
  }
  if (summary.range_start_turn === summary.range_end_turn) {
    return `第 ${summary.range_end_turn} 回`;
  }
  return `第 ${summary.range_start_turn}-${summary.range_end_turn} 回`;
}

function firstSentence(value: string | null | undefined) {
  const text = (value ?? "").trim();
  if (!text) {
    return "";
  }
  return text.split(/[。！？.!?\n]/)[0]?.trim() ?? "";
}

function chunkTurns(turns: TurnRead[], size: number) {
  const chunks: TurnRead[][] = [];
  for (let index = 0; index < turns.length; index += size) {
    chunks.push(turns.slice(index, index + size));
  }
  return chunks;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function compactRecord(record: Record<string, unknown>) {
  return Object.entries(record)
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ");
}

function compactList(values: Array<string | null | undefined>) {
  return values.map((value) => (value ?? "").trim()).filter(Boolean);
}

function unique(values: string[]) {
  return Array.from(new Set(values));
}
