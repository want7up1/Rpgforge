import { afterEach, expect, it, vi } from "vitest";
import { clearTurnRequest, prepareTurnRequest, TurnMonitorScope } from "./turnRequest";
afterEach(() => vi.unstubAllGlobals());
it("同一未确认行动刷新或revision变化后仍复用请求ID", () => {
  const data = new Map<string, string>(); vi.stubGlobal("sessionStorage", { getItem: (k: string) => data.get(k), setItem: (k: string, v: string) => data.set(k, v), removeItem: (k: string) => data.delete(k) });
  const first = prepareTurnRequest("g", "同一行动", 3);
  expect(prepareTurnRequest("g", "同一行动", 4)).toEqual(first);
  clearTurnRequest("g"); expect(prepareTurnRequest("g", "同一行动", 4).requestId).not.toBe(first.requestId);
});
it("不同存档和不同新行动不共享请求号", () => {
  const data = new Map<string, string>(); vi.stubGlobal("sessionStorage", { getItem: (k: string) => data.get(k), setItem: (k: string, v: string) => data.set(k, v) });
  const first = prepareTurnRequest("g", "行动甲", 3);
  expect(prepareTurnRequest("g", "行动乙", 3).requestId).not.toBe(first.requestId);
  expect(prepareTurnRequest("h", "行动甲", 3).requestId).not.toBe(first.requestId);
});

it("提交尚在等待job详情时离开，迟到返回不能重新建立监听", async () => {
  const scope = new TurnMonitorScope(); const detach = scope.attach("old"); const request = scope.start("old")!;
  let release!: () => void; const response = new Promise<void>(resolve => { release = resolve; });
  const openStream = vi.fn();
  const continuation = (async () => { await response; if (scope.isCurrent("old", request)) openStream(); })();
  detach(); release(); await continuation;
  expect(request.signal.aborted).toBe(true); expect(openStream).not.toHaveBeenCalled(); expect(scope.start("old")).toBeUndefined();
});
it("切游戏后旧请求返回或旧cleanup不能终止新游戏监听", async () => {
  const scope = new TurnMonitorScope(); const cleanupOld = scope.attach("old"); const old = scope.start("old")!;
  scope.attach("new"); const current = scope.start("new")!; cleanupOld();
  expect(scope.isCurrent("old", old)).toBe(false); expect(scope.isCurrent("new", current)).toBe(true); expect(current.signal.aborted).toBe(false);
});
it("同游戏新尝试使旧请求失效，提交阶段和流阶段共用controller", () => {
  const scope = new TurnMonitorScope(); scope.attach("g"); const first = scope.start("g")!; const second = scope.start("g")!;
  expect(scope.isCurrent("g", first)).toBe(false); expect(first.signal.aborted).toBe(true); expect(scope.isCurrent("g", second)).toBe(true);
});
