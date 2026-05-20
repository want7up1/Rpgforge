export type GameListItem = {
  id: string;
  title: string;
  genre: string | null;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type GameConfigRead = {
  id: string;
  game_id: string;
  system_prompt: string | null;
  worldview: Record<string, unknown>;
  script_outline: Record<string, unknown>;
  generation_settings: GenerationSettings;
  generation_notes: string | null;
  created_at: string;
  updated_at: string;
};

export type GenerationSettings = {
  narrative_target_min_chars?: number;
  narrative_target_max_chars?: number;
  narrative_min_chars?: number;
  paragraph_min?: number;
  paragraph_max?: number;
  scene_heading_max?: number;
  emphasis_min?: number;
  emphasis_max?: number;
  recent_turn_excerpt_chars?: number;
};

export type StoryBlueprintPayload = Record<string, unknown>;

export type AdvancedConfigJsonDraft = {
  worldview_json: Record<string, unknown>;
  script_outline_json: Record<string, unknown>;
};

export type LoreEntryRead = {
  id: string;
  game_id: string;
  title: string;
  type: string | null;
  keywords: string[];
  trigger_words: string[];
  priority: string | null;
  always_on: boolean;
  visibility: string | null;
  public_info: string | null;
  gm_secret: string | null;
  content: string;
  usage_note: string | null;
  is_active: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type LoreEntryMemoryRead = LoreEntryRead & {
  embedding_configured: boolean;
};

export type ModeRead = {
  id: string;
  game_id: string;
  name: string;
  triggers: string[];
  injection: string;
  priority: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type WorldviewUpdate = {
  summary?: string | null;
  tone?: string | null;
  genre?: string | null;
  key_npcs?: string[] | null;
  factions?: string[] | null;
  conflicts?: string[] | null;
};

export type ContractUpdate = {
  premise?: string | null;
  player_fantasy?: string | null;
  central_question?: string | null;
  emotional_arc?: string | null;
  main_goal?: string | null;
  current_act?: string | null;
  narrative_style?: string | null;
  tone?: string | null;
  pacing?: string | null;
  narrative_focus?: string | null;
  canon_terms?: string[] | null;
  key_npcs?: string[] | null;
  key_conflicts?: string[] | null;
  forbidden_drift?: string[] | null;
  forbidden_reveals?: string[] | null;
  must_preserve?: string[] | null;
  must_not_become?: string[] | null;
  guardrails?: string[] | null;
  act_plan?: string[] | null;
};

export type GameConfigUpdate = {
  title?: string | null;
  genre?: string | null;
  description?: string | null;
  system_prompt?: string | null;
  generation_notes?: string | null;
  generation_settings?: GenerationSettings | null;
  worldview?: WorldviewUpdate | null;
  worldview_json?: Record<string, unknown> | null;
  script_outline_json?: Record<string, unknown> | null;
  campaign_contract?: ContractUpdate | null;
  director_contract?: ContractUpdate | null;
  story_contract?: ContractUpdate | null;
};

export type LoreEntryCreate = {
  title: string;
  type?: string | null;
  keywords?: string[];
  trigger_words?: string[];
  priority?: string | null;
  always_on?: boolean;
  visibility?: string | null;
  public_info?: string | null;
  gm_secret?: string | null;
  content: string;
  usage_note?: string | null;
};

export type LoreEntryUpdate = Partial<LoreEntryCreate> & {
  is_active?: boolean;
};

export type ModeCreate = {
  name: string;
  triggers?: string[];
  injection: string;
  priority?: string | null;
  enabled?: boolean;
};

export type ModeUpdate = Partial<ModeCreate>;

export type GameSettingVersionRead = {
  id: string;
  game_id: string;
  scope: "config" | "lore" | "mode" | string;
  entity_id: string | null;
  action: string;
  snapshot_json: Record<string, unknown>;
  created_at: string;
};

export type GameStateRead = {
  id: string;
  game_id: string;
  current_turn: number;
  state_json: Record<string, unknown>;
  summary: string | null;
  created_at: string;
  updated_at: string;
};

export type SummaryRead = {
  id: string;
  game_id: string;
  type: string;
  range_start_turn: number | null;
  range_end_turn: number | null;
  content: string;
  important_facts: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type CharacterRole = "protagonist" | "npc" | "companion" | "other";
export type CharacterListScope = "director" | "public";

export type CharacterStoryProfile = {
  dramatic_function: string;
  desire: string;
  fear: string;
  leverage: string;
  relationship_arc: string;
  public_limit: string;
};

export type CharacterRead = {
  id: string;
  game_id: string;
  name: string;
  aliases: string[];
  role: CharacterRole;
  identity: string | null;
  description: string | null;
  appearance: string | null;
  story_profile: CharacterStoryProfile;
  portrait_prompt: string | null;
  portrait_url: string | null;
  portrait_thumb_url: string | null;
  portrait_mime_type: string | null;
  portrait_thumb_mime_type: string | null;
  portrait_original_filename: string | null;
  portrait_uploaded_at: string | null;
  visibility: "visible" | "hidden";
  is_visible: boolean;
  source: string;
  created_at: string;
  updated_at: string;
};

export type CharacterUpdate = {
  name?: string;
  aliases?: string[];
  role?: CharacterRole;
  identity?: string | null;
  description?: string | null;
  appearance?: string | null;
  story_profile?: CharacterStoryProfile;
  portrait_prompt?: string | null;
  visibility?: "visible" | "hidden";
  is_visible?: boolean;
};

export type CharacterSyncResponse = {
  total: number;
  created: number;
  updated: number;
  characters: CharacterRead[];
};

export type StateDeltaStatus = "pending" | "edited" | "approved" | "rejected";

export type StateDeltaRead = {
  id: string;
  game_id: string;
  turn_id: string;
  delta_json: Record<string, unknown>;
  status: StateDeltaStatus;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DeepSeekSettingsRead = {
  api_key_configured: boolean;
  api_key_masked: string | null;
  api_key_source: "database" | "environment" | "missing";
  base_url: string;
  flash_model: string;
  pro_model: string;
  task_model_routes: Record<string, "flash" | "pro">;
  settings_protected: boolean;
};

export type DeepSeekSettingsUpdate = {
  api_key?: string;
  clear_api_key?: boolean;
  base_url?: string;
  flash_model?: string;
  pro_model?: string;
  task_model_routes?: Record<string, "flash" | "pro">;
};

export type ActionOption = {
  key: "A" | "B" | "C" | "D";
  label: string;
};

export type TurnRead = {
  id: string;
  game_id: string;
  turn_number: number;
  player_input: string;
  gm_output: string;
  visible_summary: string | null;
  hidden_summary: string | null;
  state_delta_json: Record<string, unknown>;
  action_options_json: ActionOption[];
  model_used: string | null;
  created_at: string;
};

export type TurnJobStatus = "pending" | "running" | "completed" | "failed";
export type TurnJobMaintenanceStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped";

export type TurnJobCreateResponse = {
  id: string;
  status: TurnJobStatus;
};

export type TurnJobRead = {
  id: string;
  game_id: string;
  status: TurnJobStatus;
  turn: TurnRead | null;
  turn_id: string | null;
  model_used: string | null;
  error_message: string | null;
  reasoning_content: string;
  content_buffer: string;
  narrative_buffer: string;
  progress_message: string | null;
  stage: string | null;
  stage_label: string | null;
  stage_index: number;
  stage_total: number;
  stage_started_at: string | null;
  maintenance_status: TurnJobMaintenanceStatus;
  maintenance_stage: string | null;
  maintenance_message: string | null;
  maintenance_error: string | null;
  maintenance_started_at: string | null;
  maintenance_completed_at: string | null;
  stream_started_at: string | null;
  last_event_at: string | null;
};

export type TurnJobStreamEvent = {
  type: "snapshot" | "delta" | "progress" | "completed" | "failed" | "heartbeat";
  job_id?: string;
  sent_at?: string;
  terminal?: boolean;
  job?: TurnJobRead;
  status?: TurnJobStatus;
  model_used?: string | null;
  progress_message?: string | null;
  stage?: string | null;
  stage_label?: string | null;
  stage_index?: number;
  stage_total?: number;
  stage_started_at?: string | null;
  reasoning_delta?: string;
  content_delta?: string;
  reset_buffers?: boolean;
  reasoning_length?: number;
  content_length?: number;
  narrative_buffer?: string;
  narrative_length?: number;
  last_event_at?: string | null;
};

export type GameDetail = GameListItem & {
  config: GameConfigRead | null;
  state: GameStateRead | null;
  lore_entries: LoreEntryRead[];
  modes: ModeRead[];
  summaries: SummaryRead[];
  turns: TurnRead[];
};

export type LoreDiagnosticRead = {
  id: string;
  title: string;
  type: string | null;
  priority: string | null;
  always_on: boolean;
  keywords: string[];
  trigger_words: string[];
  usage_note: string | null;
  score: number | null;
  keyword_score: number | null;
  vector_score: number | null;
  matched_terms: string[];
};

export type ContextDiagnosticRead = {
  turn_id: string | null;
  turn_number: number | null;
  player_input: string;
  selected_mode: ModeRead | null;
  recent_turn_numbers: number[];
  memory_summaries: Record<string, unknown>;
  campaign_contract: Record<string, unknown>;
  story_blueprint: StoryBlueprintPayload;
  always_on_lore: LoreDiagnosticRead[];
  related_lore: LoreDiagnosticRead[];
};

export type GameMemoryRead = {
  game: GameListItem;
  current_turn: number;
  turn_count: number;
  lore_entries: LoreEntryMemoryRead[];
  summaries: SummaryRead[];
};

export type LoreReindexResponse = {
  total: number;
  updated: number;
};

export type SummaryRebuildResponse = {
  total: number;
  summaries: SummaryRead[];
};

export type GameProgressSaveRead = {
  id: string;
  game_id: string;
  name: string;
  note: string | null;
  state_current_turn: number;
  turn_count: number;
  summary_count: number;
  created_at: string;
  updated_at: string;
};

export type GameProgressSaveCreate = {
  name: string;
  note?: string | null;
};

export type GameProgressSaveUpdate = {
  name?: string | null;
  note?: string | null;
};

export type GeneratorMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ConfirmedRequirements = {
  story_background: string;
  core_premise: string;
  must_include: string[];
  forbidden_content: string[];
  playstyle_preferences: string[];
  tone_preferences: string[];
  raw_user_input: string;
};

export type GeneratorChatResponse = {
  stage: "interview" | "ready_to_generate";
  confirmed_requirements: Record<string, unknown>;
  missing_questions: string[];
  assistant_reply: string;
  model_used: string;
};

export type GeneratorChatJobStatus = "pending" | "running" | "completed" | "failed";

export type GeneratorChatJobCreateResponse = {
  id: string;
  status: GeneratorChatJobStatus;
};

export type GeneratorChatJobRead = {
  id: string;
  status: GeneratorChatJobStatus;
  response: GeneratorChatResponse | null;
  model_used: string | null;
  error_message: string | null;
  reasoning_content: string;
  content_buffer: string;
  progress_message: string | null;
  stream_started_at: string | null;
  last_event_at: string | null;
};

export type GeneratorFinalizeJobStatus = "pending" | "running" | "completed" | "failed";

export type GeneratorFinalizeJobCreateResponse = {
  id: string;
  status: GeneratorFinalizeJobStatus;
};

export type GeneratorFinalizeJobRead = {
  id: string;
  status: GeneratorFinalizeJobStatus;
  config: GeneratedGameConfig | null;
  model_used: string | null;
  error_message: string | null;
  reasoning_content: string;
  content_buffer: string;
  progress_message: string | null;
  stream_started_at: string | null;
  last_event_at: string | null;
};

export type GeneratorJobStreamEvent = {
  type: "snapshot" | "progress" | "completed" | "failed" | "heartbeat";
  job_id?: string;
  sent_at?: string;
  terminal?: boolean;
  job?: GeneratorChatJobRead | GeneratorFinalizeJobRead;
};

export type GeneratedLoreEntry = {
  title: string;
  type: string;
  keywords: string[];
  trigger_words: string[];
  priority: string;
  always_on: boolean;
  visibility: string;
  public_info: string;
  gm_secret: string;
  content: string;
  usage_note: string;
};

export type GeneratedMode = {
  name: string;
  triggers: string[];
  injection: string;
  priority: string;
  enabled: boolean;
};

export type GeneratedGameConfig = {
  title: string;
  genre: string | null;
  description: string | null;
  system_prompt: string;
  worldview: Record<string, unknown>;
  script_outline: Record<string, unknown>;
  generation_notes: string;
  characters?: Record<string, unknown>[];
  lore_entries: GeneratedLoreEntry[];
  modes: GeneratedMode[];
  initial_state: Record<string, unknown>;
  voice_profiles?: Record<string, unknown>[];
};
