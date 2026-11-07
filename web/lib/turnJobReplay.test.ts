import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ connect: vi.fn(), get: vi.fn() }));
vi.mock("@/lib/api", () => ({ createTurnJobEventSource: api.connect, getTurnJob: api.get, parseTurnJobStreamEvent: (event: MessageEvent) => JSON.parse(event.data) }));
import { createInitialTurnProcess, waitForTurnJobWithStream } from "./turnJobStream";
import type { TurnJobRead } from "./types";
class Source extends EventTarget { onerror = null; onopen = null; close = vi.fn(); emit(data: object) { const e = data as { type: string }; this.dispatchEvent(new MessageEvent(e.type, { data: JSON.stringify(data) })); } }
let source: Source;
beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal("window", new EventTarget()); vi.stubGlobal("document", Object.assign(new EventTarget(), { visibilityState: "visible" })); vi.stubGlobal("EventSource", Source); source = new Source(); api.connect.mockReturnValue(source); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const initial = (): TurnJobRead => ({ ...createInitialTurnProcess("g", "j", "running"), timeline_generation: 2, stream_revision: 1, event_seq: 10 });
it("固定流序列：重复、乱序、reset及短快照后最终正文准确", async () => {
  const snapshots: TurnJobRead[] = []; const promise = waitForTurnJobWithStream("g", "j", () => {}, job => snapshots.push(job), initial());
  const delta = { type: "delta", job_id: "j", timeline_generation: 2, stream_revision: 1, event_seq: 11, content_delta: "旧正文", narrative_buffer: "旧正文", content_length: 3 };
  source.emit(delta); source.emit(delta); source.emit({ ...delta, event_seq: 9 });
  source.emit({ ...delta, stream_revision: 2, event_seq: 12, reset_buffers: true, content_delta: "新😀", narrative_buffer: "新😀", content_length: 2 });
  source.emit({ type: "snapshot", job: { ...initial(), stream_revision: 3, event_seq: 13, content_buffer: "短", narrative_buffer: "短" } });
  source.emit({ ...delta, timeline_generation: 1, stream_revision: 90, event_seq: 200 });
  source.emit({ type: "completed", job: { ...initial(), status: "completed", stream_revision: 3, event_seq: 14, content_buffer: "最终", narrative_buffer: "最终" } });
  expect((await promise).narrative_buffer).toBe("最终");
  expect(snapshots.map(job => job.narrative_buffer)).toEqual(["", "旧正文", "新😀", "短", "最终"]);
});
it("缺失分片触发一次快照轮询，不展示断裂的增量文本", async () => {
  const snapshots: TurnJobRead[] = []; const final = { ...initial(), status: "completed" as const, event_seq: 30, content_buffer: "完整正文", narrative_buffer: "完整正文" }; api.get.mockResolvedValue(final);
  const promise = waitForTurnJobWithStream("g", "j", () => {}, job => snapshots.push(job), initial());
  source.emit({ type: "delta", stream_revision: 1, event_seq: 20, content_delta: "文", content_length: 4, narrative_buffer: "完整正文" });
  await vi.advanceTimersByTimeAsync(1500);
  expect((await promise).narrative_buffer).toBe("完整正文"); expect(snapshots).toHaveLength(2); expect(api.get).toHaveBeenCalledTimes(1);
});

it("权威failed终态通知UI并关闭连接，允许清除原请求进入新尝试", async () => {
  const snapshots: TurnJobRead[] = [];
  const promise = waitForTurnJobWithStream("g", "j", () => {}, job => snapshots.push(job), initial());
  const rejected = expect(promise).rejects.toThrow("模型调用失败");
  source.emit({ type: "failed", job: { ...initial(), event_seq: 11, status: "failed", error_message: "模型调用失败" } });
  await rejected;
  expect(snapshots.at(-1)?.status).toBe("failed");
  expect(source.close).toHaveBeenCalled();
  expect(api.get).not.toHaveBeenCalled();
});

it("崩溃后DB终态seq落后已发送帧：SSE旧帧仍拒绝，直接GET终态可恢复", async () => {
  const snapshots: TurnJobRead[] = []; const running = { ...initial(), event_seq: 100 };
  const failed = { ...running, status: "failed" as const, event_seq: 81, error_message: "进程中断" }; api.get.mockResolvedValue(failed);
  const promise = waitForTurnJobWithStream("g", "j", () => {}, job => snapshots.push(job), running);
  const rejected = expect(promise).rejects.toThrow("进程中断");
  source.emit({ type: "failed", job: failed }); expect(snapshots).toHaveLength(1);
  (source as unknown as EventSource).onerror?.(new Event("error"));
  await vi.advanceTimersByTimeAsync(5500); await rejected;
  expect(snapshots.at(-1)?.status).toBe("failed"); expect(api.get).toHaveBeenCalledTimes(1); expect(vi.getTimerCount()).toBe(0);
});
it("直接GET的低序号终态仍不能覆盖更新的时间线", async () => {
  const snapshots: TurnJobRead[] = []; const running = { ...initial(), timeline_generation: 3, event_seq: 100 };
  api.get.mockResolvedValue({ ...running, timeline_generation: 2, status: "failed", event_seq: 81, error_message: "旧时间线" });
  const controller = new AbortController();
  const promise = waitForTurnJobWithStream("g", "j", () => {}, job => snapshots.push(job), running, controller.signal);
  (source as unknown as EventSource).onopen?.(new Event("open")); await Promise.resolve(); await Promise.resolve();
  expect(snapshots).toHaveLength(1);
  const rejected = expect(promise).rejects.toMatchObject({ name: "AbortError" }); controller.abort(); await rejected;
});
