"use client";

import { memo } from "react";
import type { InventoryItem, StateV2 } from "@/lib/stateV2";

/** 常驻只放影响阅读和下一步选择的处境；完整记录在手账与状态页。 */
export const NarrativeStatusStrip = memo(function NarrativeStatusStrip({ state, onOpen }: { state: StateV2; onOpen: () => void }) {
  const conditions = state.conditions.slice(0, 2).map(item => [item.name, item.status === "active" ? "" : item.status].filter(Boolean).join("："));
  const items = state.inventory.slice(0, 2).map(item => item.name);
  if (!conditions.length && !state.party.length && !items.length) return null;
  return <button aria-label="查看当前状态摘要和手账" className="flex w-full flex-wrap gap-x-4 gap-y-1 border-b-2 border-[color:var(--border)] bg-[color:var(--panel)] px-3 py-2 text-left text-xs text-[color:var(--muted)]" onClick={onOpen} type="button">
    {conditions.length ? <span>处境：{conditions.join("；")}</span> : null}
    {state.party.length ? <span>同行：{state.party.join("、")}</span> : null}
    {items.length ? <span>携带：{items.join("、")}</span> : null}
  </button>;
});

export function NarrativeInventory({ items }: { items: InventoryItem[] }) {
  return items.length ? <ul className="mt-3 grid gap-2 text-sm">{items.map(item => <li key={`${item.name}:${item.unit ?? ""}`}>
    <strong>{item.name}</strong>{item.quantity !== undefined && (item.quantity !== 1 || item.unit) ? ` ×${item.quantity}${item.unit ? ` ${item.unit}` : ""}` : ""}
    {item.description ? <p className="mt-1 text-xs text-[color:var(--muted)]">{item.description}</p> : null}
  </li>)}</ul> : <p className="mt-3 text-sm text-[color:var(--muted)]">暂无已记录的随身物品。</p>;
}
