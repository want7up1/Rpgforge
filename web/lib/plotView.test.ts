import { describe, it, expect } from "vitest";
import { buildBoardModel } from "@/lib/generatorBoard";
import { derivePlotView, actKeyOf } from "@/lib/plotView";

const settings = {
  story_core: {
    premise: "占位前提",
    central_mystery: "占位悬念",
    must_preserve: ["占位红线"] // 这是 constraints 的 stringList，不应进 overview
  },
  act_plan: [
    { id: "act_1", title: "第一幕", objective: "目标一" },
    { id: "act_2", title: "第二幕", objective: "目标二" }
  ],
  main_quest_path: [
    { id: "q1", title: "节点一", objective: "o1", act_id: "act_1" },
    { id: "q2", title: "节点二", objective: "o2", act_id: "act_2" },
    { id: "q3", title: "孤儿", objective: "o3", act_id: "act_X" }
  ]
};

function view(s: Record<string, unknown>) {
  return derivePlotView(buildBoardModel({ source: "settings", settings: s }));
}

describe("derivePlotView", () => {
  it("纲领总览只含 story_core 标量（6 个），不含约束的 stringList", () => {
    const v = view(settings);
    expect(v.overview).toHaveLength(6); // 6 个标量块无条件建块
    const premise = v.overview.find((b) => b.fields[0]?.key === "premise");
    expect(premise?.fields[0]?.value).toBe("占位前提");
    // must_preserve 是 settingsStringList，不应出现
    expect(v.overview.some((b) => b.fields[0]?.key === "must_preserve")).toBe(false);
  });

  it("节点按 act_id 分组到对应幕", () => {
    const v = view(settings);
    expect(v.acts).toHaveLength(2);
    expect(actKeyOf(v.acts[0].actBlock)).toBe("act_1");
    expect(v.acts[0].nodes.map((n) => n.title)).toEqual(["节点一"]);
    expect(v.acts[1].nodes.map((n) => n.title)).toEqual(["节点二"]);
  });

  it("act_id 指向不存在的幕 → 进 unassignedNodes", () => {
    const v = view(settings);
    expect(v.unassignedNodes.map((n) => n.title)).toEqual(["孤儿"]);
  });

  it("空 settings：无幕无节点，纲领仍为 6 个占位空块", () => {
    const v = view({});
    expect(v.acts).toEqual([]);
    expect(v.unassignedNodes).toEqual([]);
    expect(v.overview).toHaveLength(6);
  });
});
