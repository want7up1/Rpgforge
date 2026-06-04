"use client";

import { useState } from "react";

import { createModule } from "@/lib/api";

export function SaveAsModuleDialog({
  defaultName,
  moduleType,
  payload,
  sourceGameId,
  onClose,
  onSaved
}: {
  defaultName: string;
  moduleType: string;
  payload: Record<string, unknown>;
  sourceGameId: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createModule({
        name: name.trim(), description: description.trim() || null, module_type: moduleType,
        payload, tags: tags.split(",").map((t) => t.trim()).filter(Boolean), source_game_id: sourceGameId,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="surface-panel surface-panel-strong w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="surface-title">⚗ 存为模块</h3>
        <div className="mt-3 grid gap-3">
          <label className="grid gap-1 text-sm"><span className="font-semibold">名称</span>
            <input className="app-input" value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="grid gap-1 text-sm"><span className="font-semibold">描述（可选）</span>
            <textarea className="app-input min-h-16" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <label className="grid gap-1 text-sm"><span className="font-semibold">标签（逗号分隔）</span>
            <input className="app-input" value={tags} onChange={(e) => setTags(e.target.value)} /></label>
        </div>
        {error ? <p className="app-alert mt-2">{error}</p> : null}
        <div className="mt-4 flex gap-2">
          <button className="app-button app-button-primary" disabled={saving || !name.trim()} type="button" onClick={() => void handleSave()}>
            {saving ? "保存中..." : "存入工坊"}
          </button>
          <button className="app-button" type="button" onClick={onClose}>取消</button>
        </div>
      </div>
    </div>
  );
}
