"use client";

import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { deleteModule, importModules, listModules, moduleExportUrl, patchModule } from "@/lib/api";
import type { SettingModule } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  world: "世界与基调", characters: "角色", plot: "剧情结构",
  mechanics: "玩法机制", constraints: "约束与红线", materials: "素材库", advanced: "高级"
};

export default function WorkshopPage() {
  const [modules, setModules] = useState<SettingModule[]>([]);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await listModules({ type: type || undefined, q: q || undefined });
        setModules(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "读取失败");
      }
    }
    void load();
  }, [type, tick]); // q 通过按钮/回车触发（bump tick）

  function handleSearch() {
    setTick((n) => n + 1);
  }

  function toggle(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) { n.delete(id); } else { n.add(id); }
      return n;
    });
  }

  async function handleDelete(id: string) {
    if (!window.confirm("删除该模块？")) return;
    await deleteModule(id);
    setTick((n) => n + 1);
  }

  async function handleRename(m: SettingModule) {
    const name = window.prompt("模块名", m.name);
    if (name && name.trim()) {
      await patchModule(m.id, { name: name.trim() });
      setTick((n) => n + 1);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await importModules(JSON.parse(await file.text()));
      setTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      e.target.value = "";
    }
  }

  return (
    <AppShell>
      <section className="game-page-hero">
        <h1 className="game-page-title">剧本炼金工坊</h1>
        <p className="mt-2 text-sm text-[color:var(--muted)]">可复用设定模块的个人库（仅本地，文件导入导出）。</p>
      </section>
      {error ? <section className="app-alert">{error}</section> : null}

      <section className="surface-panel">
        <div className="flex flex-wrap items-center gap-2">
          <input className="app-input max-w-xs" placeholder="搜索名称/描述…" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }} />
          <button className="app-button" type="button" onClick={handleSearch}>搜索</button>
          <select className="app-input max-w-[10rem]" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">全部类型</option>
            {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="flex-1" />
          <button className="app-button" type="button" onClick={() => fileRef.current?.click()}>⬆ 导入工坊文件</button>
          <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={handleImport} />
          <a className={`app-button ${selected.size ? "" : "pointer-events-none opacity-50"}`}
            href={moduleExportUrl([...selected])}>⬇ 导出所选（{selected.size}）</a>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {modules.length === 0 ? (
            <p className="surface-subtle">暂无模块。去任意剧本设定页的看板「存为模块」。</p>
          ) : modules.map((m) => (
            <article key={m.id} className={`archive-card ${selected.has(m.id) ? "ring-2 ring-[#4a9a6f]" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 font-semibold">
                  <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />
                  {m.name}
                </label>
                <span className="app-pill">{TYPE_LABELS[m.module_type] ?? m.module_type}</span>
              </div>
              {m.description ? <p className="mt-1 text-xs text-[color:var(--muted)]">{m.description}</p> : null}
              {m.tags.length ? <p className="mt-1 text-xs text-[color:var(--muted)]">{m.tags.map((t) => `#${t}`).join(" ")}</p> : null}
              <div className="mt-2 flex gap-2">
                <button className="app-button" type="button" onClick={() => void handleRename(m)}>改名</button>
                <button className="app-button" type="button" onClick={() => void handleDelete(m.id)}>删除</button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
