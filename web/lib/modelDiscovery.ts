import type { DeepSeekSettingsRead, ModelDiscoveryRead } from "@/lib/types";

export type ModelSelection = { flash: string; pro: string };
export const normalizedModelBaseUrl = (value: string) => value.trim().replace(/\/+$/, "") || "https://api.deepseek.com";

export function modelProbeReadiness(baseUrl: string, apiKey: string, saved: DeepSeekSettingsRead, clearKey = false): { ready: boolean; message: string } {
  if (clearKey) return { ready: false, message: "已选择清空 Key，暂停模型探测。" };
  let url: URL;
  try { url = new URL(normalizedModelBaseUrl(baseUrl)); }
  catch { return { ready: false, message: "请填写完整的模型服务 Base URL。" }; }
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return { ready: false, message: "Base URL 需为不含账号密码的 HTTP 或 HTTPS 地址。" };
  if (!apiKey.trim() && !saved.api_key_configured) return { ready: false, message: "填写 API Key 后将自动探测模型。" };
  if (!apiKey.trim()) {
    let savedOrigin: string;
    try { savedOrigin = new URL(normalizedModelBaseUrl(saved.base_url)).origin; }
    catch { return { ready: false, message: "请填写该服务的 API Key 后再探测。" }; }
    if (url.origin !== savedOrigin) return { ready: false, message: "服务地址已切换，请填写该服务的 API Key 后再探测。" };
  }
  return { ready: true, message: "输入完成后会自动探测模型，也可立即重新探测。" };
}

export function selectDiscoveredModels(result: ModelDiscoveryRead, selected: ModelSelection): { models: string[]; flash: string; pro: string } {
  const models = [...new Set(result.models.map(model => model.id.trim()).filter(Boolean))];
  const choose = (current: string, recommended: string | null) => models.includes(current) ? current : recommended && models.includes(recommended) ? recommended : models[0] || "";
  return { models, flash: choose(selected.flash, result.flash_model), pro: choose(selected.pro, result.pro_model) };
}

export function canSaveModelDraft(saved: DeepSeekSettingsRead, draft: { baseUrl: string; apiKey: string; flash: string; pro: string }, discovery: { current: boolean; models: string[] }): boolean {
  if (!draft.flash.trim() || !draft.pro.trim()) return false;
  const unchangedProvider = normalizedModelBaseUrl(saved.base_url) === normalizedModelBaseUrl(draft.baseUrl) && !draft.apiKey.trim();
  if (unchangedProvider && draft.flash === saved.flash_model && draft.pro === saved.pro_model) return true;
  return discovery.current && discovery.models.includes(draft.flash) && discovery.models.includes(draft.pro);
}

/** 输入、取消、重试与离页都使旧请求失效，响应乱序不会覆盖新服务的模型列表。 */
export class ModelProbeSession {
  private generation = 0;
  private controller: AbortController | null = null;
  cancel(): void { this.generation++; this.controller?.abort(); }
  start(): { signal: AbortSignal; isCurrent: () => boolean; cancel: () => void } {
    this.cancel();
    const generation = this.generation;
    const controller = this.controller = new AbortController();
    return { signal: controller.signal, isCurrent: () => generation === this.generation && !controller.signal.aborted, cancel: () => controller.abort() };
  }
}
