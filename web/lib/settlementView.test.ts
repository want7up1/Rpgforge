import { expect, it } from "vitest";
import { buildTurnSettlement } from "./gameExperience";
import { getStateV2 } from "./stateV2";
import type { SettlementReceipt, TurnRead } from "./types";
const turn = (extra: Partial<TurnRead> = {}): TurnRead => ({ id: "t", game_id: "g", turn_number: 3, player_input: "行动", gm_output: "正文", visible_summary: null, hidden_summary: null, state_delta_json: {}, action_options_json: [], model_used: null, created_at: "", ...extra });
it("展示实际回执进度，不把原始申请当已生效", () => {
  const result = buildTurnSettlement(turn({ state_delta_json: { relationship_events: [{ npc: "不应出现", status: "成功" }] }, settlement_receipt: { version: 1, status: "confirmed", turn_number: 3, sections: [{ key: "progress", label: "主线进展", changes: [{ subject: "找到证人", before: "未完成", after: "已完成", reason: "证人交出信件" }] }] } }));
  expect(result.status).toBe("confirmed"); expect(result.summary.join()).toContain("找到证人"); expect(result.summary.join()).not.toContain("不应出现");
});
it("待整理不展示申请成功；旧档保留信息并标记未核验", () => {
  const delta = { inventory_add: [{ name: "钥匙" }] }; const pending = buildTurnSettlement(turn({ state_delta_json: delta, settlement_receipt: { version: 1, status: "pending", turn_number: 3, sections: [] } }));
  expect(pending.hasChanges).toBe(false); expect(pending.status).toBe("pending"); const legacy = buildTurnSettlement(turn({ state_delta_json: delta })); expect(legacy.status).toBe("legacy"); expect(legacy.summary.join()).toContain("钥匙");
});
it("兼容旧物品字符串，新数量和隐藏状态投影", () => {
  const state = getStateV2({ inventory: ["信件", { name: "钥匙", quantity: 2 }, { name: "秘密", visibility: "hidden" }, { name: "已用完", quantity: 0 }], conditions: [{ name: "伤口" }, { name: "隐患", visibility: "hidden" }], relationships: [{ npc: "甲", status: "合作" }, { npc: "乙", visibility: "secret" }] });
  expect(state.inventory.map(i => i.name)).toEqual(["信件", "钥匙"]); expect(state.conditions.map(i => i.name)).toEqual(["伤口"]); expect(state.relationship_tracks.map(i => i.npc)).toEqual(["甲"]);
});
it("v2优先，旧档缺物品不虚构清单", () => { const state = getStateV2({ story_progress: { current_act: "old" }, v2: { story_progress: { current_act: "new" } } }); expect(state.story_progress.current_act).toBe("new"); expect(state.inventory).toEqual([]); });

it("兼容旧尾声只写入根状态，保持其它v2字段的既有优先级", () => {
  const state = getStateV2({ story_progress: { current_act: "old", epilogue: "正式尾声" }, v2: { story_progress: { current_act: "new", epilogue: "" } } });
  expect(state.story_progress.current_act).toBe("new");
  expect(state.story_progress.epilogue).toBe("正式尾声");
});

it("变化原因已包含在实际结果中时不重复显示", () => {
  const result = buildTurnSettlement(turn({ settlement_receipt: { version: 1, status: "confirmed", turn_number: 3, sections: [{ key: "relationship", label: "关系", changes: [{ subject: "林岚", before: "戒备", after: "愿意合作 · 兑现了承诺", reason: "兑现了承诺" }] }] } }));
  expect(result.summary[0].match(/兑现了承诺/g)).toHaveLength(1);
});

it("数据库默认空JSON回执按真实旧档兼容，保留历史delta且不宣称已核验", () => {
  const result = buildTurnSettlement(turn({ settlement_receipt: {} as SettlementReceipt, state_delta_json: { inventory_add: [{ name: "历史钥匙" }] } }));
  expect(result.status).toBe("legacy");
  expect(result.summary.join()).toContain("历史钥匙");
  expect(result.message).toContain("尚未核验");
});
it("未知版本或缺sections的历史回执不会使游戏页崩溃", () => {
  for (const receipt of [{ version: 1, status: "confirmed" }, { version: 2, status: "confirmed", sections: [] }, { version: 1, status: "unknown", sections: [] }]) {
    expect(buildTurnSettlement(turn({ settlement_receipt: receipt as unknown as SettlementReceipt })).status).toBe("legacy");
  }
});

it("无v2旧物品item别名和小数数量/单位原样保留", () => {
  const state = getStateV2({ inventory: [{ item: "Knife", quantity: 2 }, { name: "药液", quantity: "0.5", unit: "ml" }, { name: "水", qty: 0.25, unit: "L" }, { name: "数字字符串", quantity: "2" }] });
  expect(state.inventory.map(item => [item.name, item.quantity, item.unit])).toEqual([["Knife", 2, ""], ["药液", 0.5, "ml"], ["水", 0.25, "L"], ["数字字符串", 2, ""]]);
});
it("非法数量不变造为零或一，不影响仍有效的物品文字", () => {
  const state = getStateV2({ inventory: [{ name: "空数量", quantity: "" }, { name: "非数字", quantity: "NaN" }, { name: "负数", quantity: -1 }, { name: "无限", quantity: Infinity }] });
  expect(state.inventory).toHaveLength(4);
  expect(state.inventory.every(item => item.quantity === undefined)).toBe(true);
});
it("所有私有可见性别名统一从物品/处境/关系/NPC/任务/线索玩家投影过滤", () => {
  const aliases = ["hidden", "secret", "unknown", "gm", "gm_only", "director", "director_only", "internal", "private", "隐藏", "秘密", "未知", "幕后", "主持人", " GM_ONLY "];
  for (const visibility of aliases) {
    const state = getStateV2({ inventory: [{ item: "秘密物品", visibility }], conditions: [{ name: "秘密处境", visibility }], relationships: [{ npc: "秘密关系", visibility }], npcs: [{ name: "秘密NPC", visibility }], quests: [{ name: "秘密任务", visibility }], open_threads: [{ title: "秘密线索", visibility }] });
    expect([state.inventory, state.conditions, state.relationship_tracks, state.npc_registry, state.quest_log.active, state.open_threads.active].map(list => list.length)).toEqual([0, 0, 0, 0, 0, 0]);
  }
});
it("可见任务/线索/NPC保留visibility，隐藏任务桶不下发给玩家", () => {
  const state = getStateV2({ v2: { npc_registry: [{ name: "甲", visibility: "visible" }], quest_log: { active: [{ name: "已知任务", visibility: "known" }], hidden: [{ name: "未揭示任务" }] }, open_threads: { active: [{ title: "信件", visibility: "public" }] } } });
  expect(state.npc_registry[0].visibility).toBe("visible"); expect(state.quest_log.active[0].visibility).toBe("known"); expect(state.open_threads.active[0].visibility).toBe("public"); expect(state.quest_log.hidden).toEqual([]);
});
it("旧delta变化摘要同样过滤中文和主持人专用私有条目", () => {
  const result = buildTurnSettlement(turn({ state_delta_json: { inventory_add: [{ name: "秘密", visibility: "隐藏" }, { name: "机密", visibility: "gm_only" }, { name: "可见" }] } }));
  expect(result.summary.join()).toContain("可见"); expect(result.summary.join()).not.toContain("秘密"); expect(result.summary.join()).not.toContain("机密");
});

it("先从完整NPC登记收集隐藏名，再过滤在场、同行和登记玩家视图", () => {
  const state = getStateV2({ v2: { npc_registry: [{ name: "影子", aliases: ["暗影"], visibility: "director_only" }, { name: "同伴", visibility: "known" }], party: ["影子", "同伴"], active_scene: { present_npcs: ["暗影", "影子", "同伴"] } } });
  expect(state.npc_registry.map(npc => npc.name)).toEqual(["同伴"]);
  expect(state.party).toEqual(["同伴"]);
  expect(state.active_scene.present_npcs).toEqual(["同伴"]);
});
it("旧档根NPC登记里的中文隐藏名同样不从在场或同行泄露", () => {
  const state = getStateV2({ npcs: [{ name: "未登场者", visibility: "幕后" }, { name: "已知者" }], party: ["未登场者", "已知者"], v2: { active_scene: { present_npcs: ["未登场者", "已知者"] } } });
  expect(state.party).toEqual(["已知者"]); expect(state.active_scene.present_npcs).toEqual(["已知者"]);
});
