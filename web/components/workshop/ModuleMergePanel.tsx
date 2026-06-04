"use client";

import { useEffect, useState } from "react";

import { listModules, mergePreviewModules } from "@/lib/api";
import type { ModuleMergePreview, SettingModule } from "@/lib/types";

type Resolution = "rename" | "overwrite" | "skip";

/** 将 preview 与生成时的 targetSettings 引用绑定，用于渲染阶段检测陈旧预览 */
type BoundPreview = {
  snapshot: Record<string, unknown>;
  data: ModuleMergePreview;
};

export function ModuleMergePanel({
  targetSettings,
  onApply
}: {
  targetSettings: Record<string, unknown>;
  onApply: (merged: Record<string, unknown>) => Promise<void> | void;
}) {
  const [modules, setModules] = useState<SettingModule[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adapt, setAdapt] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [bound, setBound] = useState<BoundPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listModules().then(setModules).catch((e) => setError(e instanceof Error ? e.message : "读取模块失败"));
  }, []);

  // 若 targetSettings 引用变更（父组件编辑了 settings），陈旧预览在渲染时自动作废，
  // 避免将基于旧 settings 生成的合并结果写入新 settings（数据完整性保障）
  const preview = bound !== null && bound.snapshot === targetSettings ? bound.data : null;

  function toggle(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) { n.delete(id); } else { n.add(id); }
      return n;
    });
    setBound(null);
  }

  async function runPreview() {
    setBusy(true); setError(null);
    try {
      const data = await mergePreviewModules({
        target_settings: targetSettings, module_ids: [...selected],
        adapt, conflict_resolutions: resolutions,
      });
      // 将结果与此刻的 targetSettings 引用绑定，便于后续陈旧检测
      setBound({ snapshot: targetSettings, data });
    } catch (e) {
      setError(e instanceof Error ? e.message : "预览失败");
    } finally { setBusy(false); }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true); setError(null);
    try {
      await onApply(preview.merged_settings);
      setBound(null); setSelected(new Set()); setResolutions({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "并入失败");
    } finally { setBusy(false); }
  }

  return (
    <section className="surface-panel">
      <h2 className="surface-title">从工坊并入</h2>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {modules.length === 0 ? <p className="surface-subtle">工坊暂无模块。</p> :
          modules.map((m) => (
            <label key={m.id} className={`archive-card flex items-center gap-2 ${selected.has(m.id) ? "ring-2 ring-[#4a9a6f]" : ""}`}>
              <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />
              <span className="font-semibold">{m.name}</span>
              <span className="app-pill ml-auto">{m.module_type}</span>
            </label>
          ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={adapt} onChange={(e) => { setAdapt(e.target.checked); setBound(null); }} />
          ⭐ AI 本地优化（改写贴合当前剧本）
        </label>
        <button className="app-button app-button-primary" type="button" disabled={busy || selected.size === 0} onClick={() => void runPreview()}>
          {busy ? "处理中..." : "生成并入预览"}
        </button>
      </div>
      {error ? <p className="app-alert mt-2">{error}</p> : null}

      {preview ? (
        <div className="mt-4 border-t border-[color:var(--border)] pt-3">
          <h3 className="font-semibold">并入预览</h3>
          <p className="text-xs text-[color:var(--muted)]">去重跳过 {preview.report.deduped} 条重复字符串。</p>
          <div className="mt-2 grid gap-2">
            {preview.report.entries.map((e) => {
              const mod = modules.find((m) => m.id === e.module_id);
              return (
                <div key={e.module_id} className="archive-card text-sm">
                  <b>{mod?.name ?? e.module_id}</b> — {actionLabel(e.action)}{e.renamed_to ? `（→ ${e.renamed_to}）` : ""}
                  {e.conflict ? (
                    <span className="ml-2">
                      冲突处理：
                      {(["rename", "overwrite", "skip"] as Resolution[]).map((r) => (
                        <button key={r}
                          className={`app-button ml-1 ${(resolutions[e.module_id] ?? "rename") === r ? "app-button-primary" : ""}`}
                          type="button"
                          onClick={() => { setResolutions((s) => ({ ...s, [e.module_id]: r })); setBound(null); }}>
                          {resLabel(r)}
                        </button>
                      ))}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
          {preview.adapted.length ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-sm text-[color:var(--muted)]">⭐ AI 改写前后对比（{preview.adapted.length}）</summary>
              <div className="mt-2 grid gap-2">
                {preview.adapted.map((a) => (
                  <div key={a.module_id} className="grid gap-1 sm:grid-cols-2">
                    <pre className="app-wrap-text rounded border border-[#f0c2bb] bg-[#fff0ee] p-2 text-xs">{JSON.stringify(a.before, null, 1)}</pre>
                    <pre className="app-wrap-text rounded border border-[#bfe0c8] bg-[#eef7f0] p-2 text-xs">{JSON.stringify(a.after, null, 1)}</pre>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button className="app-button app-button-primary" type="button" disabled={busy} onClick={() => void confirm()}>确认并入</button>
            <button className="app-button" type="button" onClick={() => setBound(null)}>取消</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function actionLabel(a: string): string {
  return ({ added: "新增", renamed: "改名并入", overwritten: "覆盖现有", skipped: "跳过" } as Record<string, string>)[a] ?? a;
}
function resLabel(r: Resolution): string {
  return ({ rename: "改名", overwrite: "覆盖", skip: "跳过" } as Record<Resolution, string>)[r];
}
