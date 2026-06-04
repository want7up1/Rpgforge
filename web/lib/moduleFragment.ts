import type { BoardBlock } from "@/lib/generatorBoard";

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}
function asArray(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v) ? (v as Record<string, unknown>[]) : [];
}
function readPath(root: Record<string, unknown>, path: string[]): unknown {
  let node: unknown = root;
  for (const seg of path) {
    if (node && typeof node === "object" && !Array.isArray(node)) {
      node = (node as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return node;
}
function setPath(value: unknown, path: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  let node = out;
  for (let i = 0; i < path.length - 1; i += 1) {
    node[path[i]] = {};
    node = node[path[i]] as Record<string, unknown>;
  }
  node[path[path.length - 1]] = value;
  return out;
}
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v ?? null)) as T;
}

// module_type 直接取看板分类（world/characters/plot/mechanics/constraints/materials）
export function moduleTypeFromBlock(block: BoardBlock): string {
  return block.category;
}

// 从源 story_settings 按 block.address 读出完整数据，组装最小片段 payload。
export function buildModulePayload(
  storySettings: Record<string, unknown>,
  block: BoardBlock
): Record<string, unknown> {
  const a = block.address;
  if (a.kind === "settingsItem") {
    const item = asArray(storySettings[a.arrayKey]).find((it) => str(it[a.idKey]) === a.idValue);
    return item ? { [a.arrayKey]: [clone(item)] } : {};
  }
  if (a.kind === "settingsStringList") {
    const value = readPath(storySettings, a.path);
    return setPath(Array.isArray(value) ? clone(value) : [], a.path);
  }
  if (a.kind === "settingsScalar") {
    const value = readPath(storySettings, a.path);
    return setPath(value === undefined ? "" : clone(value), a.path);
  }
  return {}; // confirmedField 不支持提取（提取仅在 settings 形态看板）
}

// block 是否可提取为模块（仅 settings 形态地址）
export function isExtractable(block: BoardBlock): boolean {
  return block.address.kind !== "confirmedField";
}
