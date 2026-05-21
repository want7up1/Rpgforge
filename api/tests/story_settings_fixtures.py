from copy import deepcopy

from app.schemas.generator import GeneratedGameConfig


def story_settings_payload() -> dict:
    return {
        "format_version": "rpgforge.story.v2",
        "game_profile": {
            "title": "雁回镇旧案",
            "genre": "黑暗武侠",
            "description": "失忆镖师追查义庄旧案。",
            "tone": "冷峻悬疑",
            "logline": "雨夜义庄的一串泥痕，把失忆镖师拖回旧案中心。",
        },
        "worldview": {
            "summary": "雁回镇靠山临水，义庄旧案多年未结，黑伞客在雨夜重新现身。",
            "setting": "雁回镇义庄",
            "public_facts": ["镇外旧义庄多年无人敢近。"],
            "hidden_facts": ["义庄暗藏旧案账册。"],
            "core_conflicts": ["旧案证据被各方争夺。"],
            "factions": ["雁回镇捕房", "黑伞会"],
            "locations": ["雁回镇义庄", "[地点]"],
        },
        "story_core": {
            "premise": "失忆镖师沈砚追查义庄旧案。",
            "core_fantasy": "以调查、江湖人情和危险抉择撬开旧案。",
            "central_mystery": "沈砚失忆前到底护送了什么？",
            "main_goal": "查清义庄旧案。",
            "emotional_arc": "从孤立疑惧走向主动承担真相代价。",
            "narrative_style": "克制、细节密集、不给超自然答案。",
            "current_act": "act_1",
            "must_preserve": ["雨夜义庄"],
            "must_not_become": ["不要修仙"],
            "forbidden_drift": ["不要修仙"],
            "canon_terms": ["雁回镇", "义庄", "黑伞客陆沉舟"],
        },
        "core_characters": [
            {
                "id": "shen_yan",
                "name": "沈砚",
                "aliases": [],
                "role": "protagonist",
                "identity": "失忆镖师",
                "description": "追查义庄旧案的主角。",
                "appearance": "旧青色短打，右手缠着褪色布带。",
                "portrait_prompt": "",
                "visibility": "visible",
                "dramatic_function": "被旧案牵引的调查主角",
                "desire": "找回失去的记忆",
                "fear": "发现自己才是旧案凶手",
                "leverage": "对义庄铃声有生理反应",
                "relationship_arc": "从孤身追查到重新信任同伴",
                "public_limit": "不能提前公开旧案真凶",
            },
            {
                "id": "lu_chenzhou",
                "name": "陆沉舟",
                "aliases": [],
                "role": "npc",
                "identity": "黑伞客",
                "description": "常在雨夜出现的外乡人。",
                "appearance": "黑伞遮面，袖口有旧账房墨痕。",
                "portrait_prompt": "",
                "visibility": "visible",
                "dramatic_function": "线索守门人",
                "desire": "拿回义庄账册",
                "fear": "旧案牵连到自己家族",
                "leverage": "对账册下落过度敏感",
                "relationship_arc": "从对立试探到被迫合作",
                "public_limit": "不会主动承认知道账册",
            },
        ],
        "act_plan": [
            {
                "id": "act_1",
                "title": "义庄夜雨",
                "objective": "找到旧案第一条线索。",
                "dramatic_question": "沈砚能否证明自己不是旧案帮凶？",
                "pressure": "黑伞客也在寻找同一条线索。",
                "must_hit_beats": ["检查门槛泥痕", "确认黑伞客到过义庄"],
                "allowed_reveals": ["旧案仍有人遮掩"],
                "forbidden_reveals": ["账册真凶"],
                "relationship_turn": "沈砚开始怀疑陆沉舟另有目的。",
                "escalation_limit": "只允许推进到义庄线索层，不引入终局门派战争。",
                "completion_anchors": [
                    {
                        "id": "act_1_find_mud",
                        "title": "找到门槛泥痕",
                        "required": True,
                        "description": "确认有人近期翻入义庄。",
                        "completion_signal": "发现门槛内侧的新鲜泥痕。",
                    },
                    {
                        "id": "act_1_identify_black_umbrella",
                        "title": "确认黑伞客踪迹",
                        "required": True,
                        "description": "确认黑伞客陆沉舟与义庄有关。",
                        "completion_signal": "找到黑伞客留下的伞骨划痕或目击证词。",
                    },
                ],
                "transition_to_next_act": {
                    "target_act": "act_2",
                    "condition": "两个义庄锚点完成，玩家决定追查黑伞客。",
                    "transition_style": "雨夜追踪",
                },
            },
            {
                "id": "act_2",
                "title": "黑伞追踪",
                "objective": "查明陆沉舟为何寻找义庄账册。",
                "dramatic_question": "陆沉舟是敌人，还是被旧案胁迫的证人？",
                "pressure": "捕房开始封锁义庄线索。",
                "must_hit_beats": ["追踪陆沉舟", "找到账册残页"],
                "allowed_reveals": ["账册与捕房旧人有关"],
                "forbidden_reveals": ["最终主谋身份"],
                "relationship_turn": "沈砚与陆沉舟形成脆弱合作。",
                "escalation_limit": "只揭露账册残页，不揭露最终主谋。",
                "completion_anchors": [
                    {
                        "id": "act_2_find_page",
                        "title": "找到账册残页",
                        "required": True,
                        "description": "拿到能指向下一幕的实物证据。",
                        "completion_signal": "获得义庄账册残页。",
                    }
                ],
                "transition_to_next_act": {},
            },
        ],
        "main_quest_path": [
            {
                "id": "main_quest_1",
                "act_id": "act_1",
                "title": "查明义庄泥痕",
                "objective": "找到旧案第一条线索。",
                "player_visible": "调查义庄异常痕迹。",
                "completion_signal": "发现门槛内侧的新鲜泥痕。",
                "optional": False,
            },
            {
                "id": "main_quest_2",
                "act_id": "act_2",
                "title": "追踪黑伞客",
                "objective": "弄清陆沉舟寻找账册的理由。",
                "player_visible": "顺着黑伞客留下的线索追查。",
                "completion_signal": "获得义庄账册残页。",
                "optional": False,
            },
        ],
        "core_mechanics": [
            {
                "id": "investigation",
                "name": "调查推进",
                "rule": "给线索不给答案，隐藏真相必须通过可观察痕迹逐步揭露。",
                "progression": "完成锚点后才允许切换下一幕。",
                "visibility": "public",
            }
        ],
        "action_style_rules": [
            {
                "id": "main_story",
                "name": "主线推进",
                "triggers": ["主线", "推进", "追查"],
                "rule": "围绕当前幕目标推进，但不强迫玩家离开当前场景。",
                "priority": "high",
                "enabled": True,
            },
            {
                "id": "investigation",
                "name": "调查行动",
                "triggers": ["调查", "检查", "线索", "搜索"],
                "rule": "提供可验证线索和代价，不直接泄露隐藏真相。",
                "priority": "critical",
                "enabled": True,
            },
            {
                "id": "social",
                "name": "社交试探",
                "triggers": ["询问", "交涉", "试探"],
                "rule": "让 NPC 通过语气、回避和交换条件透露信息。",
                "priority": "medium",
                "enabled": True,
            },
        ],
        "story_material_library": [
            {
                "id": "yizhuang",
                "title": "雁回镇义庄",
                "type": "location",
                "keywords": ["义庄", "泥痕", "棺木"],
                "triggers": ["义庄", "泥痕", "棺木"],
                "priority": "critical",
                "always_on": True,
                "visibility": "mixed",
                "public_info": "镇外旧义庄多年无人敢近。",
                "gm_secret": "义庄暗藏旧案账册。",
                "content": "义庄是第一幕核心地点，门槛泥痕和棺木旁伞骨划痕指向陆沉舟。",
                "usage": "玩家调查义庄、泥痕或棺木时注入，不直接说出账册真凶。",
                "enabled": True,
            },
            {
                "id": "lu_chenzhou_material",
                "title": "黑伞客陆沉舟",
                "type": "npc",
                "keywords": ["黑伞客", "陆沉舟", "黑伞"],
                "triggers": ["黑伞", "陆沉舟", "雨夜"],
                "priority": "high",
                "always_on": False,
                "visibility": "mixed",
                "public_info": "常持黑伞的外乡人。",
                "gm_secret": "陆沉舟知道义庄旧案账册的下落。",
                "content": "陆沉舟与义庄旧案有关，会在雨夜接近旧义庄寻找账册。",
                "usage": "玩家提到黑伞、陆沉舟或雨夜时注入。",
                "enabled": True,
            },
        ],
        "home_base": {
            "id": "home_base",
            "name": "[地点]",
            "role": "休整、情报整理与关系推进据点。",
            "public_functions": ["整理线索", "修整装备"],
            "hidden_hooks": ["基地旧档案中夹有义庄账页拓印。"],
            "upgrade_paths": ["情报室", "医药间"],
            "npc_services": ["老账房协助辨认字迹"],
            "scene_uses": ["回合间总结线索"],
        },
        "hard_rules": {
            "must_follow": ["每回合输出玩家可见剧情，并给出 A/B/C/D 四个具体行动选项。"],
            "must_not": ["不要修仙", "不要提前揭露账册真凶"],
            "reveal_rules": ["隐藏真相只能通过线索逐步揭露。"],
            "continuity_rules": ["人物动机和地点状态必须保持一致。"],
            "gm_output_rules": ["正文不输出状态结算。"],
        },
        "generation_parameters": {
            "narrative_target_min_chars": 800,
            "narrative_target_max_chars": 1200,
            "narrative_min_chars": 700,
            "paragraph_min": 3,
            "paragraph_max": 6,
            "scene_heading_max": 1,
            "emphasis_min": 2,
            "emphasis_max": 4,
            "recent_turn_excerpt_chars": 420,
        },
    }


def initial_state_payload() -> dict:
    return {
        "current_turn": 0,
        "time": {"current": "秋末，雨夜", "pressure": "黑伞客也在接近义庄"},
        "location": {
            "current": "雁回镇义庄",
            "known_locations": ["雁回镇义庄", "[地点]"],
        },
        "protagonist": {
            "name": "沈砚",
            "identity": "失忆镖师",
            "appearance": "旧青色短打，右手缠着褪色布带。",
            "attributes": {},
        },
        "progression": {
            "level": 1,
            "xp": 0,
            "next_level_xp": 100,
            "total_xp": 0,
            "xp_log": [],
        },
        "skills": [],
        "abilities": [],
        "conditions": [],
        "relationships": [],
        "inventory": [],
        "quests": [],
        "npcs": [],
        "factions": [],
        "variables": {},
        "known_facts": ["镇外旧义庄多年无人敢近。"],
        "hidden_facts": ["义庄暗藏旧案账册。"],
        "open_threads": ["确认泥痕来源"],
        "story_progress": {
            "current_act": "act_1",
            "completed_acts": [],
            "completed_anchors": [],
            "ready_for_next_act": False,
            "last_advance_turn": None,
            "last_advance_reason": "",
            "act_history": [],
            "anchor_history": [],
        },
    }


def build_generated_config() -> GeneratedGameConfig:
    return GeneratedGameConfig(
        title="雁回镇旧案",
        genre="黑暗武侠",
        description="失忆镖师追查义庄旧案。",
        story_settings=story_settings_payload(),
        initial_state=initial_state_payload(),
    )


def build_two_act_config() -> GeneratedGameConfig:
    return build_generated_config()


def copied_story_settings() -> dict:
    return deepcopy(story_settings_payload())
