/** SSE 只负责连接生命周期；快照/增量与终态含义留给各业务。 */
export type StreamResult<T> = { done: T } | { error: Error } | undefined;

type StreamOptions<T> = {
  connect: () => EventSource;
  eventNames: readonly string[];
  apply: (event: MessageEvent) => StreamResult<T>;
  refresh: () => Promise<StreamResult<T>>;
  poll: () => Promise<T>;
  onFallback: (message: string) => void;
  label: string;
  signal?: AbortSignal;
};

export function waitForJobStream<T>(options: StreamOptions<T>): Promise<T> {
  const { signal } = options;
  if (signal?.aborted) return Promise.reject(abortError());
  if (typeof window === "undefined" || typeof EventSource === "undefined") return options.poll();

  return new Promise<T>((resolve, reject) => {
    let source: EventSource | null = null;
    let connectTimer: ReturnType<typeof setTimeout> | undefined;
    let errorTimer: ReturnType<typeof setTimeout> | undefined;
    let settled = false;
    let polling = false;
    let lastBeat = Date.now();
    let received = false;
    const clearTimers = () => {
      clearTimeout(connectTimer);
      clearTimeout(errorTimer);
      connectTimer = errorTimer = undefined;
    };
    const cleanup = () => {
      settled = true;
      clearTimers();
      clearInterval(watchdog);
      source?.close();
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("online", resume);
      window.removeEventListener("pageshow", pageShow);
      signal?.removeEventListener("abort", abort);
    };
    const finish = (result: StreamResult<T>) => {
      if (settled || !result) return;
      cleanup();
      if ("error" in result) reject(result.error);
      else resolve(result.done);
    };
    const abort = () => finish({ error: abortError() });
    const fallback = (reason: string) => {
      if (settled || polling) return;
      polling = true;
      clearTimers();
      source?.close();
      options.onFallback(`${options.label}${reason}，已切换为轮询确认任务状态。`);
      void options.poll().then(done => finish({ done }), error => finish({ error: asError(error) }));
    };
    const connect = () => {
      if (settled || polling) return;
      clearTimers();
      source?.close();
      lastBeat = Date.now();
      try {
        const current = options.connect();
        source = current;
        const active = () => !settled && !polling && source === current;
        current.onopen = () => {
          if (!active()) return;
          lastBeat = Date.now();
          // 每次重连都读取权威快照，补齐锁屏/断网时漏掉的终态。
          void options.refresh().then(result => {
            if (active()) finish(result);
          }).catch(() => { if (active()) fallback("状态同步失败"); });
        };
        const onFrame = (event: Event) => {
          if (!active()) return;
          received = true;
          lastBeat = Date.now();
          clearTimers();
          try {
            finish(options.apply(event as MessageEvent));
          } catch {
            fallback("事件解析失败");
          }
        };
        for (const name of options.eventNames) current.addEventListener(name, onFrame);
        current.onerror = () => {
          if (!active() || errorTimer !== undefined) return;
          errorTimer = setTimeout(() => fallback("连接中断"), received ? 4000 : 1500);
        };
        connectTimer = setTimeout(() => fallback("连接超时"), 6000);
      } catch {
        fallback("连接失败");
      }
    };
    const resume = () => { if (document.visibilityState !== "hidden") connect(); };
    const pageShow = (event: PageTransitionEvent) => { if (event.persisted) resume(); };
    const watchdog = setInterval(() => {
      if (document.visibilityState !== "hidden" && Date.now() - lastBeat > 60_000) connect();
    }, 30_000);
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    window.addEventListener("pageshow", pageShow);
    signal?.addEventListener("abort", abort, { once: true });
    connect();
  });
}

export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(abortError()); return; }
    const abort = () => { clearTimeout(timer); reject(abortError()); };
    const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, ms);
    signal?.addEventListener("abort", abort, { once: true });
  });
}

export function formatLastEvent(value: string | null): string {
  if (!value) return "暂无";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "未知";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  return seconds < 2 ? "刚刚" : seconds < 60 ? `${seconds} 秒前` : `${Math.floor(seconds / 60)} 分钟前`;
}

export function abortError(): Error {
  return new DOMException("已停止监视此任务。", "AbortError");
}

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

export type StreamVersion = {
  timeline_generation?: number;
  stream_revision?: number;
  event_seq?: number;
};

/** 不以文本长度冒充版本；重写/重试可合法地产生更短的新正文。 */
export class StreamCursor {
  private version: StreamVersion;
  constructor(initial: StreamVersion = {}) { this.version = { ...initial }; }
  accept(incoming: StreamVersion): boolean {
    for (const key of ["timeline_generation", "stream_revision", "event_seq"] as const) {
      const next = incoming[key];
      const current = this.version[key];
      if (next === undefined) continue; // 旧服务端兼容
      if (current === undefined || next > current) {
        this.version = key === "timeline_generation" ? { ...incoming }
          : key === "stream_revision" ? { ...this.version, ...incoming, event_seq: incoming.event_seq }
          : { ...this.version, ...incoming };
        return true;
      }
      if (next < current) return false;
    }
    if (incoming.event_seq !== undefined && incoming.event_seq > 0 && incoming.event_seq === this.version.event_seq) return false;
    this.version = { ...this.version, ...incoming };
    return true;
  }
}
