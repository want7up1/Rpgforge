import { describe, it, expect } from "vitest";
import { buildModulePayload, moduleEditBlock, moduleTypeFromBlock } from "@/lib/moduleFragment";
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

describe("moduleEditBlock", () => {
  // 回归护栏：固定块无条件建块后，模块 payload 还原的首块恒为空 game_profile，
  // 导致工坊「编辑内容」全空白。moduleEditBlock 必须取真正有内容的块。
  it("素材模块片段 → 命中素材块而非空 game_profile", () => {
    const b = moduleEditBlock({ story_material_library: [{ title: "占位素材", content: "占位内容" }] });
    expect(b?.title).toBe("占位素材");
    expect(b?.address).toMatchObject({ kind: "settingsItem", arrayKey: "story_material_library" });
  });
  it("角色模块片段 → 命中角色块", () => {
    const b = moduleEditBlock({ core_characters: [{ name: "占位角色", role: "npc" }] });
    expect(b?.title).toBe("占位角色");
    expect(b?.address).toMatchObject({ kind: "settingsItem", arrayKey: "core_characters" });
  });
  it("标量片段 → 命中对应单值块", () => {
    const b = moduleEditBlock({ story_core: { central_mystery: "占位悬念" } });
    expect(b?.fields.some((f) => f.key === "central_mystery" && f.value === "占位悬念")).toBe(true);
  });
  it("字符串列表片段 → 命中对应桶块", () => {
    const b = moduleEditBlock({ hard_rules: { must_follow: ["占位规则"] } });
    expect(b?.title).toBe("必须遵守");
    expect(b?.fields[0]?.value).toEqual(["占位规则"]);
  });
});
