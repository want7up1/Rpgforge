"use client";

import { useState } from "react";

import type { BoardField, BoardFieldValue, SubFieldSpec } from "@/lib/generatorBoard";

function asStr(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

// objectList 里单个子对象的小型编辑器
function SubItemEditor({
  spec,
  item,
  onChange
}: {
  spec: SubFieldSpec[];
  item: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  function set(key: string, value: unknown) {
    onChange({ ...item, [key]: value });
  }
  return (
    <div className="grid gap-2">
      {spec.map((s) => (
        <label key={s.key} className="grid gap-1 text-xs">
          <span className="font-medium">{s.label}</span>
          {s.type === "bool" ? (
            <input type="checkbox" checked={Boolean(item[s.key])} onChange={(e) => set(s.key, e.target.checked)} />
          ) : s.type === "number" ? (
            <input
              className="app-input"
              type="number"
              value={asStr(item[s.key])}
              onChange={(e) => set(s.key, e.target.value === "" ? 0 : Number(e.target.value))}
            />
          ) : s.type === "stringList" ? (
            <textarea
              className="app-input min-h-16"
              value={(Array.isArray(item[s.key]) ? (item[s.key] as string[]) : []).join("\n")}
              onChange={(e) => set(s.key, e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))}
            />
          ) : s.type === "textarea" ? (
            <textarea className="app-input min-h-16" value={asStr(item[s.key])} onChange={(e) => set(s.key, e.target.value)} />
          ) : (
            <input className="app-input" value={asStr(item[s.key])} onChange={(e) => set(s.key, e.target.value)} />
          )}
        </label>
      ))}
    </div>
  );
}

function JsonEditor({ value, onChange }: { value: BoardFieldValue; onChange: (v: BoardFieldValue) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="grid gap-1">
      <textarea
        className="app-input min-h-24 font-mono text-xs"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          try {
            onChange(JSON.parse(e.target.value) as BoardFieldValue);
            setError(null);
          } catch {
            setError("JSON 格式有误，暂未保存该字段");
          }
        }}
      />
      {error ? <span className="text-xs text-[color:var(--danger-text)]">{error}</span> : null}
    </div>
  );
}

export function BoardFieldEditor({
  field,
  value,
  onChange
}: {
  field: BoardField;
  value: BoardFieldValue;
  onChange: (v: BoardFieldValue) => void;
}) {
  if (field.type === "text") {
    return <input className="app-input" value={asStr(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  if (field.type === "textarea") {
    return <textarea className="app-input min-h-24 resize-y leading-6" value={asStr(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  if (field.type === "number") {
    return (
      <input
        className="app-input"
        type="number"
        value={asStr(value)}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    );
  }
  if (field.type === "bool") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} /> 是
      </label>
    );
  }
  if (field.type === "stringList") {
    const list = Array.isArray(value) ? (value as string[]) : [];
    return (
      <div className="grid gap-1">
        {list.map((s, i) => (
          <div key={i} className="flex gap-2">
            <input
              className="app-input flex-1"
              value={s}
              onChange={(e) => {
                const n = [...list];
                n[i] = e.target.value;
                onChange(n);
              }}
            />
            <button className="app-button" type="button" onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="app-button w-fit" type="button" onClick={() => onChange([...list, ""])}>＋ 加一条</button>
      </div>
    );
  }
  if (field.type === "objectList") {
    const items = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
    const spec = field.itemFields ?? [];
    return (
      <div className="grid gap-2">
        {items.map((it, i) => (
          <div key={i} className="rounded border border-[color:var(--border)] bg-[color:var(--soft-panel)] p-2">
            <SubItemEditor
              spec={spec}
              item={it}
              onChange={(next) => {
                const n = [...items];
                n[i] = next;
                onChange(n);
              }}
            />
            <button className="app-button mt-2" type="button" onClick={() => onChange(items.filter((_, j) => j !== i))}>删除此项</button>
          </div>
        ))}
        <button
          className="app-button w-fit"
          type="button"
          onClick={() =>
            onChange([
              ...items,
              Object.fromEntries(spec.map((s) => [s.key, s.type === "bool" ? false : s.type === "stringList" ? [] : s.type === "number" ? 0 : ""]))
            ])
          }
        >
          ＋ 新增一项
        </button>
      </div>
    );
  }
  if (field.type === "keyValue") {
    const obj = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
    const entries = Object.entries(obj);
    return (
      <div className="grid gap-1">
        {entries.map(([k, v], i) => (
          <div key={i} className="flex gap-2">
            <input
              className="app-input w-1/3"
              value={k}
              onChange={(e) => {
                const next: Record<string, unknown> = {};
                entries.forEach(([kk, vv], j) => {
                  next[j === i ? e.target.value : kk] = vv;
                });
                onChange(next);
              }}
            />
            <input className="app-input flex-1" value={asStr(v)} onChange={(e) => onChange({ ...obj, [k]: e.target.value })} />
            <button
              className="app-button"
              type="button"
              onClick={() => {
                const next = { ...obj };
                delete next[k];
                onChange(next);
              }}
            >
              ✕
            </button>
          </div>
        ))}
        <button className="app-button w-fit" type="button" onClick={() => onChange({ ...obj, "": "" })}>＋ 加一项</button>
      </div>
    );
  }
  return <JsonEditor value={value} onChange={onChange} />;
}
