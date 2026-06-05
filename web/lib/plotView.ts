// 剧情线主从视图的纯逻辑：把 BoardModel 派生成「纲领 / 幕(含节点) / 未分配节点」。
// 不依赖 React，便于 vitest 单测（与 generatorBoard.ts 同风格）。
import type { BoardBlock, BoardModel } from "@/lib/generatorBoard";

export type PlotAct = { actBlock: BoardBlock; nodes: BoardBlock[] };
export type PlotView = {
  overview: BoardBlock[];        // 纲领标量块（world 分类的 story_core.*）
  acts: PlotAct[];               // 幕，按 model 顺序，各自挂归属节点
  unassignedNodes: BoardBlock[]; // act_id 为空或指向不存在幕的孤儿节点
};

function fieldValue(block: BoardBlock, key: string): string {
  const f = block.fields.find((x) => x.key === key);
  if (f == null) return "";
  return typeof f.value === "string" ? f.value : f.value == null ? "" : String(f.value);
}

// 幕的稳定标识：settingsItem 地址的 idValue（= act.id 或 title）。
export function actKeyOf(actBlock: BoardBlock): string {
  return actBlock.address.kind === "settingsItem" ? actBlock.address.idValue : actBlock.id;
}

export function derivePlotView(model: BoardModel): PlotView {
  const world = model.categories.find((c) => c.id === "world");
  const plot = model.categories.find((c) => c.id === "plot");

  const overview = (world?.blocks ?? []).filter(
    (b) =>
      b.address.kind === "settingsScalar" &&
      b.address.path.length === 2 &&
      b.address.path[0] === "story_core"
  );

  const actBlocks = (plot?.blocks ?? []).filter(
    (b) => b.address.kind === "settingsItem" && b.address.arrayKey === "act_plan"
  );
  const nodeBlocks = (plot?.blocks ?? []).filter(
    (b) => b.address.kind === "settingsItem" && b.address.arrayKey === "main_quest_path"
  );

  const actKeys = new Set(actBlocks.map(actKeyOf));
  const acts: PlotAct[] = actBlocks.map((actBlock) => {
    const key = actKeyOf(actBlock);
    return {
      actBlock,
      nodes: nodeBlocks.filter((n) => fieldValue(n, "act_id") === key)
    };
  });
  const unassignedNodes = nodeBlocks.filter((n) => {
    const a = fieldValue(n, "act_id");
    return a === "" || !actKeys.has(a);
  });

  return { overview, acts, unassignedNodes };
}
