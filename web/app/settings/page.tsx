"use client";

import { FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { discoverModels, getDeepSeekSettings, updateDeepSeekSettings } from "@/lib/api";
import type { DeepSeekSettingsRead } from "@/lib/types";

import { canSaveModelDraft, modelProbeReadiness, ModelProbeSession, normalizedModelBaseUrl, selectDiscoveredModels } from "@/lib/modelDiscovery";
type ModelSlot = "flash" | "pro";

const taskRouteRows: {
  key: string;
  label: string;
  description: string;
  defaultSlot: ModelSlot;
}[] = [
  {
    key: "generator_interview",
    label: "冒险设定确认",
    description: "理解冒险想法、确认核心需求和剧本锚点。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize",
    label: "冒险世界入口",
    description: "负责冒险世界生成任务的入口与兼容路由。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_outline",
    label: "剧本导演总纲",
    description: "先锁定 story_settings v2 的世界观、故事核心、幕结构计划和强制边界。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_core_characters",
    label: "核心人物生成",
    description: "生成主角、关键 NPC、关系定位、公开介绍和外貌描述。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_act_plan",
    label: "五幕主线生成",
    description: "生成当前故事的幕结构、完成锚点和过渡条件。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_main_quest_path",
    label: "主线轨迹生成",
    description: "生成软主线任务轨迹，让 GM 能推进但不强迫玩家离场。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_core_mechanics",
    label: "核心机制生成",
    description: "生成长期玩法机制、成长、资源、压力和判定规则。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_action_style_rules",
    label: "行动风格规则生成",
    description: "生成调查、社交、探索、战斗等行动风格下的 GM 处理规则。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_story_material_library",
    label: "剧本素材库生成",
    description: "生成可召回的地点、势力、秘密、线索、压力和反转素材。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_home_base",
    label: "[地点]生成",
    description: "生成长期据点、功能、NPC 服务、升级路径和剧情钩子。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_hard_rules",
    label: "强制规则生成",
    description: "生成最高优先级强制规则、禁止事项、揭露规则和连续性规则。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_initial_state",
    label: "初始状态生成",
    description: "生成开局处境、随身物品、人物关系和已知线索。",
    defaultSlot: "pro"
  },
  {
    key: "gm_runtime",
    label: "剧情输出",
    description: "根据玩家行动逐步输出正文剧情和行动选项。",
    defaultSlot: "pro"
  },
  {
    key: "gm_runtime_rewrite",
    label: "剧情重写",
    description: "偏离校验失败时重写本回合剧情。",
    defaultSlot: "pro"
  },
  {
    key: "story_director",
    label: "剧情导演层",
    description: "回合前规划节奏、当前幕目标和禁止揭露内容。",
    defaultSlot: "flash"
  },
  {
    key: "drift_validator",
    label: "偏离校验器",
    description: "检查剧情是否偏离剧本承诺、状态和当前行动。",
    defaultSlot: "flash"
  },
  {
    key: "state_delta_extract",
    label: "状态提取",
    description: "从剧情结果中提取处境、物品、关系、任务与线索变化。",
    defaultSlot: "flash"
  },
  {
    key: "compress_context",
    label: "记忆摘要",
    description: "压缩回合、章节和长期记忆。",
    defaultSlot: "flash"
  }
];

type LoadState =
  | { status: "loading" }
  | { status: "ready"; settings: DeepSeekSettingsRead }
  | { status: "error"; message: string };

type DiscoveryState = { status: "idle" | "loading" | "success" | "error"; models: string[]; revision: number; message: string };

export default function SettingsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [flashModel, setFlashModel] = useState("");
  const [proModel, setProModel] = useState("");
  const [taskModelRoutes, setTaskModelRoutes] = useState<Record<string, ModelSlot>>(defaultTaskModelRoutes);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [providerRevision, setProviderRevision] = useState(0);
  const revision = useRef(0);
  const [probeTick, setProbeTick] = useState(0);
  const [probeCancelled, setProbeCancelled] = useState(false);
  const [discovery, setDiscovery] = useState<DiscoveryState>({ status: "idle", models: [], revision: -1, message: "" });
  const probes = useRef(new ModelProbeSession());
  const discoveredRevision = useRef<number | null>(null);
  const saving = useRef<AbortController | null>(null);
  const saved = state.status === "ready" ? state.settings : null;

  useEffect(() => {
    const controller = new AbortController();
    const session = probes.current;
    try { localStorage.removeItem("rpgforge.settingsAdminToken"); } catch { /* 清理旧版本的管理Token，不保存服务Key */ }
    void getDeepSeekSettings(controller.signal).then(settings => {
      if (controller.signal.aborted) return;
      setBaseUrl(normalizedModelBaseUrl(settings.base_url));
      setFlashModel(settings.flash_model);
      setProModel(settings.pro_model);
      setTaskModelRoutes(normalizeTaskModelRoutes(settings.task_model_routes));
      setState({ status: "ready", settings });
    }).catch(caught => {
      if (!controller.signal.aborted) setState({ status: "error", message: caught instanceof Error ? caught.message : "设置读取失败。" });
    });
    return () => { controller.abort(); session.cancel(); saving.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!saved || pending || probeCancelled || discoveredRevision.current === providerRevision) return;
    if (!modelProbeReadiness(baseUrl, apiKey, saved, clearApiKey).ready) return;
    const probe = probes.current.start();
    const timer = setTimeout(async () => {
      if (!probe.isCurrent()) return;
      setDiscovery({ status: "loading", models: [], revision: providerRevision, message: "正在读取服务提供的模型列表…" });
      try {
        const result = await discoverModels({ base_url: normalizedModelBaseUrl(baseUrl), api_key: apiKey.trim() || undefined }, probe.signal);
        if (!probe.isCurrent()) return;
        const { models } = selectDiscoveredModels(result, { flash: "", pro: "" });
        if (!models.length) throw new Error("该服务未返回可用模型，请检查服务地址和 Key 后重新探测。");
        discoveredRevision.current = providerRevision;
        setFlashModel(current => selectDiscoveredModels(result, { flash: current, pro: "" }).flash);
        setProModel(current => selectDiscoveredModels(result, { flash: "", pro: current }).pro);
        setDiscovery({ status: "success", models, revision: providerRevision, message: `已发现 ${models.length} 个模型，可选择槽位；保存后生效。` });
      } catch (caught) {
        if (probe.isCurrent()) setDiscovery({ status: "error", models: [], revision: providerRevision, message: `探测失败：${caught instanceof Error ? caught.message : "请检查服务地址和 Key 后重试。"}` });
      }
    }, 600);
    return () => { clearTimeout(timer); probe.cancel(); };
  }, [apiKey, baseUrl, clearApiKey, pending, probeCancelled, probeTick, providerRevision, saved]);

  function invalidateProvider() {
    probes.current.cancel();
    discoveredRevision.current = null;
    const next = ++revision.current;
    setProviderRevision(next);
    setProbeCancelled(false);
    setDiscovery({ status: "idle", models: [], revision: next, message: "" });
    setMessage(null);
  }

  function retryProbe() {
    probes.current.cancel();
    discoveredRevision.current = null;
    setProbeCancelled(false);
    setProbeTick(current => current + 1);
  }

  function cancelProbe() {
    probes.current.cancel();
    setProbeCancelled(true);
    setDiscovery({ status: "idle", models: [], revision: providerRevision, message: "已取消探测，可重新探测。" });
  }

  const currentDiscovery = discovery.status === "success" && discovery.revision === providerRevision;
  const canSave = saved !== null && canSaveModelDraft(saved, { baseUrl, apiKey, flash: flashModel, pro: proModel }, { current: currentDiscovery, models: discovery.models });
  const readiness = saved ? modelProbeReadiness(baseUrl, apiKey, saved, clearApiKey) : { ready: false, message: "" };
  const sameProvider = saved && normalizedModelBaseUrl(saved.base_url) === normalizedModelBaseUrl(baseUrl) && !apiKey.trim();
  const models = currentDiscovery ? discovery.models : sameProvider && saved ? [...new Set([saved.flash_model, saved.pro_model].filter(Boolean))] : [];

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !canSave) return;
    saving.current?.abort();
    const controller = saving.current = new AbortController();
    probes.current.cancel();
    setPending(true);
    setMessage(null);
    try {
      const updated = await updateDeepSeekSettings({ api_key: apiKey.trim() || undefined, clear_api_key: clearApiKey,
        base_url: normalizedModelBaseUrl(baseUrl), flash_model: flashModel, pro_model: proModel, task_model_routes: taskModelRoutes }, controller.signal);
      if (controller.signal.aborted) return;
      setApiKey("");
      setClearApiKey(false);
      setBaseUrl(normalizedModelBaseUrl(updated.base_url));
      setState({ status: "ready", settings: updated });
      setMessage("模型服务配置已保存，新的生成和回合请求会使用这些设置。");
    } catch (caught) {
      if (!controller.signal.aborted) setMessage(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return <AppShell>
    <section className="px-panel px-panel-strong px-panel-pad">
      <p className="px-eyebrow">SYSTEM CONSOLE</p><h1 className="px-heading mt-2 text-3xl">系统设置</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">填写服务地址与 API Key 自动发现模型，再选择槽位并分配任务；保存后生效。</p>
    </section>
    {state.status === "loading" ? <section className="px-panel px-panel-pad">正在读取设置…</section>
      : state.status === "error" ? <section className="px-alert">{state.message}</section>
      : <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <form className="px-panel px-panel-pad" onSubmit={handleSubmit}>
          <fieldset disabled={pending} className="grid gap-4 min-w-0">
            <label className="grid gap-2"><span className="px-label">Base URL</span>
              <input className="px-input" onChange={event => { invalidateProvider(); setBaseUrl(event.target.value); }} placeholder="https://api.example.com/v1" value={baseUrl} autoComplete="off" />
            </label>
            <label className="grid gap-2"><span className="px-label">API Key</span>
              <input className="px-input" disabled={clearApiKey} onChange={event => { invalidateProvider(); setApiKey(event.target.value); }} placeholder={state.settings.api_key_configured ? "留空使用已保存的 Key" : "填写该服务的 API Key"} type="password" autoComplete="off" value={apiKey} />
            </label>
            <label className="flex items-center gap-2 text-sm"><input checked={clearApiKey} onChange={event => { invalidateProvider(); setClearApiKey(event.target.checked); if (event.target.checked) { setApiKey(""); setFlashModel(state.settings.flash_model); setProModel(state.settings.pro_model); } }} type="checkbox" />清空数据库中保存的 API Key</label>
            <div className="grid gap-2">
              <p aria-live="polite" className={discovery.status === "error" ? "px-warning" : "px-status"}>{discovery.message || readiness.message}</p>
              <div className="flex flex-wrap gap-2"><button type="button" className="px-btn" disabled={!readiness.ready || discovery.status === "loading"} onClick={retryProbe}>重新探测模型</button>
                {discovery.status === "loading" || (readiness.ready && !currentDiscovery && !probeCancelled && discovery.status !== "error") ? <button type="button" className="px-btn" onClick={cancelProbe}>取消探测</button> : null}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <ModelSelect label="快速模型槽位" value={flashModel} models={models} disabled={!currentDiscovery} onChange={setFlashModel} />
              <ModelSelect label="高质量模型槽位" value={proModel} models={models} disabled={!currentDiscovery} onChange={setProModel} />
            </div>
            {!canSave ? <p className="text-xs text-[color:var(--muted)]">更换服务或 Key 后，请先探测并选择当前服务返回的模型。</p> : null}
            <section className="grid gap-3 border-t-2 border-[color:var(--border)] pt-4">
              <div><h2 className="px-heading text-base">模型职责分配</h2><p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">为每个步骤选择快速或高质量槽位，两槽也可以使用同一个模型。</p></div>
              <div className="grid gap-3">{taskRouteRows.map(row => <ModelRouteControl flashModel={flashModel} proModel={proModel} key={row.key} row={row} slot={taskModelRoutes[row.key] ?? row.defaultSlot} onChange={slot => setTaskModelRoutes(current => ({ ...current, [row.key]: slot }))} />)}</div>
            </section>
            {message ? <div className="px-status" role="status">{message}</div> : null}
            <button className="px-btn px-btn-primary" disabled={pending || !canSave} type="submit">{pending ? "保存中..." : "保存模型配置"}</button>
          </fieldset>
        </form>
        <aside className="px-panel px-panel-pad"><h2 className="px-heading text-base">已保存配置</h2><dl className="mt-4 grid gap-3 text-sm">
          <StatusRow label="API Key">{state.settings.api_key_configured ? state.settings.api_key_masked : "未配置"}</StatusRow>
          <StatusRow label="Key 来源">{{ database: "已保存", environment: "环境配置", missing: "未配置" }[state.settings.api_key_source]}</StatusRow>
          <StatusRow label="Base URL">{state.settings.base_url || "https://api.deepseek.com"}</StatusRow>
          <StatusRow label="快速模型">{state.settings.flash_model}</StatusRow><StatusRow label="高质量模型">{state.settings.pro_model}</StatusRow>
          <StatusRow label="职责分配"><div className="grid gap-2">{taskRouteRows.map(row => {
            const slot = state.settings.task_model_routes[row.key] ?? row.defaultSlot;
            return <div className="flex flex-wrap items-center justify-between gap-2" key={row.key}><span>{row.label}</span><span className="px-badge">{slotLabel(slot)} · {slot === "pro" ? state.settings.pro_model : state.settings.flash_model}</span></div>;
          })}</div></StatusRow>
        </dl></aside>
      </div>}
  </AppShell>;
}

function ModelSelect({ label, value, models, disabled, onChange }: { label: string; value: string; models: string[]; disabled: boolean; onChange: (value: string) => void }) {
  const selected = models.includes(value) ? value : "";
  return <label className="grid gap-2 min-w-0"><span className="px-label">{label}</span><select className="px-input min-w-0" value={selected} disabled={disabled} onChange={event => onChange(event.target.value)}>
    {!selected ? <option value="">等待探测模型</option> : null}{models.map(model => <option key={model} value={model}>{model}</option>)}
  </select></label>;
}

function ModelRouteControl({
  flashModel,
  onChange,
  proModel,
  row,
  slot
}: {
  flashModel: string;
  onChange: (slot: ModelSlot) => void;
  proModel: string;
  row: (typeof taskRouteRows)[number];
  slot: ModelSlot;
}) {
  const activeModel = slot === "pro" ? proModel : flashModel;

  return (
    <article className="px-card">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="min-w-0">
          <h3 className="font-bold">{row.label}</h3>
          <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
            {row.description}
          </p>
          <p className="mt-1 break-all text-xs text-[color:var(--muted)]">
            当前实际模型：{activeModel || "未填写"}
          </p>
        </div>
        <div className="mode-switch">
          <button
            className={slot === "flash" ? "mode-active" : undefined}
            onClick={() => onChange("flash")}
            type="button"
          >
            快速
          </button>
          <button
            className={slot === "pro" ? "mode-active" : undefined}
            onClick={() => onChange("pro")}
            type="button"
          >
            高质量
          </button>
        </div>
      </div>
    </article>
  );
}

function normalizeTaskModelRoutes(
  value: Record<string, ModelSlot> | undefined
): Record<string, ModelSlot> {
  const normalized = defaultTaskModelRoutes();
  if (!value) {
    return normalized;
  }
  for (const row of taskRouteRows) {
    const slot = value[row.key];
    if (slot === "flash" || slot === "pro") {
      normalized[row.key] = slot;
    }
  }
  return normalized;
}

function defaultTaskModelRoutes(): Record<string, ModelSlot> {
  return Object.fromEntries(
    taskRouteRows.map((row) => [row.key, row.defaultSlot])
  ) as Record<string, ModelSlot>;
}

function slotLabel(slot: ModelSlot) {
  return slot === "pro" ? "高质量" : "快速";
}

function StatusRow({
  children,
  label
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="border-b-2 border-[color:var(--border)] pb-3 last:border-b-0">
      <dt className="px-label">{label}</dt>
      <dd className="mt-1 break-all font-medium">{children}</dd>
    </div>
  );
}
