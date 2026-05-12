import type { GameDetail, SummaryRead, TurnRead } from "@/lib/types";

export type TurnSettlementSection = {
  key: string;
  label: string;
  items: string[];
};

export type TurnSettlementView = {
  hasChanges: boolean;
  summary: string[];
  sections: TurnSettlementSection[];
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
    sections
  };
}

export function buildContractView(game: GameDetail): ContractView {
  const config = game.config;
  const script = asRecord(config?.script_outline);
  const worldview = asRecord(config?.worldview);
  const campaignContract = asRecord(script.campaign_contract);
  const directorContract = asRecord(script.director_contract);
  const storyContract = asRecord(script.story_contract);

  const sections: ContractSectionView[] = [
    {
      key: "tone",
      label: "题材与基调",
      items: compactList([
        game.genre,
        game.description,
        pickString(worldview, ["summary", "overview", "theme", "tone", "genre"]),
        pickString(storyContract, ["tone", "mood", "genre"])
      ])
    },
    {
      key: "goal",
      label: "主线目标",
      items: compactList([
        pickString(campaignContract, ["main_goal", "core_goal", "objective", "goal", "campaign_goal"]),
        pickString(script, ["main_goal", "core_goal", "objective"])
      ])
    },
    {
      key: "act",
      label: "当前幕",
      items: compactList([
        pickString(campaignContract, ["current_act", "act", "stage", "phase"]),
        pickString(directorContract, ["current_act", "act", "stage"])
      ])
    },
    {
      key: "guardrails",
      label: "禁止偏离点",
      items: compactList([
        ...pickList(campaignContract, ["forbidden_deviations", "forbidden_points", "avoid", "must_not"]),
        ...pickList(directorContract, ["forbidden_deviations", "guardrails", "must_not", "avoid"]),
        ...pickList(storyContract, ["forbidden_deviations", "must_not", "avoid"])
      ])
    },
    {
      key: "style",
      label: "叙事风格",
      items: compactList([
        pickString(storyContract, ["narrative_style", "style", "voice", "pacing"]),
        pickString(directorContract, ["pacing", "narrative_focus", "style"]),
        pickString(script, ["narrative_style", "style"])
      ])
    },
    {
      key: "conflict",
      label: "关键 NPC / 关键冲突",
      items: compactList([
        ...pickList(campaignContract, ["key_npcs", "important_npcs", "key_conflicts", "main_conflict"]),
        ...pickList(storyContract, ["key_npcs", "important_npcs", "key_conflicts"]),
        ...pickList(worldview, ["key_npcs", "factions", "conflicts", "main_conflict"])
      ])
    }
  ];

  return {
    hasContent: sections.some((section) => section.items.length > 0),
    sections
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
