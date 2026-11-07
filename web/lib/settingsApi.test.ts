import { afterEach, expect, it, vi } from "vitest";
import { discoverModels, fetchGameEvaluations, fetchRecentTraces, fetchRecentTurnStats, fetchTraceDetail, fetchTurnJobTraces, triggerTurnEvaluation, updateDeepSeekSettings } from "./api";
afterEach(() => vi.unstubAllGlobals());
it("设置保存与模型发现不发送管理Token，发现请求可取消且不保存配置", async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ models: [{ id: "fixture" }], flash_model: "fixture", pro_model: "fixture" }), { status: 200 })); vi.stubGlobal("fetch", fetcher);
  const controller = new AbortController();
  await discoverModels({ base_url: "https://fixture.example/v1", api_key: "fixture-key" }, controller.signal);
  const [url, options] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/settings/deepseek/models"); expect(options.method).toBe("POST"); expect(options.signal).toBe(controller.signal);
  expect(new Headers(options.headers).has("X-Settings-Admin-Token")).toBe(false);
  expect(fetcher).toHaveBeenCalledTimes(1);
  await updateDeepSeekSettings({ task_model_routes: { gm_runtime: "pro" } });
  const [, update] = fetcher.mock.calls[1] as unknown as [string, RequestInit];
  expect(update.method).toBe("PATCH"); expect(new Headers(update.headers).has("X-Settings-Admin-Token")).toBe(false);
});
it("遥测、trace和评分查询保留功能且全部去除管理Token header", async () => {
  const fetcher = vi.fn(async () => new Response("[]", { status: 200 })); vi.stubGlobal("fetch", fetcher);
  await fetchRecentTurnStats(50); await fetchRecentTraces({ limit: 30 }); await fetchTraceDetail("trace"); await fetchTurnJobTraces("job"); await fetchGameEvaluations("game"); await triggerTurnEvaluation("turn");
  expect(fetcher).toHaveBeenCalledTimes(6);
  for (const args of fetcher.mock.calls) { const [, options] = args as unknown as [string, RequestInit]; expect(new Headers(options.headers).has("X-Settings-Admin-Token")).toBe(false); }
});
