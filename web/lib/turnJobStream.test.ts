import { describe, expect, it } from "vitest";
import { createInitialTurnProcess, mergeTurnJobSnapshot } from "./turnJobStream";
describe("回合流快照", () => {
  const base = () => ({ ...createInitialTurnProcess("g", "j", "running"), stream_revision: 2, event_seq: 10, timeline_generation: 3, reasoning_content: "旧推理很长", content_buffer: "旧正文很长", narrative_buffer: "旧叙事很长" });
  it("同版本滞后快照保留已接收缓冲", () => { const a = base(); expect(mergeTurnJobSnapshot(a, { ...a, narrative_buffer: "旧" }).narrative_buffer).toBe(a.narrative_buffer); });
  it("新版本接受更短正文，不拼接旧正文", () => { const a = base(); const b = mergeTurnJobSnapshot(a, { ...a, stream_revision: 3, reasoning_content: "新", content_buffer: "新", narrative_buffer: "新" }); expect(b.narrative_buffer).toBe("新"); expect(b.reasoning_content).toBe("新"); });
  it("终态使用最终清理后的短正文", () => { const a = base(); expect(mergeTurnJobSnapshot(a, { ...a, status: "completed", narrative_buffer: "最终" }).narrative_buffer).toBe("最终"); });
});
