import { describe, it, expect } from "vitest";
import { buildBoardModel, BOARD_CATEGORIES } from "@/lib/generatorBoard";

describe("buildBoardModel from story_settings", () => {
  const settings = {
    game_profile: { title: "雁回镇旧案", genre: "黑暗武侠", tone: "阴郁" },
    worldview: { summary: "雨夜义庄" },
    story_core: {
      central_mystery: "镖队为何失踪",
      must_preserve: ["雨夜义庄"],
      must_not_become: ["修仙飞升"],
      canon_terms: ["红伞"]
    },
    core_characters: [
      { name: "失忆镖师", role: "protagonist", description: "主角" },
      { name: "红伞女人", role: "npc", description: "神秘" }
    ],
    act_plan: [{ id: "act_1", title: "雨夜义庄", objective: "查失踪" }],
    main_quest_path: [{ id: "mq_1", title: "找镖队" }],
    core_mechanics: [{ name: "检定", rule: "d20" }],
    action_style_rules: [{ name: "战斗描写", rule: "详细" }],
    story_material_library: [{ title: "红伞传说", content: "..." }],
    hard_rules: { must_follow: ["完整描写"], must_not: ["剧透身世"], reveal_rules: [], continuity_rules: [] }
  };

  it("产出 7 个分类（含高级）", () => {
    const model = buildBoardModel({ source: "settings", settings });
    expect(model.categories.map((c) => c.id)).toEqual(
      BOARD_CATEGORIES.map((c) => c.id)
    );
  });

  it("角色分类含 2 个 block，title 为角色名", () => {
    const model = buildBoardModel({ source: "settings", settings });
    const chars = model.categories.find((c) => c.id === "characters")!;
    expect(chars.blocks.map((b) => b.title)).toEqual(["失忆镖师", "红伞女人"]);
  });

  it("约束分类带 danger 配色且含 hard_rules + story_core 红线", () => {
    const model = buildBoardModel({ source: "settings", settings });
    const con = model.categories.find((c) => c.id === "constraints")!;
    expect(con.tone).toBe("danger");
    const titles = con.blocks.map((b) => b.title);
    expect(titles).toContain("必须遵守");
    expect(titles).toContain("禁止变成");
    expect(titles).toContain("专名表");
  });

  it("每个角色 block 的 address 能定位回数组项", () => {
    const model = buildBoardModel({ source: "settings", settings });
    const hong = model.categories
      .find((c) => c.id === "characters")!
      .blocks.find((b) => b.title === "红伞女人")!;
    expect(hong.address).toEqual({
      kind: "settingsItem",
      arrayKey: "core_characters",
      idKey: "name",
      idValue: "红伞女人"
    });
  });
});
