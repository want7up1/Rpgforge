"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import {
  fetchGameEvaluations,
  fetchRecentTraces,
  fetchRecentTurnStats,
  fetchTraceDetail,
  type AgentTraceDetail,
  type AgentTraceSummary,
  type RecentTurnStats,
  type TurnEvaluationRead
} from "@/lib/api";

// 与 /settings 页面共用同一个 token，方便用户只配一次。
const adminTokenStorageKey = "rpgforge.settingsAdminToken";

type LoadState = "idle" | "loading" | "ok" | "error";

export default function AdminPage() {
  // lazy initializer 从 localStorage 读，避免在 effect 内同步 setState。
  const initialToken =
    typeof window === "undefined" ? "" : localStorage.getItem(adminTokenStorageKey) ?? "";
  const [token, setToken] = useState<string>(initialToken);
  const [tokenInput, setTokenInput] = useState<string>(initialToken);
  const [stats, setStats] = useState<RecentTurnStats | null>(null);
  const [traces, setTraces] = useState<AgentTraceSummary[]>([]);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string>("");
  const [limit, setLimit] = useState<number>(100);
  // 手动刷新的计数器：bump 一下触发重新加载。
  const [reloadTick, setReloadTick] = useState(0);
  // trace 详情面板
  const [detail, setDetail] = useState<AgentTraceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  // 评分查询
  const [evalGameId, setEvalGameId] = useState("");
  const [evals, setEvals] = useState<TurnEvaluationRead[]>([]);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState("");

  // 加载逻辑放进 effect 内部的 async 函数，所有 setState 都在 await 之后，
  // 避免 react-hooks/set-state-in-effect 警告。
  useEffect(() => {
    if (!token) {
      return;
    }
    const controller = new AbortController();

    async function load(currentToken: string) {
      try {
        const [statsData, traceData] = await Promise.all([
          fetchRecentTurnStats(currentToken, limit),
          fetchRecentTraces(currentToken, { limit: 30 })
        ]);
        if (controller.signal.aborted) return;
        setStats(statsData);
        setTraces(traceData);
        setState("ok");
        setError("");
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setState("error");
      }
    }

    void load(token);
    return () => controller.abort();
  }, [token, limit, reloadTick]);

  function handleSaveToken() {
    if (typeof window === "undefined") return;
    const trimmed = tokenInput.trim();
    localStorage.setItem(adminTokenStorageKey, trimmed);
    setToken(trimmed);
  }

  function handleRefresh() {
    if (!token) {
      setError("请先在下方填写并保存管理 Token。");
      setState("error");
      return;
    }
    setReloadTick((n) => n + 1);
  }

  async function handleOpenTrace(traceId: string) {
    if (!token) return;
    setDetailLoading(true);
    setDetailError("");
    setDetail(null);
    try {
      const data = await fetchTraceDetail(token, traceId);
      setDetail(data);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err));
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleLoadEvals() {
    if (!token || !evalGameId.trim()) {
      setEvalError("请填写 token 和 game id。");
      return;
    }
    setEvalLoading(true);
    setEvalError("");
    try {
      const data = await fetchGameEvaluations(token, evalGameId.trim());
      setEvals(data);
      if (data.length === 0) {
        setEvalError("该游戏暂无评分。可用 scripts/judge_turn.py 生成。");
      }
    } catch (err) {
      setEvalError(err instanceof Error ? err.message : String(err));
    } finally {
      setEvalLoading(false);
    }
  }

  return (
    <AppShell>
      <main className="mx-auto grid w-full max-w-5xl gap-5 text-sm">
        <section className="px-panel px-panel-strong px-panel-pad">
          <p className="px-eyebrow">OBSERVATORY</p>
          <h1 className="px-heading mt-2 text-2xl">AI 链路监控</h1>
          <p className="mt-2 text-[color:var(--muted)]">
            最近 {limit} 个已完成回合的 telemetry、评分、trace。所有数据来自 agent_traces / turn_jobs / turn_evaluations。
          </p>
        </section>

        <section className="px-panel px-panel-pad">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1">
              <label className="px-label mb-1 block">管理 Token</label>
              <input
                type="password"
                className="px-input"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="SETTINGS_ADMIN_TOKEN"
              />
            </div>
            <button
              type="button"
              onClick={handleSaveToken}
              className="px-btn px-btn-primary"
            >
              保存
            </button>
            <button
              type="button"
              onClick={handleRefresh}
              className="px-btn"
              disabled={state === "loading"}
            >
              刷新
            </button>
            <div>
              <label className="px-label mb-1 block">样本量</label>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="px-input"
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
              </select>
            </div>
          </div>
        </section>

        {state === "loading" && <p className="px-status">加载中…</p>}
        {state === "error" && <p className="px-alert">错误：{error}</p>}

        {stats && (
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card
              label="样本回合数"
              value={String(stats.sample_size)}
              hint={`最近 ${limit} 个 completed turn job`}
            />
            <Card
              label="Director fallback"
              value={pct(stats.director_fallback_rate)}
              hint={`${stats.director_fallback_count} 次降级到本地决策`}
              tone={stats.director_fallback_rate > 0.1 ? "warn" : "ok"}
            />
            <Card
              label="GM 重写率"
              value={pct(stats.rewrite_rate)}
              hint={`${stats.rewrite_count} 次被 Drift 判定需要重写`}
              tone={stats.rewrite_rate > 0.2 ? "warn" : "ok"}
            />
            <Card
              label="StateExtractor 失败率"
              value={pct(stats.extractor_failed_rate)}
              hint={`${stats.extractor_failed_count} 次提取失败（含重试覆盖前）`}
              tone={stats.extractor_failed_rate > 0.05 ? "warn" : "ok"}
            />
            <Card
              label="平均评分"
              value={
                stats.avg_overall_score !== null
                  ? `${stats.avg_overall_score} / 5`
                  : "—"
              }
              hint={`基于 ${stats.evaluations_count} 个 Judge 评分`}
            />
            <Card
              label="Drift 严重度分布"
              value=""
              hint=""
              extra={
                <div className="mt-1 grid gap-0.5 text-xs">
                  {Object.entries(stats.drift_severity_distribution)
                    .sort((a, b) => b[1] - a[1])
                    .map(([sev, n]) => (
                      <div key={sev} className="flex justify-between">
                        <span className="text-[color:var(--muted)]">{sev}</span>
                        <span className="font-mono text-[color:var(--phosphor)]">{n}</span>
                      </div>
                    ))}
                </div>
              }
            />
            <Card
              label="Agent 平均延迟"
              value=""
              hint=""
              extra={
                <div className="mt-1 grid gap-0.5 text-xs">
                  {Object.entries(stats.avg_latency_ms_by_agent)
                    .sort((a, b) => b[1] - a[1])
                    .map(([agent, ms]) => (
                      <div key={agent} className="flex justify-between">
                        <span className="text-[color:var(--muted)]">{agent}</span>
                        <span className="font-mono text-[color:var(--phosphor)]">{Math.round(ms)} ms</span>
                      </div>
                    ))}
                </div>
              }
            />
          </section>
        )}

        {traces.length > 0 && (
          <section className="px-panel px-panel-pad">
            <h2 className="px-heading text-base">最近 30 条 LLM 调用</h2>
            <div className="px-table-wrap mt-3">
              <table className="px-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>Agent</th>
                    <th>模型</th>
                    <th>状态</th>
                    <th>tokens (in/out)</th>
                    <th>latency</th>
                    <th>job</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.map((t) => (
                    <tr
                      key={t.id}
                      onClick={() => void handleOpenTrace(t.id)}
                      className={t.status === "success" ? "" : "row-danger"}
                    >
                      <td className="font-mono">
                        {new Date(t.created_at).toLocaleTimeString()}
                      </td>
                      <td>{t.agent}</td>
                      <td className="font-mono">{t.model ?? "—"}</td>
                      <td>{t.status}</td>
                      <td className="font-mono">
                        {t.tokens_input ?? "—"} / {t.tokens_output ?? "—"}
                      </td>
                      <td className="font-mono">{t.latency_ms} ms</td>
                      <td className="font-mono">
                        {t.job_kind ? `${t.job_kind}/${(t.job_id ?? "").slice(0, 8)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-[color:var(--faint)]">点击任意行查看完整 prompt / output。</p>
          </section>
        )}

        {(detailLoading || detailError || detail) && (
          <section className="px-panel px-panel-pad">
            <h2 className="px-heading text-base">Trace 详情</h2>
            {detailLoading && <p className="mt-2 text-[color:var(--muted)]">加载中…</p>}
            {detailError && <p className="px-alert mt-2">错误：{detailError}</p>}
            {detail && (
              <div className="mt-3 grid gap-4">
                <div className="text-xs text-[color:var(--muted)]">
                  <span className="font-mono">{detail.id}</span> · {detail.agent} ·{" "}
                  {detail.model ?? "—"} · {detail.status} · {detail.latency_ms} ms
                  {detail.error_message ? (
                    <span className="text-[color:var(--danger)]"> · {detail.error_message}</span>
                  ) : null}
                </div>
                {(detail.prompt_messages ?? []).map((m, i) => (
                  <div key={i}>
                    <div className="px-label">
                      message[{i}] · {m.role}
                    </div>
                    <pre className="px-scroll-text mt-1 max-h-64 font-mono text-xs">
                      {m.content}
                    </pre>
                  </div>
                ))}
                {detail.reasoning_text ? (
                  <div>
                    <div className="px-label">reasoning</div>
                    <pre className="px-scroll-text mt-1 max-h-48 border-[#8a6420] font-mono text-xs text-[color:var(--amber)]">
                      {detail.reasoning_text}
                    </pre>
                  </div>
                ) : null}
                <div>
                  <div className="px-label">output</div>
                  <pre className="px-scroll-text mt-1 max-h-96 font-mono text-xs">
                    {detail.output_text ?? "(empty)"}
                  </pre>
                </div>
              </div>
            )}
          </section>
        )}

        <section className="px-panel px-panel-pad">
          <h2 className="px-heading text-base">Judge 评分查询</h2>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1">
              <label className="px-label mb-1 block">Game ID</label>
              <input
                type="text"
                className="px-input font-mono"
                value={evalGameId}
                onChange={(e) => setEvalGameId(e.target.value)}
                placeholder="游戏 UUID"
              />
            </div>
            <button
              type="button"
              onClick={() => void handleLoadEvals()}
              className="px-btn"
              disabled={evalLoading}
            >
              查询
            </button>
          </div>
          {evalError && <p className="px-warning mt-2 text-xs">{evalError}</p>}
          {evals.length > 0 && (
            <div className="px-table-wrap mt-3">
              <table className="px-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>overall</th>
                    <th>忠实</th>
                    <th>状态一致</th>
                    <th>节奏</th>
                    <th>文笔</th>
                    <th>新意</th>
                    <th>安全</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {evals.map((ev) => (
                    <tr
                      key={ev.id}
                      className={ev.status === "success" ? "" : "row-danger"}
                    >
                      <td className="font-mono">
                        {new Date(ev.created_at).toLocaleString()}
                      </td>
                      <td className="font-mono font-bold text-[color:var(--phosphor)]">
                        {ev.overall_score ?? "—"}
                      </td>
                      <td className="font-mono">{ev.canon_fidelity ?? "—"}</td>
                      <td className="font-mono">{ev.state_consistency ?? "—"}</td>
                      <td className="font-mono">{ev.pacing ?? "—"}</td>
                      <td className="font-mono">{ev.prose_quality ?? "—"}</td>
                      <td className="font-mono">{ev.freshness ?? "—"}</td>
                      <td className="font-mono">{ev.safety ?? "—"}</td>
                      <td>{ev.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}

function Card({
  label,
  value,
  hint,
  tone,
  extra
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "ok" | "warn";
  extra?: React.ReactNode;
}) {
  return (
    <div className={`px-metric ${tone === "warn" ? "border-[#8a6420]" : ""}`}>
      <div className="px-metric-label">{label}</div>
      {value && <div className={`mt-1 text-xl font-black ${tone === "warn" ? "text-[#ffb347]" : "text-[color:var(--phosphor)]"}`}>{value}</div>}
      {hint && <div className="mt-1 text-xs text-[color:var(--muted)]">{hint}</div>}
      {extra}
    </div>
  );
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}
