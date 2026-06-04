import { describe, it, expect } from "vitest";
import { buildModulePayload, moduleTypeFromBlock } from "@/lib/moduleFragment";
import { buildBoardModel, type BoardBlock } from "@/lib/generatorBoard";

const settings = {
  core_characters: [{ name: "主角", role: "protagonist" }, { name: "红伞女人", role: "npc", desire: "复仇" }],
  story_core: { canon_terms: ["雁回镇", "红伞"] },
  hard_rules: { must_follow: ["战斗须详细", "不剧透身世"], must_not: [] },
  core_mechanics: [{ name: "检定", rule: "d20" }]
};
function block(title: string): BoardBlock {
  const model = buildBoardModel({ source: "settings", settings });
  return model.categories.flatMap((c) => c.blocks).find((b) => b.title === title)!;
}

describe("buildModulePayload", () => {
  it("settingsItem 角色 → 完整条目片段", () => {
    expect(buildModulePayload(settings, block("红伞女人"))).toEqual({
      core_characters: [{ name: "红伞女人", role: "npc", desire: "复仇" }]
    });
  });
  it("settingsStringList 约束 → 桶片段", () => {
    expect(buildModulePayload(settings, block("必须遵守"))).toEqual({
      hard_rules: { must_follow: ["战斗须详细", "不剧透身世"] }
    });
  });
  it("settingsStringList 专名 → story_core 桶", () => {
    expect(buildModulePayload(settings, block("专名表"))).toEqual({
      story_core: { canon_terms: ["雁回镇", "红伞"] }
    });
  });
  it("module_type = block.category", () => {
    expect(moduleTypeFromBlock(block("红伞女人"))).toBe("characters");
    expect(moduleTypeFromBlock(block("检定"))).toBe("mechanics");
  });
});
