import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { NarrativeInventory } from "@/components/NarrativeState";
import { getStateV2 } from "./stateV2";
it("状态页与手账共用物品呈现不会丢小数或单位", () => {
  const items = getStateV2({ inventory: [{ name: "药液", quantity: "0.5", unit: "ml" }, { name: "清水", quantity: 1, unit: "L" }, { item: "Knife", quantity: 2 }] }).inventory;
  const html = renderToStaticMarkup(createElement(NarrativeInventory, { items }));
  expect(html).toContain("×0.5 ml"); expect(html).toContain("×1 L"); expect(html).toContain("Knife"); expect(html).toContain("×2");
});
