import type {
  GameDetail,
  GameMemoryRead,
  GameStateRead,
  GameListItem,
  ActionOption,
  CharacterRead,
  CharacterSyncResponse,
  CharacterUpdate,
  ContextDiagnosticRead,
  DeepSeekSettingsRead,
  DeepSeekSettingsUpdate,
  GeneratorChatJobCreateResponse,
  GeneratorChatJobRead,
  GeneratorFinalizeJobCreateResponse,
  GeneratorFinalizeJobRead,
  GeneratedGameConfig,
  GeneratorChatResponse,
  GeneratorJobStreamEvent,
  GeneratorMessage,
  StateDeltaRead,
  LoreReindexResponse,
  SummaryRebuildResponse,
  TurnJobCreateResponse,
  TurnJobStreamEvent,
  TurnJobRead,
  TurnRead
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

export async function getGames(): Promise<GameListItem[]> {
  return requestJson<GameListItem[]>("/api/games");
}

export async function getGame(gameId: string): Promise<GameDetail> {
  return requestJson<GameDetail>(`/api/games/${gameId}`);
}

export async function deleteGame(gameId: string): Promise<void> {
  return requestVoid(`/api/games/${gameId}`, { method: "DELETE" });
}

export async function getGameMemory(gameId: string): Promise<GameMemoryRead> {
  return requestJson<GameMemoryRead>(`/api/games/${gameId}/memory`);
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

export async function reindexGameLore(gameId: string): Promise<LoreReindexResponse> {
  return requestJson<LoreReindexResponse>(`/api/games/${gameId}/memory/lore/reindex`, {
    method: "POST"
  });
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

export async function getCharacters(gameId: string): Promise<CharacterRead[]> {
  return requestJson<CharacterRead[]>(`/api/games/${gameId}/characters`);
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
}): Promise<GeneratorChatJobCreateResponse> {
  return requestJson<GeneratorChatJobCreateResponse>("/api/generator/chat-jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getGeneratorChatJob(jobId: string): Promise<GeneratorChatJobRead> {
  return requestJson<GeneratorChatJobRead>(`/api/generator/chat-jobs/${jobId}`);
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

export async function getTurns(gameId: string): Promise<TurnRead[]> {
  return requestJson<TurnRead[]>(`/api/games/${gameId}/turns`);
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
