"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import {
  fetchRecentTraces,
  fetchRecentTurnStats,
  type AgentTraceSummary,
  type RecentTurnStats
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

  return (
    <AppShell>
      <main className="mx-auto max-w-5xl px-4 py-8 text-sm">
        <h1 className="text-2xl font-semibold mb-2">AI 链路监控</h1>
        <p className="text-gray-500 mb-6">
          最近 {limit} 个已完成回合的 telemetry、评分、trace。所有数据来自 agent_traces / turn_jobs / turn_evaluations。
        </p>

        <section className="mb-6 rounded-lg border border-gray-200 p-4">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">管理 Token</label>
              <input
                type="password"
                className="w-full rounded border border-gray-300 px-2 py-1"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="SETTINGS_ADMIN_TOKEN"
              />
            </div>
            <button
              type="button"
              onClick={handleSaveToken}
              className="rounded bg-gray-900 px-3 py-1 text-white"
            >
              保存
            </button>
            <button
              type="button"
              onClick={handleRefresh}
              className="rounded border border-gray-300 px-3 py-1"
              disabled={state === "loading"}
            >
              刷新
            </button>
            <div>
              <label className="block text-xs text-gray-500 mb-1">样本量</label>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="rounded border border-gray-300 px-2 py-1"
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
              </select>
            </div>
          </div>
        </section>

        {state === "loading" && <p className="text-gray-500">加载中…</p>}
        {state === "error" && <p className="text-red-600">错误：{error}</p>}

        {stats && (
          <section className="grid grid-cols-2 gap-4 md:grid-cols-4 mb-8">
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
                <div className="text-xs space-y-0.5">
                  {Object.entries(stats.drift_severity_distribution)
                    .sort((a, b) => b[1] - a[1])
                    .map(([sev, n]) => (
                      <div key={sev} className="flex justify-between">
                        <span className="text-gray-500">{sev}</span>
                        <span className="font-mono">{n}</span>
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
                <div className="text-xs space-y-0.5">
                  {Object.entries(stats.avg_latency_ms_by_agent)
                    .sort((a, b) => b[1] - a[1])
                    .map(([agent, ms]) => (
                      <div key={agent} className="flex justify-between">
                        <span className="text-gray-500">{agent}</span>
                        <span className="font-mono">{Math.round(ms)} ms</span>
                      </div>
                    ))}
                </div>
              }
            />
          </section>
        )}

        {traces.length > 0 && (
          <section>
            <h2 className="mb-2 text-lg font-semibold">最近 30 条 LLM 调用</h2>
            <div className="overflow-x-auto rounded border border-gray-200">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-left">
                  <tr>
                    <th className="px-2 py-1">时间</th>
                    <th className="px-2 py-1">Agent</th>
                    <th className="px-2 py-1">模型</th>
                    <th className="px-2 py-1">状态</th>
                    <th className="px-2 py-1">tokens (in/out)</th>
                    <th className="px-2 py-1">latency</th>
                    <th className="px-2 py-1">job</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.map((t) => (
                    <tr
                      key={t.id}
                      className={
                        t.status === "success"
                          ? ""
                          : "bg-red-50 text-red-700"
                      }
                    >
                      <td className="px-2 py-1 font-mono">
                        {new Date(t.created_at).toLocaleTimeString()}
                      </td>
                      <td className="px-2 py-1">{t.agent}</td>
                      <td className="px-2 py-1 font-mono">{t.model ?? "—"}</td>
                      <td className="px-2 py-1">{t.status}</td>
                      <td className="px-2 py-1 font-mono">
                        {t.tokens_input ?? "—"} / {t.tokens_output ?? "—"}
                      </td>
                      <td className="px-2 py-1 font-mono">{t.latency_ms} ms</td>
                      <td className="px-2 py-1 font-mono">
                        {t.job_kind ? `${t.job_kind}/${(t.job_id ?? "").slice(0, 8)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
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
  const toneClass =
    tone === "warn" ? "border-amber-300 bg-amber-50" : "border-gray-200";
  return (
    <div className={`rounded-lg border ${toneClass} p-3`}>
      <div className="text-xs text-gray-500">{label}</div>
      {value && <div className="text-xl font-semibold mt-1">{value}</div>}
      {hint && <div className="text-xs text-gray-500 mt-1">{hint}</div>}
      {extra}
    </div>
  );
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}
