import { expect, it } from "vitest";
import { canSaveModelDraft, modelProbeReadiness, ModelProbeSession, normalizedModelBaseUrl, selectDiscoveredModels } from "./modelDiscovery";
import type { DeepSeekSettingsRead } from "./types";
const saved: DeepSeekSettingsRead = { base_url: "https://old.example/v1", api_key_configured: true, api_key_masked: "masked", api_key_source: "database", flash_model: "old-fast", pro_model: "old-pro", task_model_routes: {}, settings_protected: false };
it("模型列表去重，优先保留有效已选模型，其次采用服务端推荐", () => {
  const result = selectDiscoveredModels({ models: [{ id: "fast" }, { id: "pro" }, { id: "fast" }], flash_model: "fast", pro_model: "pro" }, { flash: "pro", pro: "gone" });
  expect(result).toEqual({ models: ["fast", "pro"], flash: "pro", pro: "pro" });
});
it("单个模型可同时填入两个槽位，未知推荐不虚构模型ID", () => {
  expect(selectDiscoveredModels({ models: [{ id: "single" }], flash_model: null, pro_model: "missing" }, { flash: "", pro: "" })).toEqual({ models: ["single"], flash: "single", pro: "single" });
});
it("无Key时可用已保存Key，同源路径切换仍可探测", () => {
  expect(modelProbeReadiness("https://old.example/v2", "", saved).ready).toBe(true);
  expect(modelProbeReadiness("https://new.example/v1", "", saved)).toMatchObject({ ready: false, message: expect.stringContaining("填写该服务") });
  expect(modelProbeReadiness("https://new.example/v1", "fixture-key", saved).ready).toBe(true);
});
it("缺少Key、清Key、无效地址均不触发自动探测", () => {
  expect(modelProbeReadiness(saved.base_url, "", { ...saved, api_key_configured: false }).ready).toBe(false);
  expect(modelProbeReadiness(saved.base_url, "", saved, true).ready).toBe(false);
  expect(modelProbeReadiness("not a url", "fixture-key", saved).ready).toBe(false);
  expect(modelProbeReadiness("https://user:pass@example.com", "fixture-key", saved).ready).toBe(false);
});
it("空的已保存地址填充为同一个官方默认地址", () => {
  expect(normalizedModelBaseUrl("")).toBe("https://api.deepseek.com");
  expect(modelProbeReadiness("https://api.deepseek.com", "", { ...saved, base_url: "" }).ready).toBe(true);
});
it("旧配置尚未探测也能仅改职责或清Key保存，不强迫重选旧模型", () => {
  expect(canSaveModelDraft(saved, { baseUrl: saved.base_url + "/", apiKey: "", flash: saved.flash_model, pro: saved.pro_model }, { current: false, models: [] })).toBe(true);
});
it("更换服务或Key后，旧列表不可保存；当前探测的两个有效选项才可保存", () => {
  const draft = { baseUrl: "https://new.example/v1", apiKey: "fixture-key", flash: "fast", pro: "pro" };
  expect(canSaveModelDraft(saved, draft, { current: false, models: ["fast", "pro"] })).toBe(false);
  expect(canSaveModelDraft(saved, draft, { current: true, models: ["fast"] })).toBe(false);
  expect(canSaveModelDraft(saved, draft, { current: true, models: ["fast", "pro"] })).toBe(true);
  expect(canSaveModelDraft(saved, { ...draft, baseUrl: saved.base_url }, { current: false, models: ["fast", "pro"] })).toBe(false);
});
it("输入变化、取消与离页使晚到的模型结果失效", async () => {
  const session = new ModelProbeSession(); const old = session.start();
  let release!: () => void; const pending = new Promise<void>(resolve => { release = resolve; }); let applied = false;
  const late = (async () => { await pending; if (old.isCurrent()) applied = true; })();
  const latest = session.start(); release(); await late;
  expect(old.signal.aborted).toBe(true); expect(applied).toBe(false); expect(latest.isCurrent()).toBe(true);
  session.cancel(); expect(latest.isCurrent()).toBe(false);
});
