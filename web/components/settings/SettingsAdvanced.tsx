"use client";

import { ChangeEvent, FormEvent, ReactNode, useState } from "react";

import { JsonBlock } from "@/components/JsonBlock";
import {
  getGameSettingsExport,
  getGameSettingsGuideExport,
  importGameSettings,
  restoreSettingVersion,
  updateGameConfig
} from "@/lib/api";
import { downloadBlob } from "@/lib/downloads";
import type { GameDetail, GameSettingVersionRead } from "@/lib/types";

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}
function parseRecordJson(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch (caught) {
    throw new Error(`${label} 不是合法 JSON：${caught instanceof Error ? caught.message : "解析失败"}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON object。`);
  }
  return parsed as Record<string, unknown>;
}
function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function Fold({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="surface-panel">
      <summary className="cursor-pointer surface-title">{title}</summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

export function SettingsAdvanced({
  game,
  versions,
  onRefresh,
  disabled = false
}: {
  game: GameDetail;
  versions: GameSettingVersionRead[];
  onRefresh: () => Promise<void>;
  disabled?: boolean;
}) {
  return (
    <div className="grid gap-3">
      <Fold title="高级 · 原始 story_settings JSON">
        <RawJsonEditor game={game} onRefresh={onRefresh} disabled={disabled} />
      </Fold>
      <Fold title="高级 · 导入 / 导出 / 填写说明">
        <ImportExport game={game} onRefresh={onRefresh} disabled={disabled} />
      </Fold>
      <Fold title="高级 · 版本历史">
        <VersionHistory gameId={game.id} versions={versions} onRefresh={onRefresh} disabled={disabled} />
      </Fold>
    </div>
  );
}

function RawJsonEditor({ game, onRefresh, disabled = false }: { game: GameDetail; onRefresh: () => Promise<void>; disabled?: boolean }) {
  const current = asRecord(game.config?.story_settings);
  const [draft, setDraft] = useState(() => formatJson(current));
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("正在保存 story_settings...");
    setError(null);
    try {
      await updateGameConfig(game.id, { story_settings_json: parseRecordJson(draft, "story_settings") });
      await onRefresh();
      setStatus("story_settings 已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败。");
      setStatus(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="grid gap-3" onSubmit={handleSubmit}>
      <p className="surface-subtle">直接编辑整份设定。只作用于 story_settings，不改回合历史/状态/摘要/存档。</p>
      <textarea
        className="app-input min-h-[320px] font-mono text-xs"
        disabled={disabled || saving}
        onChange={(e) => setDraft(e.target.value)}
        value={draft}
      />
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary" disabled={disabled || saving} type="submit">
          {saving ? "保存中..." : "保存 story_settings"}
        </button>
        <button className="app-button" disabled={disabled || saving} type="button" onClick={() => { setDraft(formatJson(current)); setError(null); setStatus("已恢复为当前已保存内容。"); }}>
          恢复当前内容
        </button>
      </div>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
    </form>
  );
}

function ImportExport({ game, onRefresh, disabled = false }: { game: GameDetail; onRefresh: () => Promise<void>; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(kind: "json" | "guide") {
    setBusy(true);
    setError(null);
    setStatus(kind === "json" ? "正在导出 JSON..." : "正在生成填写说明...");
    try {
      const { blob, filename } =
        kind === "json" ? await getGameSettingsExport(game.id) : await getGameSettingsGuideExport(game.id);
      downloadBlob(blob, filename);
      setStatus("已开始下载。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出失败。");
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setStatus("正在导入...");
    try {
      const payload = JSON.parse(await file.text()) as unknown;
      await importGameSettings(game.id, payload);
      await onRefresh();
      setStatus("已导入并保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导入失败。");
      setStatus(null);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2">
        <button className="app-button app-button-primary w-fit" disabled={disabled || busy} type="button" onClick={() => download("json")}>导出 JSON</button>
        <button className="app-button w-fit" disabled={disabled || busy} type="button" onClick={() => download("guide")}>下载填写说明</button>
      </div>
      <label className="grid gap-1 text-sm font-medium">
        <span>导入 story_settings JSON（覆盖设定，不动存档/回合/状态）</span>
        <input accept="application/json,.json" className="app-input" disabled={disabled || busy} onChange={handleImport} type="file" />
      </label>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
    </div>
  );
}

function VersionHistory({
  gameId,
  versions,
  onRefresh,
  disabled = false
}: {
  gameId: string;
  versions: GameSettingVersionRead[];
  onRefresh: () => Promise<void>;
  disabled?: boolean;
}) {
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRestore(versionId: string) {
    setRestoringId(versionId);
    setStatus("正在恢复该版本...");
    setError(null);
    try {
      await restoreSettingVersion(gameId, versionId);
      await onRefresh();
      setStatus("版本已恢复。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复失败。");
      setStatus(null);
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div className="grid gap-3">
      <p className="surface-subtle">保存/导入/恢复设定时会记录快照；恢复只影响设定，不影响存档进度。</p>
      {status ? <p className="app-status">{status}</p> : null}
      {error ? <p className="app-alert">{error}</p> : null}
      {versions.length === 0 ? (
        <p className="text-sm text-[color:var(--muted)]">暂无设置版本。</p>
      ) : (
        versions.map((version) => (
          <article className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-3" key={version.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-semibold">{version.scope} · {version.action}</p>
                <p className="text-xs text-[color:var(--muted)]">{new Date(version.created_at).toLocaleString()}</p>
              </div>
              <button className="app-button" disabled={disabled || restoringId === version.id} type="button" onClick={() => handleRestore(version.id)}>
                {restoringId === version.id ? "恢复中..." : "恢复"}
              </button>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-[color:var(--muted)]">查看快照</summary>
              <div className="mt-2 max-h-96 overflow-auto rounded border border-[color:var(--border)]">
                <JsonBlock data={version.snapshot_json} />
              </div>
            </details>
          </article>
        ))
      )}
    </div>
  );
}
