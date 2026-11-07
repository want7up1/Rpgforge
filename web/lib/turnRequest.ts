export type TurnRequestAttempt = { gameId: string; action: string; requestId: string; revision?: number };
const key = (gameId: string) => `rpgforge.turn-request.${gameId}`;

/** 同一未确认行动在网络重试/刷新后复用请求号；收到完成或明确拒绝后才清除。 */
export function prepareTurnRequest(gameId: string, action: string, revision?: number): TurnRequestAttempt {
  try {
    const stored = JSON.parse(sessionStorage.getItem(key(gameId)) || "null") as TurnRequestAttempt | null;
    if (stored?.gameId === gameId && stored.action === action && typeof stored.requestId === "string") return stored;
  } catch { /* 隐私模式或旧记录不可读时仍可继续 */ }
  const attempt = { gameId, action, revision, requestId: globalThis.crypto?.randomUUID?.() ?? `turn-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}` };
  try { sessionStorage.setItem(key(gameId), JSON.stringify(attempt)); } catch { /* 不阻断行动 */ }
  return attempt;
}

export function clearTurnRequest(gameId: string): void {
  try { sessionStorage.removeItem(key(gameId)); } catch { /* 隐私模式 */ }
}

/** 挂载、请求准入和事件流共用同一生命周期，晚到的请求不能重开已离开的监听。 */
export class TurnMonitorScope {
  private gameId: string | null = null;
  private activation = 0;
  private controller: AbortController | null = null;

  attach(gameId: string): () => void {
    this.abort();
    this.gameId = gameId;
    const activation = ++this.activation;
    return () => {
      if (this.activation !== activation) return;
      this.gameId = null;
      this.abort();
    };
  }

  start(gameId: string): AbortController | undefined {
    if (!this.isGameActive(gameId)) return;
    this.abort();
    return this.controller = new AbortController();
  }

  isGameActive(gameId: string): boolean { return this.gameId === gameId; }
  isCurrent(gameId: string, controller: AbortController): boolean {
    return this.isGameActive(gameId) && this.controller === controller && !controller.signal.aborted;
  }
  abort(): void { this.controller?.abort(); }
}
