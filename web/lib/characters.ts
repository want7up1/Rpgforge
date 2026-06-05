import type { CharacterRead, CharacterRole, CharacterStoryProfile } from "@/lib/types";
import type { RelationshipTrack, StateV2 } from "@/lib/stateV2";

export const characterRoleLabels: Record<CharacterRole, string> = {
  protagonist: "主角",
  antagonist: "反派",
  companion: "同伴",
  npc: "NPC",
  other: "其他"
};

export const storyProfileLabels: Record<keyof CharacterStoryProfile, string> = {
  dramatic_function: "戏剧功能",
  desire: "欲望",
  fear: "恐惧",
  leverage: "可被牵动点",
  relationship_arc: "关系弧线",
  public_limit: "公开边界"
};

export const emptyStoryProfile: CharacterStoryProfile = {
  dramatic_function: "",
  desire: "",
  fear: "",
  leverage: "",
  relationship_arc: "",
  public_limit: ""
};

export type CharacterMatch = {
  label: string;
  character: CharacterRead;
};

export type CharacterRuntimeView = {
  location: string;
  status: string;
  relationship: string;
  attitude: string;
  stage: string;
  axes: { key: string; label: string; value: number }[];
  recent: string;
};

const relationshipAxisLabels: Record<string, string> = {
  trust: "信任",
  affection: "亲密",
  respect: "尊重",
  fear: "畏惧",
  loyalty: "忠诚",
  conflict: "冲突"
};

export function normalizeStoryProfile(
  value: Partial<CharacterStoryProfile> | null | undefined
): CharacterStoryProfile {
  return {
    dramatic_function: value?.dramatic_function ?? "",
    desire: value?.desire ?? "",
    fear: value?.fear ?? "",
    leverage: value?.leverage ?? "",
    relationship_arc: value?.relationship_arc ?? "",
    public_limit: value?.public_limit ?? ""
  };
}

export function normalizeCharacterName(value: string) {
  return value.trim().toLowerCase();
}

export function uniqueCharacterNames(values: string[]) {
  return values.filter(Boolean).filter((value, index, list) => {
    const normalized = normalizeCharacterName(value);
    return list.findIndex((item) => normalizeCharacterName(item) === normalized) === index;
  });
}

export function buildCharacterMatchers(characters: CharacterRead[]): CharacterMatch[] {
  const matches: CharacterMatch[] = [];
  const seen = new Set<string>();
  for (const character of characters) {
    if (!character.is_visible) {
      continue;
    }
    for (const rawLabel of [character.name, ...character.aliases]) {
      const label = rawLabel.trim();
      if (!label || label.length < 2 || seen.has(label)) {
        continue;
      }
      seen.add(label);
      matches.push({ label, character });
    }
  }
  return matches.sort((a, b) => b.label.length - a.label.length);
}

export function findCharacterTextMatch(
  text: string,
  index: number,
  matchers: CharacterMatch[]
): CharacterMatch | null {
  for (const matcher of matchers) {
    if (!text.startsWith(matcher.label, index)) {
      continue;
    }
    if (!hasAsciiBoundary(text, index, matcher.label.length)) {
      continue;
    }
    return matcher;
  }
  return null;
}

export function nextPotentialCharacterMatchIndex(
  text: string,
  startIndex: number,
  matchers: CharacterMatch[]
): number {
  let nextIndex = -1;
  for (const matcher of matchers) {
    const found = text.indexOf(matcher.label, startIndex);
    if (found !== -1 && (nextIndex === -1 || found < nextIndex)) {
      nextIndex = found;
    }
  }
  return nextIndex;
}

export function findCharacterByName(characters: CharacterRead[], name: string) {
  const normalized = normalizeCharacterName(name);
  return characters.find((character) => {
    if (normalizeCharacterName(character.name) === normalized) {
      return true;
    }
    return character.aliases.some((alias) => normalizeCharacterName(alias) === normalized);
  });
}

export function inferPresentCharacterNames(
  characters: CharacterRead[],
  stateV2: StateV2,
  narrative: string
) {
  const matchers = buildCharacterMatchers(characters);
  const mentioned = matchers
    .filter((matcher) => narrative.includes(matcher.label))
    .map((matcher) => matcher.character.name);
  return uniqueCharacterNames([
    stateV2.protagonist_sheet.name,
    ...stateV2.party,
    ...mentioned
  ]).slice(0, 6);
}

export function buildCharacterRuntimeView(
  character: CharacterRead,
  stateV2: StateV2 | null
): CharacterRuntimeView | null {
  if (!stateV2) {
    return null;
  }
  const npc = stateV2.npc_registry.find(
    (item) => normalizeCharacterName(item.name) === normalizeCharacterName(character.name)
  );
  const relation = findRelationshipTrack(character, stateV2.relationship_tracks);
  if (!npc && !relation) {
    return null;
  }
  return {
    location: npc?.location ?? "",
    status: npc?.status ?? "",
    relationship: relation?.relationship || npc?.relationship || "",
    attitude: relation?.attitude || npc?.attitude || "",
    stage: relation?.stage ?? "",
    axes: relation ? relationshipAxesFromTrack(relation) : [],
    recent: relation?.recent_interaction ?? ""
  };
}

function findRelationshipTrack(character: CharacterRead, tracks: RelationshipTrack[]) {
  const names = [character.name, ...character.aliases].map(normalizeCharacterName);
  return tracks.find((track) => names.includes(normalizeCharacterName(track.npc)));
}

function relationshipAxesFromTrack(track: RelationshipTrack) {
  return Object.entries(relationshipAxisLabels)
    .map(([key, label]) => {
      const value = track[key as keyof RelationshipTrack];
      return typeof value === "number" ? { key, label, value } : null;
    })
    .filter((item): item is { key: string; label: string; value: number } => item !== null);
}

function hasAsciiBoundary(text: string, index: number, length: number): boolean {
  const before = text[index - 1] ?? "";
  const after = text[index + length] ?? "";
  return !isAsciiWord(before) && !isAsciiWord(after);
}

function isAsciiWord(value: string): boolean {
  return /^[A-Za-z0-9_]$/.test(value);
}
