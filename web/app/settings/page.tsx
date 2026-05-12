"use client";

import { FormEvent, type ReactNode, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { getDeepSeekSettings, updateDeepSeekSettings } from "@/lib/api";
import type { DeepSeekSettingsRead } from "@/lib/types";

const adminTokenStorageKey = "rpgforge.settingsAdminToken";
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
    label: "世界导演总纲",
    description: "先锁定剧本承诺、专有名词和分块生成锚点。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_characters",
    label: "角色档案生成",
    description: "生成主角、关键 NPC、关系定位、公开介绍和外貌描述。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_lore_entries",
    label: "世界书生成",
    description: "生成核心规则、地点、势力、秘密和触发词。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_modes",
    label: "模式注入生成",
    description: "生成主线、调查、社交、探索等场景模式。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_initial_state",
    label: "初始状态生成",
    description: "生成开局状态、能力、经验、关系和可见线索。",
    defaultSlot: "pro"
  },
  {
    key: "generator_finalize_rules",
    label: "系统规则生成",
    description: "生成本局 GM 规则、输出约束和生成说明。",
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
    description: "从剧情结果中提取状态变化、XP、技能和关系事件。",
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

export default function SettingsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [adminToken, setAdminToken] = useState(() =>
    typeof window === "undefined" ? "" : localStorage.getItem(adminTokenStorageKey) ?? ""
  );
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [flashModel, setFlashModel] = useState("deepseek-v4-flash");
  const [proModel, setProModel] = useState("deepseek-v4-pro");
  const [taskModelRoutes, setTaskModelRoutes] = useState<Record<string, ModelSlot>>(
    defaultTaskModelRoutes
  );
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const settings = await getDeepSeekSettings();
        if (!controller.signal.aborted) {
          setBaseUrl(settings.base_url);
          setFlashModel(settings.flash_model);
          setProModel(settings.pro_model);
          setTaskModelRoutes(normalizeTaskModelRoutes(settings.task_model_routes));
          setState({ status: "ready", settings });
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setState({
            status: "error",
            message: caught instanceof Error ? caught.message : "设置读取失败。"
          });
        }
      }
    }

    load();

    return () => controller.abort();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }

    setPending(true);
    setMessage(null);
    try {
      const updated = await updateDeepSeekSettings(
        {
          api_key: apiKey.trim() || undefined,
          clear_api_key: clearApiKey,
          base_url: baseUrl.trim(),
          flash_model: flashModel.trim(),
          pro_model: proModel.trim(),
          task_model_routes: taskModelRoutes
        },
        adminToken.trim() || undefined
      );
      if (adminToken.trim()) {
        localStorage.setItem(adminTokenStorageKey, adminToken.trim());
      }
      setApiKey("");
      setClearApiKey(false);
      setState({ status: "ready", settings: updated });
      setMessage("DeepSeek 配置已保存，新的生成和回合请求会立即使用。");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      setPending(false);
    }
  }

  return (
    <AppShell>
      <section className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold sm:text-3xl">设置</h1>
        <p className="max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
          这里保存运行时模型配置。浏览器只访问当前 Web 端口，后端由 Docker 内网代理。
        </p>
      </section>

      {state.status === "loading" ? (
        <section className="app-card app-card-pad text-sm text-[color:var(--muted)]">
          正在读取设置...
        </section>
      ) : state.status === "error" ? (
        <section className="app-alert">{state.message}</section>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <form
            className="app-card app-card-pad"
            onSubmit={handleSubmit}
          >
            <div className="grid gap-4">
              {state.settings.settings_protected ? (
                <label className="grid gap-2">
                  <span className="text-sm font-semibold">设置管理 Token</span>
                  <input
                    className="app-input"
                    onChange={(event) => setAdminToken(event.target.value)}
                    placeholder="SETTINGS_ADMIN_TOKEN"
                    type="password"
                    value={adminToken}
                  />
                </label>
              ) : (
                <div className="app-alert">
                  当前未配置 SETTINGS_ADMIN_TOKEN。生产环境会禁止保存设置；外网部署必须配置强 Token
                  并放在认证反代后。
                </div>
              )}

              <label className="grid gap-2">
                <span className="text-sm font-semibold">DeepSeek API Key</span>
                <input
                  className="app-input"
                  disabled={clearApiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="留空表示不修改现有 Key"
                  type="password"
                  value={apiKey}
                />
              </label>

              <label className="flex items-center gap-2 text-sm">
                <input
                  checked={clearApiKey}
                  onChange={(event) => setClearApiKey(event.target.checked)}
                  type="checkbox"
                />
                清空数据库中保存的 API Key
              </label>

              <label className="grid gap-2">
                <span className="text-sm font-semibold">Base URL</span>
                <input
                  className="app-input"
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder="https://api.deepseek.com"
                  value={baseUrl}
                />
              </label>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-2">
                  <span className="text-sm font-semibold">Flash 模型槽位</span>
                  <input
                    className="app-input"
                    onChange={(event) => setFlashModel(event.target.value)}
                    value={flashModel}
                  />
                </label>
                <label className="grid gap-2">
                  <span className="text-sm font-semibold">Pro 模型槽位</span>
                  <input
                    className="app-input"
                    onChange={(event) => setProModel(event.target.value)}
                    value={proModel}
                  />
                </label>
              </div>

              <section className="grid gap-3 border-t border-[color:var(--border)] pt-4">
                <div>
                  <h2 className="text-lg font-semibold">模型职责分配</h2>
                  <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
                    每个步骤选择使用 Flash 或 Pro 槽位。槽位对应的实际模型名由上方输入框决定。
                  </p>
                </div>
                <div className="grid gap-3">
                  {taskRouteRows.map((row) => (
                    <ModelRouteControl
                      flashModel={flashModel}
                      key={row.key}
                      onChange={(slot) =>
                        setTaskModelRoutes((current) => ({
                          ...current,
                          [row.key]: slot
                        }))
                      }
                      proModel={proModel}
                      row={row}
                      slot={taskModelRoutes[row.key] ?? row.defaultSlot}
                    />
                  ))}
                </div>
              </section>

              {message ? (
                <div className="app-status">
                  {message}
                </div>
              ) : null}

              <button
                className="app-button app-button-primary"
                disabled={pending || !flashModel.trim() || !proModel.trim()}
                type="submit"
              >
                {pending ? "保存中..." : "保存 DeepSeek 配置"}
              </button>
            </div>
          </form>

          <aside className="app-card app-card-pad">
            <h2 className="text-lg font-semibold">当前状态</h2>
            <dl className="mt-4 grid gap-3 text-sm">
              <StatusRow label="API Key">
                {state.settings.api_key_configured
                  ? state.settings.api_key_masked
                  : "未配置"}
              </StatusRow>
              <StatusRow label="Key 来源">{state.settings.api_key_source}</StatusRow>
              <StatusRow label="Base URL">
                {state.settings.base_url || "https://api.deepseek.com"}
              </StatusRow>
              <StatusRow label="Flash">{state.settings.flash_model}</StatusRow>
              <StatusRow label="Pro">{state.settings.pro_model}</StatusRow>
              <StatusRow label="职责分配">
                <div className="grid gap-2">
                  {taskRouteRows.map((row) => {
                    const slot =
                      state.settings.task_model_routes[row.key] ?? row.defaultSlot;
                    return (
                      <div
                        className="flex flex-wrap items-center justify-between gap-2"
                        key={row.key}
                      >
                        <span>{row.label}</span>
                        <span className="app-pill">
                          {slotLabel(slot)} · {slot === "pro" ? state.settings.pro_model : state.settings.flash_model}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </StatusRow>
              <StatusRow label="保存保护">
                {state.settings.settings_protected ? "已启用" : "未启用"}
              </StatusRow>
            </dl>
          </aside>
        </div>
      )}
    </AppShell>
  );
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
    <article className="rounded border border-[color:var(--border)] p-3">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="min-w-0">
          <h3 className="font-semibold">{row.label}</h3>
          <p className="mt-1 text-sm leading-6 text-[color:var(--muted)]">
            {row.description}
          </p>
          <p className="mt-1 break-all text-xs text-[color:var(--muted)]">
            当前实际模型：{activeModel || "未填写"}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            className={slot === "flash" ? "app-button app-button-primary" : "app-button"}
            onClick={() => onChange("flash")}
            type="button"
          >
            Flash
          </button>
          <button
            className={slot === "pro" ? "app-button app-button-primary" : "app-button"}
            onClick={() => onChange("pro")}
            type="button"
          >
            Pro
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
  return slot === "pro" ? "Pro" : "Flash";
}

function StatusRow({
  children,
  label
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="border-b border-[color:var(--border)] pb-3 last:border-b-0">
      <dt className="text-[color:var(--muted)]">{label}</dt>
      <dd className="mt-1 break-all font-medium">{children}</dd>
    </div>
  );
}
