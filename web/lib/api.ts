import type {
  GameDetail,
  GameMemoryRead,
  GameStateRead,
  GameListItem,
  GameConfigUpdate,
  GameSettingVersionRead,
  ActionOption,
  CharacterRead,
  CharacterListScope,
  CharacterSyncResponse,
  CharacterUpdate,
  ContextDiagnosticRead,
  DeepSeekSettingsRead,
  DeepSeekSettingsUpdate,
  GeneratorChatJobCreateResponse,
  GeneratorChatJobRead,
  GeneratorFinalizeJobCreateResponse,
  GeneratorFinalizeJobRead,
  GameProgressSaveCreate,
  GameProgressSaveRead,
  GameProgressSaveUpdate,
  GeneratedGameConfig,
  GeneratorChatResponse,
  GeneratorJobStreamEvent,
  GeneratorMessage,
  StateDeltaRead,
  SummaryRebuildResponse,
  TurnJobCreateResponse,
  TurnJobStreamEvent,
  TurnJobRead,
  TurnRead,
  SettingModule,
  ModuleMergePreview
} from "@/lib/types";

export function getApiBaseUrl(): string {
  return "";
}

type ApiErrorBody = {
  detail?: unknown;
};

async function requestJson<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers
    },
    cache: "no-store"
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.detail) {
        message = formatApiErrorDetail(body.detail);
      }
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

async function requestFormJson<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    body,
    cache: "no-store"
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as ApiErrorBody;
      if (payload.detail) {
        message = formatApiErrorDetail(payload.detail);
      }
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

async function requestVoid(path: string, options: RequestInit = {}): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: {
      ...options.headers
    },
    cache: "no-store"
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.detail) {
        message = formatApiErrorDetail(body.detail);
      }
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }
}

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String(item.msg);
        }
        return JSON.stringify(item);
      })
      .join("；");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return String(detail);
}

function filenameFromContentDisposition(header: string | null): string {
  if (!header) {
    return "RPGForge-download";
  }
  const encodedMatch = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      return encodedMatch[1];
    }
  }
  const plainMatch = /filename="?([^";]+)"?/i.exec(header);
  return plainMatch?.[1] || "RPGForge-download";
}

export async function getGames(): Promise<GameListItem[]> {
  return requestJson<GameListItem[]>("/api/games");
}

export async function getGame(gameId: string): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}`);
}

export async function deleteGame(gameId: string): Promise<void> {
  return requestVoid(`/api/games/${gameId}`, { method: "DELETE" });
}

export async function getGameProgressSaves(gameId: string): Promise<GameProgressSaveRead[]> {
  return requestJson<GameProgressSaveRead[]>(`/api/games/${gameId}/progress-saves`);
}

export async function createGameProgressSave(
  gameId: string,
  payload: GameProgressSaveCreate
): Promise<GameProgressSaveRead> {
  return requestJson<GameProgressSaveRead>(`/api/games/${gameId}/progress-saves`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateGameProgressSave(
  gameId: string,
  saveId: string,
  payload: GameProgressSaveUpdate
): Promise<GameProgressSaveRead> {
  return requestJson<GameProgressSaveRead>(`/api/games/${gameId}/progress-saves/${saveId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function loadGameProgressSave(
  gameId: string,
  saveId: string
): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}/progress-saves/${saveId}/load`, {
    method: "POST"
  });
}

export async function deleteGameProgressSave(gameId: string, saveId: string): Promise<void> {
  return requestVoid(`/api/games/${gameId}/progress-saves/${saveId}`, {
    method: "DELETE"
  });
}

export async function restartGameProgress(gameId: string): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}/progress/restart`, {
    method: "POST"
  });
}

export async function getGameScriptExport(
  gameId: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/games/${encodeURIComponent(gameId)}/script-export`,
    {
      headers: {
        Accept: "text/markdown"
      },
      cache: "no-store"
    }
  );

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.detail) {
        message = formatApiErrorDetail(body.detail);
      }
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }

  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"))
  };
}

export async function getGameSettingsExport(
  gameId: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/games/${encodeURIComponent(gameId)}/settings-export`,
    {
      headers: {
        Accept: "application/json"
      },
      cache: "no-store"
    }
  );

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.detail) {
        message = formatApiErrorDetail(body.detail);
      }
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }

  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"))
  };
}

export async function getGameSettingsGuideExport(
  gameId: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/games/${encodeURIComponent(gameId)}/settings-guide-export`,
    {
      headers: {
        Accept: "text/markdown"
      },
      cache: "no-store"
    }
  );

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.detail) {
        message = formatApiErrorDetail(body.detail);
      }
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message);
  }

  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"))
  };
}

export async function importGameSettings(
  gameId: string,
  payload: unknown
): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}/settings-import`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getGameMemory(gameId: string): Promise<GameMemoryRead> {
  return requestJson<GameMemoryRead>(`/api/games/${gameId}/memory`);
}

export async function updateGameConfig(
  gameId: string,
  payload: GameConfigUpdate
): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}/config`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function getSettingVersions(gameId: string): Promise<GameSettingVersionRead[]> {
  return requestJson<GameSettingVersionRead[]>(`/api/games/${gameId}/setting-versions`);
}

export async function restoreSettingVersion(
  gameId: string,
  versionId: string
): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}/setting-versions/${versionId}/restore`, {
    method: "POST"
  });
}

export async function getContextDiagnostic(
  gameId: string,
  turnId?: string
): Promise<ContextDiagnosticRead | null> {
  const query = turnId ? `?turn_id=${encodeURIComponent(turnId)}` : "";
  return requestJson<ContextDiagnosticRead | null>(
    `/api/games/${gameId}/context-diagnostic${query}`
  );
}

export async function rebuildGameSummaries(gameId: string): Promise<SummaryRebuildResponse> {
  return requestJson<SummaryRebuildResponse>(
    `/api/games/${gameId}/memory/summaries/rebuild`,
    { method: "POST" }
  );
}

export async function getGameState(gameId: string): Promise<GameStateRead> {
  return requestJson<GameStateRead>(`/api/games/${gameId}/state`);
}

export async function getCharacters(
  gameId: string,
  scope: CharacterListScope = "director"
): Promise<CharacterRead[]> {
  const query = scope === "director" ? "" : `?scope=${scope}`;
  return requestJson<CharacterRead[]>(`/api/games/${gameId}/characters${query}`);
}

export async function syncCharacters(gameId: string): Promise<CharacterSyncResponse> {
  return requestJson<CharacterSyncResponse>(`/api/games/${gameId}/characters/sync`, {
    method: "POST"
  });
}

export async function updateCharacter(
  gameId: string,
  characterId: string,
  payload: CharacterUpdate
): Promise<CharacterRead> {
  return requestJson<CharacterRead>(`/api/games/${gameId}/characters/${characterId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function uploadCharacterPortrait(
  gameId: string,
  characterId: string,
  file: File
): Promise<CharacterRead> {
  const formData = new FormData();
  formData.append("file", file);
  return requestFormJson<CharacterRead>(
    `/api/games/${gameId}/characters/${characterId}/portrait`,
    formData
  );
}

export async function deleteCharacterPortrait(
  gameId: string,
  characterId: string
): Promise<CharacterRead> {
  return requestJson<CharacterRead>(
    `/api/games/${gameId}/characters/${characterId}/portrait`,
    { method: "DELETE" }
  );
}

export async function createManualGame(payload: {
  title: string;
  genre?: string;
  description?: string;
}): Promise<GameDetail> {
  return requestJson<GameDetail>("/api/games", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generatorChat(payload: {
  user_input: string;
  history: GeneratorMessage[];
  confirmed_requirements: Record<string, unknown>;
}): Promise<GeneratorChatResponse> {
  return requestJson<GeneratorChatResponse>("/api/generator/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createGeneratorChatJob(payload: {
  user_input: string;
  history: GeneratorMessage[];
  confirmed_requirements: Record<string, unknown>;
  locked_fields?: string[];
}): Promise<GeneratorChatJobCreateResponse> {
  return requestJson<GeneratorChatJobCreateResponse>("/api/generator/chat-jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getGeneratorChatJob(jobId: string): Promise<GeneratorChatJobRead> {
  return requestJson<GeneratorChatJobRead>(`/api/generator/chat-jobs/${jobId}`);
}

export async function getActiveGeneratorChatJob(): Promise<GeneratorChatJobRead | null> {
  return requestJson<GeneratorChatJobRead | null>("/api/generator/chat-jobs/active");
}

export function createGeneratorChatJobEventSource(jobId: string): EventSource {
  return new EventSource(
    `${getApiBaseUrl()}/api/generator/chat-jobs/${encodeURIComponent(jobId)}/events`
  );
}

export async function generatorFinalize(payload: {
  concept: string;
  history: GeneratorMessage[];
  confirmed_requirements: Record<string, unknown>;
}): Promise<{ config: GeneratedGameConfig; model_used: string }> {
  return requestJson<{ config: GeneratedGameConfig; model_used: string }>(
    "/api/generator/finalize",
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export async function createGeneratorFinalizeJob(payload: {
  concept: string;
  history: GeneratorMessage[];
  confirmed_requirements: Record<string, unknown>;
}): Promise<GeneratorFinalizeJobCreateResponse> {
  return requestJson<GeneratorFinalizeJobCreateResponse>("/api/generator/finalize-jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getGeneratorFinalizeJob(
  jobId: string
): Promise<GeneratorFinalizeJobRead> {
  return requestJson<GeneratorFinalizeJobRead>(`/api/generator/finalize-jobs/${jobId}`);
}

export async function getActiveGeneratorFinalizeJob(): Promise<GeneratorFinalizeJobRead | null> {
  return requestJson<GeneratorFinalizeJobRead | null>("/api/generator/finalize-jobs/active");
}

export function createGeneratorFinalizeJobEventSource(jobId: string): EventSource {
  return new EventSource(
    `${getApiBaseUrl()}/api/generator/finalize-jobs/${encodeURIComponent(jobId)}/events`
  );
}

export function parseGeneratorJobStreamEvent(event: MessageEvent): GeneratorJobStreamEvent {
  return JSON.parse(event.data) as GeneratorJobStreamEvent;
}

export async function createGeneratedGame(
  generatedConfig: GeneratedGameConfig
): Promise<{ game: GameDetail }> {
  return requestJson<{ game: GameDetail }>("/api/generator/create-game", {
    method: "POST",
    body: JSON.stringify({ generated_config: generatedConfig })
  });
}

// 导入外部 AI 写的 story_settings JSON：校验+归一化后返回可预览的 config（不建游戏）。
export async function importScript(
  payload: unknown
): Promise<{ config: GeneratedGameConfig; model_used: string }> {
  return requestJson<{ config: GeneratedGameConfig; model_used: string }>(
    "/api/generator/import-script",
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

// 下载「剧本创作包」Markdown（填写指南 + 完整范例 + AI 指令）。
export async function getAuthoringKit(): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${getApiBaseUrl()}/api/generator/authoring-kit`, {
    headers: { Accept: "text/markdown" },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition"))
  };
}

export async function getTurns(gameId: string): Promise<TurnRead[]> {
  return requestJson<TurnRead[]>(`/api/games/${gameId}/turns`);
}

export type TurnAgentCost = {
  agent: string;
  model: string | null;
  tokens_input: number | null;
  tokens_output: number | null;
  tokens_reasoning: number | null;
  cache_hit_tokens: number | null;
  cache_miss_tokens: number | null;
};

export type TurnInsights = {
  turn_id: string;
  observation: Record<string, unknown> | null;
  action_outcome: Record<string, unknown> | null;
  agents: TurnAgentCost[];
  total_tokens_input: number;
  total_tokens_output: number;
  total_cache_hit_tokens: number;
  total_cache_miss_tokens: number;
  cache_hit_rate: number | null;
};

export async function fetchTurnInsights(
  gameId: string,
  turnId: string
): Promise<TurnInsights> {
  return requestJson<TurnInsights>(`/api/games/${gameId}/turns/${turnId}/insights`);
}

// C6 后悔药：回退到第 toTurn 回合（删除其后回合并重建状态），返回剩余回合列表。
export async function rewindTurns(gameId: string, toTurn: number): Promise<TurnRead[]> {
  return requestJson<TurnRead[]>(`/api/games/${gameId}/turns/rewind`, {
    method: "POST",
    body: JSON.stringify({ to_turn: toTurn })
  });
}

export async function createTurn(
  gameId: string,
  payload:
    | { player_input: string; selected_option?: never }
    | { selected_option: ActionOption; player_input?: never }
): Promise<TurnRead> {
  return requestJson<TurnRead>(`/api/games/${gameId}/turns`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createTurnJob(
  gameId: string,
  payload:
    | { player_input: string; selected_option?: never }
    | { selected_option: ActionOption; player_input?: never }
): Promise<TurnJobCreateResponse> {
  return requestJson<TurnJobCreateResponse>(`/api/games/${gameId}/turns/jobs`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getTurnJob(gameId: string, jobId: string): Promise<TurnJobRead> {
  return requestJson<TurnJobRead>(`/api/games/${gameId}/turns/jobs/${jobId}`);
}

export async function getActiveTurnJob(gameId: string): Promise<TurnJobRead | null> {
  return requestJson<TurnJobRead | null>(`/api/games/${gameId}/turns/jobs/active`);
}

export function createTurnJobEventSource(gameId: string, jobId: string): EventSource {
  return new EventSource(
    `${getApiBaseUrl()}/api/games/${encodeURIComponent(gameId)}/turns/jobs/${encodeURIComponent(
      jobId
    )}/events`
  );
}

export function parseTurnJobStreamEvent(event: MessageEvent): TurnJobStreamEvent {
  return JSON.parse(event.data) as TurnJobStreamEvent;
}

export async function getStateDeltas(
  gameId: string,
  status?: string
): Promise<StateDeltaRead[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return requestJson<StateDeltaRead[]>(`/api/games/${gameId}/state-deltas${query}`);
}

export async function updateStateDelta(
  gameId: string,
  deltaId: string,
  deltaJson: Record<string, unknown>
): Promise<StateDeltaRead> {
  return requestJson<StateDeltaRead>(`/api/games/${gameId}/state-deltas/${deltaId}`, {
    method: "PATCH",
    body: JSON.stringify({ delta_json: deltaJson })
  });
}

export async function approveStateDelta(
  gameId: string,
  deltaId: string
): Promise<GameStateRead> {
  return requestJson<GameStateRead>(
    `/api/games/${gameId}/state-deltas/${deltaId}/approve`,
    { method: "POST" }
  );
}

export async function rejectStateDelta(
  gameId: string,
  deltaId: string
): Promise<StateDeltaRead> {
  return requestJson<StateDeltaRead>(
    `/api/games/${gameId}/state-deltas/${deltaId}/reject`,
    { method: "POST" }
  );
}

export async function getDeepSeekSettings(): Promise<DeepSeekSettingsRead> {
  return requestJson<DeepSeekSettingsRead>("/api/settings/deepseek");
}

export async function updateDeepSeekSettings(
  payload: DeepSeekSettingsUpdate,
  adminToken?: string
): Promise<DeepSeekSettingsRead> {
  return requestJson<DeepSeekSettingsRead>("/api/settings/deepseek", {
    method: "PATCH",
    headers: adminToken ? { "X-Settings-Admin-Token": adminToken } : undefined,
    body: JSON.stringify(payload)
  });
}

// ---------- Admin (telemetry / trace / judge) ----------
// 所有 admin endpoint 需要 X-Settings-Admin-Token header。

export type RecentTurnStats = {
  sample_size: number;
  director_fallback_count: number;
  director_fallback_rate: number;
  rewrite_count: number;
  rewrite_rate: number;
  extractor_failed_count: number;
  extractor_failed_rate: number;
  drift_severity_distribution: Record<string, number>;
  avg_overall_score: number | null;
  evaluations_count: number;
  avg_latency_ms_by_agent: Record<string, number>;
};

export type AgentTraceSummary = {
  id: string;
  job_kind: string | null;
  job_id: string | null;
  agent: string;
  task_type: string;
  model: string | null;
  tokens_input: number | null;
  tokens_output: number | null;
  tokens_reasoning: number | null;
  latency_ms: number;
  status: string;
  error_message: string | null;
  created_at: string;
};

export type AgentTraceDetail = AgentTraceSummary & {
  prompt_messages: Array<{ role: string; content: string }> | null;
  output_text: string | null;
  reasoning_text: string | null;
  extras: Record<string, unknown> | null;
};

function adminHeaders(token: string): HeadersInit {
  return { "X-Settings-Admin-Token": token };
}

export async function fetchRecentTurnStats(
  token: string,
  limit = 100
): Promise<RecentTurnStats> {
  return requestJson<RecentTurnStats>(
    `/api/admin/stats/recent-turns?limit=${limit}`,
    { headers: adminHeaders(token) }
  );
}

export async function fetchRecentTraces(
  token: string,
  params: {
    limit?: number;
    agent?: string;
    status?: string;
    jobKind?: string;
    jobId?: string;
  } = {}
): Promise<AgentTraceSummary[]> {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.agent) query.set("agent", params.agent);
  if (params.status) query.set("status", params.status);
  if (params.jobKind) query.set("job_kind", params.jobKind);
  if (params.jobId) query.set("job_id", params.jobId);
  const qs = query.toString();
  return requestJson<AgentTraceSummary[]>(
    `/api/admin/traces${qs ? `?${qs}` : ""}`,
    { headers: adminHeaders(token) }
  );
}

export async function fetchTraceDetail(
  token: string,
  traceId: string
): Promise<AgentTraceDetail> {
  return requestJson<AgentTraceDetail>(`/api/admin/traces/${traceId}`, {
    headers: adminHeaders(token)
  });
}

export async function fetchTurnJobTraces(
  token: string,
  jobId: string
): Promise<AgentTraceDetail[]> {
  return requestJson<AgentTraceDetail[]>(
    `/api/admin/turn-jobs/${jobId}/traces`,
    { headers: adminHeaders(token) }
  );
}

export type TurnEvaluationRead = {
  id: string;
  turn_id: string;
  game_id: string;
  canon_fidelity: number | null;
  state_consistency: number | null;
  pacing: number | null;
  prose_quality: number | null;
  freshness: number | null;
  safety: number | null;
  overall_score: number | null;
  rationale: Record<string, string> | null;
  judge_model: string | null;
  trace_id: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
};

export async function fetchGameEvaluations(
  token: string,
  gameId: string,
  limit = 100
): Promise<TurnEvaluationRead[]> {
  return requestJson<TurnEvaluationRead[]>(
    `/api/admin/games/${gameId}/evaluations?limit=${limit}`,
    { headers: adminHeaders(token) }
  );
}

export async function triggerTurnEvaluation(
  token: string,
  turnId: string
): Promise<TurnEvaluationRead> {
  return requestJson<TurnEvaluationRead>(
    `/api/admin/turns/${turnId}/evaluate`,
    { method: "POST", headers: adminHeaders(token) }
  );
}

// ---------- 炼金工坊：模块 API ----------

export async function listModules(params: { type?: string; tag?: string; q?: string } = {}): Promise<SettingModule[]> {
  const qs = new URLSearchParams();
  if (params.type) qs.set("type", params.type);
  if (params.tag) qs.set("tag", params.tag);
  if (params.q) qs.set("q", params.q);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return requestJson<SettingModule[]>(`/api/modules${suffix}`);
}

export async function createModule(body: {
  name: string; description?: string | null; module_type: string;
  payload: Record<string, unknown>; tags?: string[]; source_game_id?: string | null;
}): Promise<SettingModule> {
  return requestJson<SettingModule>("/api/modules", { method: "POST", body: JSON.stringify(body) });
}

export async function patchModule(id: string, body: { name?: string; description?: string | null; tags?: string[]; payload?: Record<string, unknown> }): Promise<SettingModule> {
  return requestJson<SettingModule>(`/api/modules/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteModule(id: string): Promise<void> {
  return requestVoid(`/api/modules/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function importModules(file: unknown): Promise<SettingModule[]> {
  return requestJson<SettingModule[]>("/api/modules/import", { method: "POST", body: JSON.stringify(file) });
}

export async function mergePreviewModules(body: {
  target_settings: Record<string, unknown>; module_ids: string[];
  adapt: boolean; conflict_resolutions?: Record<string, string>;
}): Promise<ModuleMergePreview> {
  return requestJson<ModuleMergePreview>("/api/modules/merge-preview", { method: "POST", body: JSON.stringify(body) });
}

export function moduleExportUrl(ids: string[]): string {
  return `${getApiBaseUrl()}/api/modules/export?ids=${encodeURIComponent(ids.join(","))}`;
}

export async function suggestItem(
  gameId: string,
  arrayKey: string,
  draft: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const data = await requestJson<{ fields: Record<string, unknown> }>(
    `/api/games/${gameId}/settings/suggest-item`,
    { method: "POST", body: JSON.stringify({ array_key: arrayKey, draft }) }
  );
  return data.fields ?? {};
}
