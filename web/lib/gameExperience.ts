import { isPrivateVisibility } from "@/lib/privateVisibility";
import type {
  SummaryRead,
  TurnRead
} from "@/lib/types";

export type TurnSettlementSection = {
  key: string;
  label: string;
  items: string[];
};

export type TurnSettlementView = {
  hasChanges: boolean;
  summary: string[];
  sections: TurnSettlementSection[];
  status: "confirmed" | "pending" | "skipped" | "failed" | "rejected" | "legacy";
  message: string;
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

// 纯叙事结算条：只汇总文字增量（关系/状态/线索/局面），无数字、无经验/技能、无行动判定后果。
export function buildTurnSettlement(turn: TurnRead): TurnSettlementView {
  const receipt = turn.settlement_receipt;
  if (receipt?.version === 1 && Array.isArray(receipt.sections)
    && ["confirmed", "pending", "skipped", "failed", "rejected"].includes(receipt.status)) {
    const sections = receipt.sections.filter(section => section && Array.isArray(section.changes)).map(section => ({
      key: pickString(asRecord(section), ["key"]), label: pickString(asRecord(section), ["label"]),
      items: section.changes.map(change => {
        const record = asRecord(change);
        const before = pickString(record, ["before"]), after = pickString(record, ["after"]);
        const transition = before && after ? `${before} → ${after}` : after || before;
        const reason = pickString(record, ["reason"]);
        return compactList([pickString(record, ["subject"]), transition, reason && !transition.includes(reason) ? reason : ""]).join(" · ");
      }).filter(Boolean)
    })).filter(section => section.items.length);
    return {
      hasChanges: sections.length > 0, sections, status: receipt.status,
      summary: sections.flatMap(section => section.items.slice(0, 2).map(item => `${section.label}：${item}`)).slice(0, 4),
      message: pickString(asRecord(receipt), ["message"]) || ({ confirmed: "已核验本回合实际变化", pending: "剧情已生成，状态正在整理。", skipped: "本回合状态未能确认，已跳过状态更新并保留剧情。", failed: "本回合状态整理失败，请稍后恢复。", rejected: "本回合状态变化未被采用。" }[receipt.status])
    };
  }
  const delta = asRecord(turn.state_delta_json);
  const sections: TurnSettlementSection[] = [];

  pushSection(sections, "relationships", "NPC 关系", formatEventList(delta.relationship_events));
  pushSection(sections, "conditions", "状态", [
    ...formatEventList(delta.condition_updates),
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
    status: "legacy",
    message: "旧记录：以下为历史提取结果，尚未核验实际落账。"
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
  if (isPrivateVisibility(record.visibility)) return [];
  if (Object.keys(record).length === 0) {
    return [];
  }

  const name = pickString(record, [
    "name",
    "item",
    "npc",
    "target",
    "condition",
    "quest",
    "title",
    "fact"
  ]);
  // 纯叙事：只取文字字段（status/note/reason），不再渲染任何数值增量。
  const status = pickString(record, ["status", "relationship", "attitude"]);
  const reason = pickString(record, ["note", "reason", "description", "detail", "summary"]);
  const pieces = compactList([prefix, name, status, reason]);

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

function valueToList(value: unknown): string[] {
  if (value === null || value === undefined) return [];
  if (Array.isArray(value)) return value.flatMap(valueToList);
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return [String(value).trim()].filter(Boolean);
  return Object.values(asRecord(value)).flatMap(valueToList).filter(Boolean);
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
