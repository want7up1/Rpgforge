import { describe, it, expect } from "vitest";
import { buildBoardModel, BOARD_CATEGORIES, diffBoard, isLocked, lockBlock, unlockBlock, writeBlockFields, deleteBlock } from "@/lib/generatorBoard";

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

describe("buildBoardModel from confirmed_requirements", () => {
  const confirmed = {
    story_background: "黑暗武侠·雁回镇义庄",
    core_premise: "失忆镖师查失踪镖队",
    must_include: ["雨夜义庄", "红伞女人"],
    forbidden_content: ["修仙飞升"],
    playstyle_preferences: ["调查为主"],
    tone_preferences: ["阴郁"],
    raw_user_input: "..."
  };

  it("block id 等于 confirmed 字段名（便于锁定透传后端）", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed });
    const world = model.categories.find((c) => c.id === "world")!;
    expect(world.blocks.map((b) => b.id)).toContain("story_background");
    expect(world.blocks.map((b) => b.id)).toContain("core_premise");
    expect(world.blocks.map((b) => b.id)).toContain("tone_preferences");
  });

  it("must_include/forbidden_content 落约束类", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed });
    const con = model.categories.find((c) => c.id === "constraints")!;
    expect(con.blocks.map((b) => b.id)).toEqual(["must_include", "forbidden_content"]);
  });

  it("playstyle_preferences 落机制类，address 为 confirmedField", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed });
    const mech = model.categories.find((c) => c.id === "mechanics")!;
    const block = mech.blocks.find((b) => b.id === "playstyle_preferences")!;
    expect(block.address).toEqual({ kind: "confirmedField", field: "playstyle_preferences" });
  });

  it("空字段不产 block", () => {
    const model = buildBoardModel({ source: "confirmed", confirmed: { story_background: "x" } });
    const world = model.categories.find((c) => c.id === "world")!;
    expect(world.blocks.map((b) => b.id)).toEqual(["story_background"]);
  });
});

describe("diffBoard", () => {
  const base = { story_background: "a", must_include: ["x"] };
  const prev = buildBoardModel({ source: "confirmed", confirmed: base });

  it("新增 block 计入对应分类，记录 changedBlockIds", () => {
    const next = buildBoardModel({
      source: "confirmed",
      confirmed: { ...base, core_premise: "b" }
    });
    const diff = diffBoard(prev, next);
    expect(diff.changedCategories.world).toBe(1);
    expect(diff.changedBlockIds.has("core_premise")).toBe(true);
  });

  it("内容变化算改动", () => {
    const next = buildBoardModel({
      source: "confirmed",
      confirmed: { ...base, story_background: "a2" }
    });
    const diff = diffBoard(prev, next);
    expect(diff.changedBlockIds.has("story_background")).toBe(true);
  });

  it("无变化时计数为 0", () => {
    const next = buildBoardModel({ source: "confirmed", confirmed: base });
    const diff = diffBoard(prev, next);
    expect(diff.changedBlockIds.size).toBe(0);
    expect(Object.values(diff.changedCategories).every((n) => n === 0)).toBe(true);
  });

  it("prev 为 null（首次生成）时所有 block 算新", () => {
    const next = buildBoardModel({ source: "confirmed", confirmed: base });
    const diff = diffBoard(null, next);
    expect(diff.changedBlockIds.has("story_background")).toBe(true);
    expect(diff.changedBlockIds.has("must_include")).toBe(true);
  });
});

describe("锁定工具", () => {
  it("lock/unlock/isLocked", () => {
    let locked: string[] = [];
    locked = lockBlock(locked, "core_characters:红伞女人");
    expect(isLocked(locked, "core_characters:红伞女人")).toBe(true);
    locked = lockBlock(locked, "core_characters:红伞女人"); // 幂等
    expect(locked.length).toBe(1);
    locked = unlockBlock(locked, "core_characters:红伞女人");
    expect(isLocked(locked, "core_characters:红伞女人")).toBe(false);
  });
});

describe("writeBlockFields 写回 source", () => {
  it("confirmedField：写回字符串/列表字段", () => {
    const src = { story_background: "old", must_include: ["x"] };
    const out = writeBlockFields(src, { kind: "confirmedField", field: "story_background" }, [
      { key: "story_background", label: "故事背景", value: "new", type: "textarea" }
    ]);
    expect(out).toMatchObject({ story_background: "new" });
    expect(out).not.toBe(src); // 不可变
  });

  it("settingsScalar：写回 story_core.central_mystery", () => {
    const src = { story_core: { central_mystery: "old", main_goal: "g" } };
    const out = writeBlockFields(src, { kind: "settingsScalar", path: ["story_core", "central_mystery"] }, [
      { key: "central_mystery", label: "核心悬念", value: "new", type: "textarea" }
    ]);
    expect(out).toMatchObject({ story_core: { central_mystery: "new", main_goal: "g" } }); // 同级不丢
  });

  it("settingsStringList：写回 hard_rules.must_follow", () => {
    const src = { hard_rules: { must_follow: ["a"], must_not: ["b"] } };
    const out = writeBlockFields(src, { kind: "settingsStringList", path: ["hard_rules", "must_follow"] }, [
      { key: "must_follow", label: "必须遵守", value: ["a", "c"], type: "stringList" }
    ]);
    expect(out).toMatchObject({ hard_rules: { must_follow: ["a", "c"], must_not: ["b"] } });
  });

  it("settingsItem：按 idKey 定位数组项写回多字段", () => {
    const src = {
      core_characters: [
        { name: "主角", description: "d1" },
        { name: "红伞女人", description: "d2", role: "npc" }
      ]
    };
    const out = writeBlockFields(
      src,
      { kind: "settingsItem", arrayKey: "core_characters", idKey: "name", idValue: "红伞女人" },
      [
        { key: "name", label: "名称", value: "黑伞女人", type: "text" },
        { key: "description", label: "描述", value: "改了", type: "textarea" }
      ]
    );
    expect(out).toEqual({
      core_characters: [
        { name: "主角", description: "d1" }, // 其它项不动
        { name: "黑伞女人", description: "改了", role: "npc" } // 未列字段保留
      ]
    });
  });

  it("deleteBlock：settingsItem 删除数组项", () => {
    const src = { core_characters: [{ name: "a" }, { name: "b" }] };
    const out = deleteBlock(src, {
      kind: "settingsItem", arrayKey: "core_characters", idKey: "name", idValue: "a"
    });
    expect(out).toEqual({ core_characters: [{ name: "b" }] });
  });

  it("settingsScalar 整对象：path 长度1 时合并字段进对象", () => {
    const src = { game_profile: { title: "old", genre: "g" } };
    const out = writeBlockFields(src, { kind: "settingsScalar", path: ["game_profile"] }, [
      { key: "title", label: "标题", value: "new", type: "text" }
    ]);
    expect(out).toEqual({ game_profile: { title: "new", genre: "g" } });
  });
});

describe("block id 唯一性（防同名串台）", () => {
  it("同名机制/行动风格不产生重复 block.id（追加 #n）", () => {
    const settings = {
      core_mechanics: [
        { name: "战斗", rule: "a" },
        { name: "战斗", rule: "b" }
      ],
      action_style_rules: [
        { name: "战斗", rule: "c" },
        { name: "战斗", rule: "d" }
      ]
    };
    const model = buildBoardModel({ source: "settings", settings });
    const mech = model.categories.find((c) => c.id === "mechanics")!;
    const ids = mech.blocks.map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length); // 全唯一
    expect(ids).toEqual([
      "core_mechanics:战斗",
      "core_mechanics:战斗#2",
      "action_style_rules:战斗",
      "action_style_rules:战斗#2"
    ]);
  });
});
