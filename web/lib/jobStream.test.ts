import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamCursor, waitForJobStream } from "./jobStream";
class FakeSource extends EventTarget {
  onopen: (() => void) | null = null; onerror: (() => void) | null = null; close = vi.fn();
  emit(type: string, data = "{}") { this.dispatchEvent(new MessageEvent(type, { data })); }
}
let doc: EventTarget & { visibilityState: string }; let win: EventTarget;
beforeEach(() => { vi.useFakeTimers(); doc = Object.assign(new EventTarget(), { visibilityState: "visible" }); win = new EventTarget(); vi.stubGlobal("document", doc); vi.stubGlobal("window", win); vi.stubGlobal("EventSource", FakeSource); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
function fixture(overrides: Partial<Parameters<typeof waitForJobStream<string>>[0]> = {}) {
  const sources: FakeSource[] = []; const poll = vi.fn(async () => "polled"); const refresh = vi.fn(async () => undefined); const onFallback = vi.fn();
  const apply = vi.fn((event: MessageEvent) => event.data === "done" ? { done: "streamed" } : undefined); const controller = new AbortController();
  const promise = waitForJobStream<string>({ connect: () => { const s = new FakeSource(); sources.push(s); return s as unknown as EventSource; }, eventNames: ["snapshot", "heartbeat", "completed"], apply, poll, refresh, onFallback, label: "实时剧情", signal: controller.signal, ...overrides });
  return { sources, poll, refresh, onFallback, apply, controller, promise };
}
describe("任务流连接恢复", () => {
  it("终态先于错误降级时只完成一次并清除定时器", async () => {
    const f = fixture(); f.sources[0].emit("snapshot"); f.sources[0].onerror?.(); f.sources[0].emit("completed", "done");
    expect(await f.promise).toBe("streamed"); await vi.advanceTimersByTimeAsync(120_000); expect(f.poll).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
  it("静默失活重建，旧连接迟到帧不能结束新连接", async () => {
    const f = fixture(); f.sources[0].onopen?.(); f.sources[0].emit("heartbeat"); await vi.advanceTimersByTimeAsync(90_000);
    expect(f.sources).toHaveLength(2); f.sources[0].emit("completed", "done"); expect(f.apply).toHaveBeenCalledTimes(1);
    f.sources[1].onopen?.(); f.sources[1].emit("completed", "done"); expect(await f.promise).toBe("streamed"); expect(f.refresh).toHaveBeenCalledTimes(2);
  });
  it("回前台、网络恢复和bfcache均重连，隐藏期间不重连", async () => {
    const f = fixture(); doc.visibilityState = "hidden"; doc.dispatchEvent(new Event("visibilitychange")); expect(f.sources).toHaveLength(1);
    doc.visibilityState = "visible"; doc.dispatchEvent(new Event("visibilitychange")); win.dispatchEvent(new Event("online")); win.dispatchEvent(Object.assign(new Event("pageshow"), { persisted: true }));
    expect(f.sources).toHaveLength(4); f.sources[3].emit("completed", "done"); await f.promise; win.dispatchEvent(new Event("online")); expect(f.sources).toHaveLength(4);
  });
  it("解析失败只启动一次轮询", async () => {
    const f = fixture({ apply: () => { throw new Error("bad JSON"); } }); f.sources[0].emit("snapshot"); f.sources[0].emit("snapshot"); f.sources[0].onerror?.();
    expect(await f.promise).toBe("polled"); expect(f.poll).toHaveBeenCalledTimes(1); expect(f.onFallback).toHaveBeenCalledTimes(1);
  });
  it("取消关闭连接且停止处理迟到事件", async () => {
    const f = fixture(); const cancelled = expect(f.promise).rejects.toMatchObject({ name: "AbortError" }); f.controller.abort(); await cancelled;
    f.sources[0].emit("completed", "done"); win.dispatchEvent(new Event("online")); expect(f.apply).not.toHaveBeenCalled(); expect(f.sources).toHaveLength(1); expect(f.sources[0].close).toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
  it("重连重拉恢复漏掉的完成帧", async () => {
    const f = fixture({ refresh: async () => ({ done: "recovered" }) }); f.sources[0].onopen?.(); expect(await f.promise).toBe("recovered"); expect(f.poll).not.toHaveBeenCalled();
  });
});
describe("版本游标", () => {
  it("拒绝重复倒序帧，接受新版本，不接纳旧时间线", () => {
    const c = new StreamCursor();
    expect(c.accept({ timeline_generation: 4, stream_revision: 0, event_seq: 8 })).toBe(true);
    expect(c.accept({ timeline_generation: 4, stream_revision: 0, event_seq: 8 })).toBe(false);
    expect(c.accept({ timeline_generation: 4, stream_revision: 0, event_seq: 7 })).toBe(false);
    expect(c.accept({ timeline_generation: 4, stream_revision: 1, event_seq: 1 })).toBe(true);
    expect(c.accept({ timeline_generation: 4, stream_revision: 0, event_seq: 99 })).toBe(false);
    expect(c.accept({ timeline_generation: 5, stream_revision: 0, event_seq: 1 })).toBe(true);
    expect(c.accept({ timeline_generation: 4, stream_revision: 99, event_seq: 999 })).toBe(false);
  });
  it("旧接口缺少版本字段仍可读取", () => { const c = new StreamCursor(); expect(c.accept({})).toBe(true); expect(c.accept({})).toBe(true); });
});
