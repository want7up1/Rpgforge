import json

import anyio

from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.services.deepseek_client import ChatCompletionResult
from app.services.game_creator import create_game_from_config
from app.services.gameplay import GameplayService
from app.services.prompt_builder import PromptBuilder
from app.services.state_applier import apply_state_delta
from app.services.state_extractor import StateExtractor
from app.services.state_rebuilder import rebuild_game_state
from app.services.state_v2 import normalize_state_v2
from app.services.story_director import StoryDirector, StoryDirectorDecision
from app.services.story_settings import (
    build_runtime_story,
    completion_anchor_ids_for_act,
    retrieve_story_materials,
    select_action_style,
)
from app.services.turn_maintenance_jobs import _apply_delta
from tests.story_settings_fixtures import build_generated_config, build_two_act_config


def test_prompt_injects_story_settings_runtime_view_and_materials(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=1,
            player_input="我检查门槛。",
            gm_output="门槛内侧有新鲜泥痕。" * 80,
            visible_summary="发现义庄泥痕。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[{"key": "A", "label": "继续调查泥痕"}],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.commit()
    db_session.refresh(game)

    selected_style = select_action_style(game.config, "我调查义庄门槛的新鲜泥痕。")
    materials = retrieve_story_materials(
        game.config,
        player_input="我调查义庄门槛的新鲜泥痕。",
        selected_action_style=selected_style,
        state_json=game.state.state_json,
        recent_turns=list(game.turns),
    )

    messages = PromptBuilder().build_runtime_messages(
        game=game,
        player_input="我调查义庄门槛的新鲜泥痕。",
        selected_action_style=selected_style,
        recent_turns=list(game.turns),
        related_materials=materials,
        summaries={"long_term": "长期记忆：义庄旧案仍未结。"},
    )
    runtime_payload = json.loads(messages[1]["content"])

    assert "runtime_story" in runtime_payload
    assert "script_outline" not in runtime_payload
    assert "campaign_contract" not in runtime_payload
    assert "related_lore" not in runtime_payload
    assert runtime_payload["runtime_story"]["story_core"]["main_goal"] == "查清义庄旧案。"
    assert runtime_payload["runtime_story"]["current_act"]["id"] == "act_1"
    assert runtime_payload["selected_action_style"]["id"] == "investigation"
    assert [item["title"] for item in runtime_payload["related_story_materials"]][0] == "雁回镇义庄"
    assert runtime_payload["generation_parameters"]["recent_turn_excerpt_chars"] == 420
    # Round 45：最近回合改附完整正文（gm_output）供 GM 承接，不再下发冗余的 gm_output_excerpt 前缀。
    assert runtime_payload["recent_turns"][0]["gm_output"].startswith("门槛内侧有新鲜泥痕。")
    assert "gm_output_excerpt" not in runtime_payload["recent_turns"][0]


def test_gm_prompt_redacts_future_act_spoilers(db_session) -> None:
    """GM 输入只应看到当前幕；next_act 与未来幕主线节点的剧透细节必须被裁掉。"""
    game = create_game_from_config(db_session, build_generated_config())

    messages = PromptBuilder().build_runtime_messages(
        game=game,
        player_input="我检查义庄门槛。",
        selected_action_style=None,
        recent_turns=[],
    )
    runtime_story = json.loads(messages[1]["content"])["runtime_story"]

    # next_act 只保留 id + title，删除 objective/dramatic_question/allowed_reveals/anchors。
    next_act = runtime_story["next_act"]
    assert next_act == {"id": "act_2", "title": "黑伞追踪"}

    # 未来幕（act_2）主线节点只保留 id/title/act_id；剧透字段被裁。
    quests = {q["id"]: q for q in runtime_story["main_quest_path"]}
    future_quest = quests["main_quest_2"]
    assert set(future_quest.keys()) == {"id", "title", "act_id"}
    assert "objective" not in future_quest
    assert "player_visible" not in future_quest
    # 当前幕（act_1）主线节点保留全文。
    assert quests["main_quest_1"]["player_visible"] == "调查义庄异常痕迹。"

    # 未来幕的剧透措辞不应出现在 GM 的 runtime_story 里。
    blob = json.dumps(runtime_story, ensure_ascii=False)
    assert "最终主谋身份" not in blob
    assert "弄清陆沉舟寻找账册的理由" not in blob


def test_gm_system_prompt_elevates_hard_constraints(db_session) -> None:
    """硬红线必须从深层 JSON 提升到 system prompt，提高模型遵守权重。"""
    game = create_game_from_config(db_session, build_generated_config())

    messages = PromptBuilder().build_runtime_messages(
        game=game,
        player_input="我检查义庄门槛。",
        selected_action_style=None,
        recent_turns=[],
    )
    system_content = messages[0]["content"]

    assert "本剧本不可违反的强约束" in system_content
    # 「必须落实」组：正向强约束（玩家"想看却没看到"的部分）。
    assert "本回合/本幕必须落实" in system_content
    # hard_rules.must_follow
    assert "每回合输出玩家可见剧情，并给出 A/B/C/D 四个具体行动选项。" in system_content
    # hard_rules.reveal_rules
    assert "隐藏真相只能通过线索逐步揭露。" in system_content
    # hard_rules.continuity_rules
    assert "人物动机和地点状态必须保持一致。" in system_content
    # hard_rules.gm_output_rules
    assert "正文不输出状态结算。" in system_content
    # 当前幕目标
    assert "本幕目标：找到旧案第一条线索。" in system_content
    # core_mechanics 规则
    assert "给线索不给答案" in system_content
    # 「绝对禁止」组：hard_rules.must_not
    assert "绝对禁止（违反即判失败）" in system_content
    assert "不要提前揭露账册真凶" in system_content
    # story_core.canon_terms
    assert "黑伞客陆沉舟" in system_content
    # story_core.must_not_become
    assert "不要修仙" in system_content
    # 当前幕 forbidden_reveals
    assert "账册真凶" in system_content
    # Round 44：篇幅指引改为软目标（去硬下限/去 emphasis 配额，防注水/假加粗）
    assert "本回合输出篇幅指引" in system_content
    assert "按信息量自然成文" in system_content  # 篇幅按事件量自然成文
    assert "让位于剧本" in system_content  # 详细描写场景仍优先写完整

    # Round 45：叙事工艺层提进 system，且排在「当前幕简报」（唯一缓存断裂点）之前 → 稳定前缀。
    assert "本剧本叙事工艺" in system_content
    assert "叙事文风" in system_content
    assert system_content.index("本剧本叙事工艺") < system_content.index("当前幕简报")
    # 工艺字段已在 system，不在 user payload 的 story_core 重复下发（去重省 token）。
    user_story_core = json.loads(messages[1]["content"])["runtime_story"]["story_core"]
    assert "narrative_style" not in user_story_core
    assert user_story_core["main_goal"]  # 非工艺字段仍保留


def test_narrative_craft_directives_render_and_noop() -> None:
    """工艺层：有字段时渲染、全空时 no-op（不污染 system / prefix cache）。"""
    from app.services.prompt_builder import _narrative_craft_directives

    rendered = _narrative_craft_directives(
        {"story_core": {"narrative_style": "冷峻克制", "tone_do": ["留白", "克制"]}}
    )
    assert "本剧本叙事工艺" in rendered
    assert "冷峻克制" in rendered
    assert "留白" in rendered
    assert _narrative_craft_directives({"story_core": {}}) == ""
    assert _narrative_craft_directives({}) == ""


def test_state_ops_projection_keeps_minimal_drops_writing_fields() -> None:
    """StateExtractor/Compressor 投影：保留状态运算所需字段，砍掉写作向 context。"""
    from app.services.story_settings import project_runtime_story_for_state_ops

    runtime_story = {
        "format_version": "rpgforge.story.v2",
        "current_act": {"id": "act_1", "completion_anchors": [{"id": "a1"}]},
        "next_act": {
            "id": "act_2",
            "title": "黑伞追踪",
            "objective": "长剧透文本",
            "completion_anchors": [1, 2, 3],
        },
        "story_core": {"canon_terms": ["雁回镇"], "main_goal": "查案"},
        "story_progress": {"current_act": "act_1"},
        "main_quest_path": [{"id": "mq1", "act_id": "act_1", "title": "查泥痕"}],
        "core_characters": [
            {
                "id": "c1",
                "name": "陆沉舟",
                "aliases": ["黑伞客"],
                "role": "antagonist",
                "fear": "秘密暴露",
                "leverage": "账册",
                "appearance": "黑衣",
                "desire": "复仇",
                "identity": "真凶",
            }
        ],
        "worldview": {"hidden_facts": ["x"], "summary": "很长的世界观"},
        "core_mechanics": [{"name": "调查", "rule": "给线索不给答案"}],
        "hard_rules": {"must_follow": ["写满字数"], "must_not": ["x"]},
        "home_base": {"name": "义庄"},
    }
    projected = project_runtime_story_for_state_ops(runtime_story)

    # 保留状态运算必需字段。
    assert projected["current_act"]["completion_anchors"] == [{"id": "a1"}]
    assert projected["story_core"]["canon_terms"] == ["雁回镇"]
    assert projected["main_quest_path"][0]["title"] == "查泥痕"
    assert projected["story_progress"]["current_act"] == "act_1"
    # next_act 瘦成 id+title（细节剧透/锚点用不上）。
    assert projected["next_act"] == {"id": "act_2", "title": "黑伞追踪"}
    # core_characters 瘦成 name/id/aliases/role 索引，砍掉写作内幕。
    assert projected["core_characters"] == [
        {"id": "c1", "name": "陆沉舟", "aliases": ["黑伞客"], "role": "antagonist"}
    ]
    # 写作向 context 完全砍掉。
    for dropped in ("worldview", "core_mechanics", "hard_rules", "home_base"):
        assert dropped not in projected


def test_action_style_and_material_retrieval_use_story_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())

    selected = select_action_style(game.config, "我检查黑伞客留下的伞骨划痕。")
    results = retrieve_story_materials(
        game.config,
        player_input="我检查黑伞客留下的伞骨划痕。",
        selected_action_style=selected,
        state_json=game.state.state_json,
        recent_turns=[],
    )

    assert selected["name"] == "调查行动"
    titles = [result.material["title"] for result in results]
    assert "雁回镇义庄" in titles
    assert "黑伞客陆沉舟" in titles


def test_runtime_story_only_exposes_current_act_open_anchors(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    runtime_story = build_runtime_story(game.config, game.state.state_json)

    assert completion_anchor_ids_for_act(game.config, "act_1") == [
        "act_1_find_mud",
        "act_1_identify_black_umbrella",
    ]
    assert runtime_story["current_act"]["id"] == "act_1"
    assert [anchor["id"] for anchor in runtime_story["current_act"]["completion_anchors"]] == [
        "act_1_find_mud",
        "act_1_identify_black_umbrella",
    ]
    assert runtime_story["next_act"]["id"] == "act_2"

    state = dict(game.state.state_json)
    state["story_progress"] = {
        **state["story_progress"],
        "completed_anchors": ["act_1_find_mud"],
    }
    runtime_story = build_runtime_story(game.config, state)

    assert [anchor["id"] for anchor in runtime_story["current_act"]["completion_anchors"]] == [
        "act_1_identify_black_umbrella"
    ]


def test_state_delta_advances_act_only_after_required_anchors(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    state = game.state

    first_turn = Turn(game_id=game.id, turn_number=1, player_input="", gm_output="")
    first_state = apply_state_delta(
        state,
        first_turn,
        {
            "story_progress_update": {
                "completed_anchor": "act_1_find_mud",
                "completed_act": "act_1",
                "next_act": "act_2",
                "reason": "发现门槛泥痕。",
            }
        },
    )
    assert first_state["story_progress"]["current_act"] == "act_1"
    assert first_state["story_progress"]["ready_for_next_act"] is False
    assert first_state["story_progress"]["completed_acts"] == []

    state.state_json = first_state
    second_turn = Turn(game_id=game.id, turn_number=2, player_input="", gm_output="")
    second_state = apply_state_delta(
        state,
        second_turn,
        {
            "story_progress_update": {
                "completed_anchor": "act_1_identify_black_umbrella",
                "completed_act": "act_1",
                "next_act": "act_2",
                "advance_reason": "确认黑伞客踪迹。",
            }
        },
    )

    assert second_state["story_progress"]["current_act"] == "act_2"
    assert second_state["story_progress"]["completed_acts"] == ["act_1"]
    assert second_state["story_progress"]["last_advance_turn"] == 2


def test_state_delta_backfills_required_anchor_and_derives_main_quests(db_session) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "[据点]立足",
            "objective": "建立可运转的基地。",
            "completion_anchors": [
                {
                    "id": "act_1_base_secured",
                    "title": "建立[地点]",
                    "required": True,
                    "description": "清剿雷达站并建立基础防御。",
                    "completion_signal": (
                        "[地点]废弃雷达站清剿完成，基础防御工事建立，[地点]初步成型。"
                    ),
                },
                {
                    "id": "act_1_supply_secured",
                    "title": "确保基础物资",
                    "required": True,
                    "description": "完成基地初期物资储备。",
                    "completion_signal": "基地三月食物储备达成。",
                },
            ],
            "transition_to_next_act": {"target_act": "act_2"},
        },
        {
            "id": "act_2",
            "title": "北方线索",
            "objective": "追查研究所线索。",
            "completion_anchors": [],
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "建立[地点]",
            "objective": "让雷达站成为可用据点。",
            "player_visible": "完成清剿、防御和物资整理。",
            "completion_signal": "[地点]初步成型。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_2",
            "title": "追查北方研究所",
            "objective": "确认下一阶段行动目标。",
            "player_visible": "从基地出发追踪北方线索。",
            "completion_signal": "确认北方研究所入口。",
            "optional": False,
        },
        {
            "id": "main_quest_3",
            "act_id": "act_3",
            "title": "揭开终局真相",
            "objective": "进入最终阶段。",
            "player_visible": "等待前置线索成熟。",
            "completion_signal": "终局真相浮现。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点]主楼",
            "known_locations": ["[地点]废弃雷达站", "[地点]主楼"],
        },
        "known_facts": [
            "[地点]废弃雷达站清剿完成，基础防御工事建立，[地点]初步成型。",
            "[地点]在主楼内完成幸存者安置和布局确认。",
        ],
        "quests": [{"id": "side_rescue", "title": "安置幸存者", "status": "active"}],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=3, player_input="", gm_output=""),
        {
            "story_progress_update": {
                "completed_anchor": "act_1_supply_secured",
                "reason": "基地三月食物储备达成。",
            }
        },
    )

    progress = next_state["story_progress"]
    assert progress["current_act"] == "act_2"
    assert progress["completed_acts"] == ["act_1"]
    assert progress["ready_for_next_act"] is False
    assert progress["last_advance_turn"] == 3
    assert "act_1_base_secured" in progress["completed_anchors"]
    assert "act_1_supply_secured" in progress["completed_anchors"]

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "completed"
    assert quests["main_quest_1"]["name"] == "建立[地点]"
    assert quests["main_quest_2"]["status"] == "active"
    assert quests["main_quest_3"]["status"] == "hidden"
    assert quests["side_rescue"]["status"] == "active"

    quest_log = next_state["v2"]["quest_log"]
    assert [quest["name"] for quest in quest_log["completed"]] == ["建立[地点]"]
    assert [quest["name"] for quest in quest_log["active"]][:2] == [
        "追查北方研究所",
        "安置幸存者",
    ]
    assert [quest["name"] for quest in quest_log["hidden"]] == ["揭开终局真相"]

    state.state_json = next_state
    stable_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=4, player_input="", gm_output=""),
        {},
    )
    stable_quests = {
        quest["id"]: quest for quest in stable_state["quests"] if isinstance(quest, dict)
    }
    assert stable_quests["main_quest_1"]["status"] == "completed"
    assert stable_quests["main_quest_2"]["status"] == "active"
    assert stable_quests["main_quest_3"]["status"] == "hidden"


def test_state_delta_completes_main_quest_from_completed_anchor_history(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_3",
            "title": "工业园决战",
            "objective": "完成当前幕核心冲突。",
            "completion_anchors": [
                {
                    "id": "act_3_gu_devotion",
                    "title": "角色A臣服",
                    "required": True,
                    "completion_signal": "角色A首次臣服，主角[能力]完全觉醒。",
                },
                {
                    "id": "act_3_brotherhood_destroyed",
                    "title": "[组织]瓦解",
                    "required": True,
                    "completion_signal": "[组织]势力瓦解，铁狼败走。",
                },
            ],
        }
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_7",
            "act_id": "act_3",
            "title": "征服角色A",
            "objective": "击败并收服角色A。",
            "player_visible": "角色A仍是当前冲突中心。",
            "completion_signal": "角色A首次臣服，主角[能力]觉醒——大范围[异能]。",
            "optional": False,
        },
        {
            "id": "main_quest_8",
            "act_id": "act_3",
            "title": "击溃[组织]",
            "objective": "瓦解[组织]剩余势力。",
            "player_visible": "[组织]仍在工业园周边活动。",
            "completion_signal": "[组织]势力瓦解，铁狼败走。",
            "optional": False,
        },
        {
            "id": "main_quest_9",
            "act_id": "act_3",
            "title": "追踪广播信号",
            "objective": "锁定叶汐瑶信号。",
            "player_visible": "广播信号还没有锁定。",
            "completion_signal": "叶汐瑶广播信号被稳定锁定。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_3",
            "completed_acts": ["act_1", "act_2"],
            "completed_anchors": ["act_3_gu_devotion"],
            "ready_for_next_act": False,
            "anchor_history": [
                {
                    "turn": 60,
                    "act": "act_3",
                    "anchor_id": "act_3_gu_devotion",
                    "reason": "角色A首次臣服，[能力]完全觉醒。",
                }
            ],
        },
        "quests": [
            {"id": "main_quest_7", "title": "征服角色A", "status": "active"},
            {"id": "main_quest_8", "title": "击溃[组织]", "status": "active"},
            {"id": "main_quest_9", "title": "追踪广播信号", "status": "active"},
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=61, player_input="", gm_output=""),
        {},
    )

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_7"]["status"] == "completed"
    assert quests["main_quest_8"]["status"] == "active"
    assert quests["main_quest_9"]["status"] == "hidden"
    assert next_state["story_progress"]["current_act"] == "act_3"
    assert next_state["story_progress"]["ready_for_next_act"] is False


def test_state_delta_uses_configured_anchor_evidence_across_genres(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_court",
            "title": "御前密案",
            "objective": "查明账册缺页和密令来源。",
            "completion_anchors": [
                {
                    "id": "act_court_edict_verified",
                    "title": "验明密令",
                    "required": True,
                    "completion_signal": "御前密令已经验明，内廷账册缺页被追回。",
                },
                {
                    "id": "act_court_witness_safe",
                    "title": "护送证人",
                    "required": True,
                    "completion_signal": "证人安全抵达东偏殿。",
                },
            ],
        }
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_court",
            "title": "验明御前密令",
            "objective": "确认密令真伪并追回账册缺页。",
            "player_visible": "账册缺页仍是御前密案的关键。",
            "completion_signal": "御前密令已经验明，账册缺页追回。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_court",
            "title": "护送东偏殿证人",
            "objective": "确保证人安全。",
            "player_visible": "证人还没有抵达东偏殿。",
            "completion_signal": "证人安全抵达东偏殿。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_court",
            "completed_anchors": ["act_court_edict_verified"],
            "ready_for_next_act": False,
            "anchor_history": [
                {
                    "turn": 12,
                    "act": "act_court",
                    "anchor_id": "act_court_edict_verified",
                    "reason": "御前密令已经验明，内廷账册缺页被追回。",
                }
            ],
        },
        "quests": [
            {"id": "main_quest_1", "title": "验明御前密令", "status": "active"},
            {"id": "main_quest_2", "title": "护送东偏殿证人", "status": "active"},
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=13, player_input="", gm_output=""),
        {},
    )

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "completed"
    assert quests["main_quest_2"]["status"] == "active"
    assert next_state["story_progress"]["current_act"] == "act_court"
    assert next_state["story_progress"]["ready_for_next_act"] is False


def test_state_delta_infers_anchor_from_completion_signal_phrase(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_4",
            "title": "通讯塔求援",
            "objective": "追踪广播信号并确认求援者。",
            "completion_anchors": [
                {
                    "id": "act_4_ye_found",
                    "title": "找到角色B",
                    "required": True,
                    "description": "抵达通讯塔顶并确认求援者身份。",
                    "completion_signal": (
                        "追踪广播信号至研究所顶部，发现角色B独自一人在通讯塔广播求援。"
                    ),
                },
                {
                    "id": "act_4_ye_awakening",
                    "title": "角色B音波异能觉醒",
                    "required": True,
                    "description": "角色B的音波异能失控爆发。",
                    "completion_signal": "角色B音波异能觉醒，震碎周围玻璃。",
                },
            ],
            "transition_to_next_act": {"target_act": "act_5"},
        },
        {
            "id": "act_5",
            "title": "后续阶段",
            "objective": "等待全部锚点完成后进入。",
            "completion_anchors": [],
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_10",
            "act_id": "act_4",
            "title": "追踪广播信号",
            "objective": "找到正在广播求援的人。",
            "player_visible": "广播信号仍需要确认来源。",
            "completion_signal": (
                "追踪广播信号至研究所顶部，发现角色B独自一人在通讯塔广播求援。"
            ),
            "optional": False,
        },
        {
            "id": "main_quest_11",
            "act_id": "act_4",
            "title": "稳定角色B的音波异能",
            "objective": "处理音波异能失控风险。",
            "player_visible": "角色B的能力还没有稳定。",
            "completion_signal": "角色B音波异能觉醒，震碎周围玻璃。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {"current": "[地点]·通讯塔塔顶"},
        "known_facts": [
            # 整串包含 act_4_ye_found / main_quest_10 的 completion_signal（整短语高精度命中，
            # 非脆弱 semantic 碎片）；ye_awakening 的 signal 未出现 → 不完成。
            "追踪广播信号至研究所顶部，发现角色B独自一人在通讯塔广播求援。",
        ],
        "npcs": [
            {
                "name": "角色B",
                "location": "[地点]·通讯塔塔顶",
                "status": "音波异能潜力开始显现，但还没有爆发。",
            }
        ],
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_4",
            "completed_acts": ["act_1", "act_2", "act_3"],
            "completed_anchors": [],
            "ready_for_next_act": False,
        },
        "quests": [
            {"id": "main_quest_10", "title": "追踪广播信号", "status": "active"},
            {"id": "main_quest_11", "title": "稳定角色B的音波异能", "status": "hidden"},
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=78, player_input="", gm_output=""),
        {},
    )

    completed_anchors = next_state["story_progress"]["completed_anchors"]
    assert "act_4_ye_found" in completed_anchors
    assert "act_4_ye_awakening" not in completed_anchors
    assert next_state["story_progress"]["current_act"] == "act_4"
    assert next_state["story_progress"]["ready_for_next_act"] is False

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_10"]["status"] == "completed"
    assert quests["main_quest_11"]["status"] == "active"


def test_state_delta_completes_quest_from_anchor_with_equivalent_action(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_4",
            "title": "研究所探索",
            "objective": "获取地下层实验资料。",
            "completion_anchors": [
                {
                    "id": "act_4_lab_discovery",
                    "title": "实验资料发现",
                    "required": True,
                    "completion_signal": (
                        "深入研究所地下层发现[组织]基因实验记录、"
                        "[编号]实验体档案、角色C加密研究笔记。"
                    ),
                }
            ],
        }
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_12",
            "act_id": "act_4",
            "title": "探索研究所秘密",
            "objective": "深入研究所地下层获取[组织]实验记录和角色C加密笔记。",
            "player_visible": "研究所深处似乎隐藏着重要线索。",
            "completion_signal": "[编号]实验体档案和角色C加密研究笔记获取。",
            "optional": False,
        }
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_4",
            "completed_anchors": ["act_4_lab_discovery"],
            "ready_for_next_act": False,
        },
        "known_facts": [
            "研究小组读取[编号]实验体档案，解读角色C加密研究笔记。"
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=79, player_input="", gm_output=""),
        {},
    )

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_12"]["status"] == "completed"


def test_state_delta_does_not_complete_anchor_from_split_history(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_4",
            "title": "研究所探索",
            "objective": "确认三名同伴是否都参与探索。",
            "completion_anchors": [
                {
                    "id": "act_4_three_heroines_collab",
                    "title": "三人协作",
                    "required": True,
                    "completion_signal": (
                        "角色D、角色F、角色A在研究所探索中各贡献独特能力协助。"
                    ),
                }
            ],
        }
    ]
    config.story_settings["main_quest_path"] = []
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "known_facts": [
            "角色D和角色F在研究所探索中提供协助。",
            "角色A仍在城外营地待命。",
        ],
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_4",
            "completed_anchors": [],
            "ready_for_next_act": False,
        },
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=86, player_input="", gm_output=""),
        {},
    )

    assert "act_4_three_heroines_collab" not in next_state["story_progress"][
        "completed_anchors"
    ]
    assert next_state["story_progress"]["ready_for_next_act"] is False


def test_state_delta_does_not_stick_or_infer_future_main_quest_completion(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "当前阶段",
            "objective": "完成当前阶段目标。",
            "completion_anchors": [],
            "transition_to_next_act": {"target_act": "act_2"},
        },
        {
            "id": "act_2",
            "title": "未来加冕",
            "objective": "等待当前阶段结束后再处理。",
            "completion_anchors": [],
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "完成当前调查",
            "objective": "继续当前调查。",
            "player_visible": "当前调查还没有结束。",
            "completion_signal": "当前调查完成。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_2",
            "title": "完成未来加冕",
            "objective": "未来阶段才会发生。",
            "player_visible": "未来阶段尚未开始。",
            "completion_signal": "王冠在旧大厅被放入库房，众臣宣誓待命。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "known_facts": [
            "王冠在旧大厅被放入库房。",
            "众臣宣誓待命。",
        ],
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_1",
            "completed_acts": [],
            "completed_anchors": [],
            "ready_for_next_act": False,
        },
        "quests": [
            {
                "id": "main_quest_2",
                "title": "完成未来加冕",
                "status": "completed",
                "source": "main_quest_path",
            }
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=87, player_input="", gm_output=""),
        {},
    )

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "active"
    assert quests["main_quest_2"]["status"] == "hidden"


def test_state_delta_restores_current_act_from_later_completed_anchor(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_departure",
            "title": "启航准备",
            "objective": "完成远航前的基础准备。",
            "completion_anchors": [
                {
                    "id": "act_departure_hull_checked",
                    "title": "检修船体",
                    "required": True,
                    "completion_signal": "主桅和船体完成检修。",
                },
                {
                    "id": "act_departure_supplies_loaded",
                    "title": "装载补给",
                    "required": True,
                    "completion_signal": "六周淡水和干粮已经装船。",
                },
            ],
            "transition_to_next_act": {"target_act": "act_chart"},
        },
        {
            "id": "act_chart",
            "title": "海图线索",
            "objective": "找出灯塔航道。",
            "completion_anchors": [
                {
                    "id": "act_chart_found",
                    "title": "找到海图",
                    "required": True,
                    "completion_signal": "失落海图被拼合，灯塔航道浮现。",
                },
            ],
            "transition_to_next_act": {"target_act": "act_lighthouse"},
        },
        {
            "id": "act_lighthouse",
            "title": "灯塔危机",
            "objective": "处理灯塔海域的最终威胁。",
            "completion_anchors": [
                {
                    "id": "act_lighthouse_beacon_lit",
                    "title": "点亮灯塔",
                    "required": True,
                    "completion_signal": "灯塔主火重新点亮。",
                },
                {
                    "id": "act_lighthouse_fleet_defeated",
                    "title": "击退舰队",
                    "required": True,
                    "completion_signal": "黑帆舰队撤离礁环。",
                },
            ],
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_departure",
            "title": "完成启航准备",
            "objective": "让船队具备出港条件。",
            "player_visible": "船体和补给仍要确认。",
            "completion_signal": "主桅和船体完成检修，六周淡水和干粮已经装船。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_chart",
            "title": "拼合失落海图",
            "objective": "确认灯塔航道。",
            "player_visible": "海图碎片还未拼合。",
            "completion_signal": "失落海图被拼合，灯塔航道浮现。",
            "optional": False,
        },
        {
            "id": "main_quest_3",
            "act_id": "act_lighthouse",
            "title": "点亮灯塔主火",
            "objective": "恢复灯塔指引。",
            "player_visible": "灯塔主火仍然熄灭。",
            "completion_signal": "灯塔主火重新点亮。",
            "optional": False,
        },
        {
            "id": "main_quest_4",
            "act_id": "act_lighthouse",
            "title": "击退黑帆舰队",
            "objective": "解除灯塔海域威胁。",
            "player_visible": "黑帆舰队仍在礁环外集结。",
            "completion_signal": "黑帆舰队撤离礁环。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_departure",
            "completed_acts": [],
            "completed_anchors": [
                "act_departure_supplies_loaded",
                "act_chart_found",
                "act_lighthouse_beacon_lit",
            ],
            "ready_for_next_act": False,
            "anchor_history": [
                {
                    "turn": 4,
                    "act": "act_chart",
                    "anchor_id": "act_chart_found",
                    "reason": "失落海图被拼合，灯塔航道浮现。",
                },
                {
                    "turn": 5,
                    "act": "act_lighthouse",
                    "anchor_id": "act_lighthouse_beacon_lit",
                    "reason": "灯塔主火重新点亮。",
                },
            ],
        },
        "quests": [
            {"id": "main_quest_1", "title": "完成启航准备", "status": "active"},
            {"id": "main_quest_2", "title": "拼合失落海图", "status": "active"},
            {"id": "main_quest_3", "title": "点亮灯塔主火", "status": "active"},
            {"id": "main_quest_4", "title": "击退黑帆舰队", "status": "hidden"},
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=6, player_input="", gm_output=""),
        {},
    )

    progress = next_state["story_progress"]
    assert progress["current_act"] == "act_lighthouse"
    assert progress["completed_acts"] == ["act_departure", "act_chart"]
    assert progress["ready_for_next_act"] is False
    assert "act_departure_hull_checked" not in progress["completed_anchors"]
    assert "act_lighthouse_fleet_defeated" not in progress["completed_anchors"]

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "completed"
    assert quests["main_quest_2"]["status"] == "completed"
    assert quests["main_quest_3"]["status"] == "completed"
    assert quests["main_quest_4"]["status"] == "active"


def test_state_delta_advances_ready_act_from_next_act_activity(db_session) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "基地成型",
            "objective": "完成基地建设。",
            "completion_anchors": [
                {
                    "id": "act_1_ready",
                    "title": "基地成型",
                    "required": True,
                    "completion_signal": "基地完成建设。",
                }
            ],
            "transition_to_next_act": {"target_act": "act_2"},
        },
        {
            "id": "act_2",
            "title": "医疗救援",
            "objective": "探索废弃医院并救援幸存者。",
            "completion_anchors": [
                {
                    "id": "act_2_hospital_rescue",
                    "title": "医院救援",
                    "required": True,
                    "completion_signal": "废弃医院救援完成。",
                }
            ],
            "transition_to_next_act": {"target_act": "act_3"},
        },
        {
            "id": "act_3",
            "title": "后续阶段",
            "objective": "等待后续推进。",
            "completion_anchors": [],
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "完成基地建设",
            "objective": "完成第一阶段据点建设。",
            "player_visible": "让基地进入可用状态。",
            "completion_signal": "基地完成建设。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_2",
            "title": "角色D能力训练",
            "objective": "训练角色D对周围情绪的感知。",
            "player_visible": "角色D需要稳定掌握情绪感知。",
            "completion_signal": "角色D情绪感知稳定。",
            "optional": False,
        },
        {
            "id": "main_quest_3",
            "act_id": "act_2",
            "title": "救援医院幸存者",
            "objective": "探索废弃医院，寻找幸存者与医疗物资。",
            "player_visible": "废弃医院中可能还有幸存者，且医疗物资对基地至关重要。",
            "completion_signal": "废弃医院救援完成。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {"current": "废弃医院一楼大厅及药房"},
        "known_facts": [
            "废弃医院一楼发现近期人类活动痕迹。",
            "药房内仍有可用医疗物资。",
            "楼上传来轻微响动，可能有幸存者。",
        ],
        "open_threads": [
            {
                "title": "废弃医院求救信号",
                "status": "active",
                "description": "信号来自废弃医院，关键词包含医院、药品、救。",
            }
        ],
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_1",
            "completed_anchors": ["act_1_ready"],
            "ready_for_next_act": True,
        },
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=8, player_input="", gm_output=""),
        {},
    )

    progress = next_state["story_progress"]
    assert progress["current_act"] == "act_2"
    assert progress["completed_acts"] == ["act_1"]
    assert progress["ready_for_next_act"] is False
    assert progress["last_advance_turn"] == 8

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "completed"
    assert quests["main_quest_2"]["status"] == "hidden"
    assert quests["main_quest_3"]["status"] == "active"


def test_state_delta_activates_next_unfinished_current_act_quest(db_session) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "基地成型",
            "objective": "完成基地建设。",
            "completion_anchors": [
                {
                    "id": "act_1_ready",
                    "title": "基地成型",
                    "required": True,
                    "completion_signal": "基地完成建设。",
                }
            ],
            "transition_to_next_act": {"target_act": "act_2"},
        },
        {
            "id": "act_2",
            "title": "医疗救援",
            "objective": "继续完成第二幕目标。",
            "completion_anchors": [
                {
                    "id": "act_2_training",
                    "title": "能力训练",
                    "required": True,
                    "completion_signal": "能力训练完成。",
                },
                {
                    "id": "act_2_hospital_rescue",
                    "title": "医院救援",
                    "required": True,
                    "completion_signal": "医院救援完成。",
                },
                {
                    "id": "act_2_armor",
                    "title": "护甲觉醒",
                    "required": True,
                    "completion_signal": "护甲觉醒完成。",
                },
            ],
            "transition_to_next_act": {"target_act": "act_3"},
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "完成基地建设",
            "objective": "完成第一阶段据点建设。",
            "player_visible": "让基地进入可用状态。",
            "completion_signal": "基地完成建设。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_2",
            "title": "能力训练",
            "objective": "训练同伴能力。",
            "player_visible": "同伴需要稳定掌握新能力。",
            "completion_signal": "能力训练完成。",
            "optional": False,
        },
        {
            "id": "main_quest_3",
            "act_id": "act_2",
            "title": "医院救援",
            "objective": "完成医院救援。",
            "player_visible": "医院救援仍是当前重点。",
            "completion_signal": "医院救援完成。",
            "optional": False,
        },
        {
            "id": "main_quest_4",
            "act_id": "act_2",
            "title": "护甲觉醒",
            "objective": "触发新的防护能力。",
            "player_visible": "新的防护能力还没有觉醒。",
            "completion_signal": "护甲觉醒完成。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {"current": "医院病房"},
        "known_facts": ["医院救援完成，幸存者已经带回基地。"],
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_2",
            "completed_acts": ["act_1"],
            "completed_anchors": ["act_2_hospital_rescue"],
            "ready_for_next_act": False,
        },
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=9, player_input="", gm_output=""),
        {"quest_updates": [{"id": "main_quest_3", "status": "completed"}]},
    )

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "completed"
    assert quests["main_quest_2"]["status"] == "active"
    assert quests["main_quest_3"]["status"] == "completed"
    assert quests["main_quest_4"]["status"] == "hidden"
    assert next_state["story_progress"]["ready_for_next_act"] is False


def test_state_delta_adds_anchor_fallback_when_current_act_quests_are_exhausted(
    db_session,
) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "基地成型",
            "objective": "完成基地建设。",
            "completion_anchors": [
                {
                    "id": "act_1_ready",
                    "title": "基地成型",
                    "required": True,
                    "completion_signal": "基地完成建设。",
                }
            ],
            "transition_to_next_act": {"target_act": "act_2"},
        },
        {
            "id": "act_2",
            "title": "医疗救援",
            "objective": "完成第二幕剩余锚点。",
            "completion_anchors": [
                {
                    "id": "act_2_training",
                    "title": "能力训练",
                    "required": True,
                    "completion_signal": "能力训练完成。",
                },
                {
                    "id": "act_2_hospital_rescue",
                    "title": "医院救援",
                    "required": True,
                    "completion_signal": "医院救援完成。",
                },
                {
                    "id": "act_2_armor",
                    "title": "护甲觉醒",
                    "required": True,
                    "completion_signal": "护甲觉醒完成。",
                },
            ],
            "transition_to_next_act": {"target_act": "act_3"},
        },
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "完成基地建设",
            "objective": "完成第一阶段据点建设。",
            "player_visible": "让基地进入可用状态。",
            "completion_signal": "基地完成建设。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_2",
            "title": "能力训练",
            "objective": "训练同伴能力。",
            "player_visible": "同伴需要稳定掌握新能力。",
            "completion_signal": "能力训练完成。",
            "optional": False,
        },
        {
            "id": "main_quest_3",
            "act_id": "act_2",
            "title": "医院救援",
            "objective": "完成医院救援。",
            "player_visible": "医院救援仍是当前重点。",
            "completion_signal": "医院救援完成。",
            "optional": False,
        },
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_2",
            "completed_acts": ["act_1"],
            "completed_anchors": ["act_2_training", "act_2_hospital_rescue"],
            "ready_for_next_act": False,
        },
        "quests": [
            {"id": "main_quest_1", "title": "完成基地建设", "status": "completed"},
            {"id": "main_quest_2", "title": "能力训练", "status": "completed"},
            {"id": "main_quest_3", "title": "医院救援", "status": "completed"},
            {
                "id": "anchor_quest_act_2_hospital_rescue",
                "title": "医院救援",
                "status": "active",
                "source": "completion_anchor",
            },
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=10, player_input="", gm_output=""),
        {},
    )

    quests = {quest["id"]: quest for quest in next_state["quests"] if isinstance(quest, dict)}
    assert quests["main_quest_1"]["status"] == "completed"
    assert quests["main_quest_2"]["status"] == "completed"
    assert quests["main_quest_3"]["status"] == "completed"
    assert "anchor_quest_act_2_hospital_rescue" not in quests
    assert quests["anchor_quest_act_2_armor"]["status"] == "active"
    assert quests["anchor_quest_act_2_armor"]["source"] == "completion_anchor"
    assert quests["anchor_quest_act_2_armor"]["anchor_id"] == "act_2_armor"
    assert [
        quest["name"]
        for quest in next_state["v2"]["quest_log"]["active"]
    ] == ["护甲觉醒"]


def test_state_delta_resolves_completed_main_quest_threads(db_session) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "开局救援",
            "objective": "完成幸存者救援。",
            "completion_anchors": [],
        }
    ]
    config.story_settings["main_quest_path"] = [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "营救角色D",
            "objective": "在废墟中发现并营救角色D。",
            "player_visible": "附近废墟中似乎有幸存者活动的痕迹。",
            "completion_signal": "成功营救角色D并建立初步信任。",
            "optional": False,
        }
    ]
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_1",
            "completed_acts": ["act_1"],
        },
        "open_threads": [
            {
                "id": "find_white_xiaoyu",
                "title": "发现角色D",
                "status": "active",
                "description": "角色D已成功带回基地。",
            },
            {
                "id": "underground_hidden_chamber",
                "title": "地下仓库隐藏暗格发现",
                "status": "active",
                "description": "暗格仍未完全调查。",
            },
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=11, player_input="", gm_output=""),
        {},
    )

    threads = {thread["id"]: thread for thread in next_state["open_threads"]}
    assert threads["find_white_xiaoyu"]["status"] == "resolved"
    assert threads["underground_hidden_chamber"]["status"] == "active"
    assert [
        thread["title"]
        for thread in next_state["v2"]["open_threads"]["active"]
    ] == ["地下仓库隐藏暗格发现"]


def test_state_delta_resolves_completed_anchor_threads(db_session) -> None:
    config = build_generated_config()
    config.story_settings["act_plan"] = [
        {
            "id": "act_1",
            "title": "遗迹调查",
            "objective": "完成遗迹线索调查。",
            "completion_anchors": [
                {
                    "id": "act_1_hidden_room",
                    "title": "隐藏房间发现",
                    "required": True,
                    "completion_signal": "找到遗迹隐藏房间并记录壁画线索。",
                }
            ],
        }
    ]
    config.story_settings["main_quest_path"] = []
    game = create_game_from_config(db_session, config)
    state = game.state
    state.state_json = {
        **state.state_json,
        "story_progress": {
            **state.state_json["story_progress"],
            "current_act": "act_1",
            "completed_anchors": ["act_1_hidden_room"],
        },
        "open_threads": [
            {
                "id": "act_1_hidden_room",
                "title": "隐藏房间发现",
                "status": "active",
            },
            {
                "id": "south_gate",
                "title": "南门脚印",
                "status": "active",
            },
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=12, player_input="", gm_output=""),
        {},
    )

    threads = {thread["id"]: thread for thread in next_state["open_threads"]}
    assert threads["act_1_hidden_room"]["status"] == "resolved"
    assert threads["south_gate"]["status"] == "active"


def test_state_delta_normalizes_runtime_character_state(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "protagonist": {"name": "未定", "identity": "未定", "attributes": {}},
        "npcs": [
            {
                "name": "无名女性幸存者",
                "status": "alive",
                "location": "废弃医院",
            }
        ],
        "relationships": [
            {
                "npc": "无名女性幸存者",
                "name": "无名女性幸存者",
                "trust": 3,
                "recent_events": [{"reason": "初次安抚"}],
            }
        ],
        "inventory": [
            {"item": "罐头", "unit": "罐", "quantity": 3},
            {"item": "罐头", "unit": "罐", "quantity": 2},
            "工具箱",
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=3, player_input="", gm_output=""),
        {
            "npc_updates": [
                {
                    "id": "无名女性幸存者",
                    "name": "陈雨桐",
                    "location": "[地点]",
                    "attitude": "信任初建",
                }
            ],
            "relationship_events": [
                {
                    "npc": "陈雨桐",
                    "axis": "trust",
                    "direction": "increase",
                    "intensity": "minor",
                    "reason": "自报姓名并接受庇护",
                }
            ],
            "inventory_add": [
                {"item": "罐头", "unit": "罐", "quantity": 5},
                {"item": "绷带", "quantity": 1},
                {"item": "绷带", "quantity": 2},
            ],
        },
    )

    assert next_state["protagonist"]["name"] == "沈砚"
    assert next_state["protagonist"]["identity"] == "失忆镖师"
    assert next_state["npcs"][0]["name"] == "陈雨桐"
    assert "无名女性幸存者" in next_state["npcs"][0]["aliases"]
    assert next_state["v2"]["npc_registry"][0]["name"] == "陈雨桐"
    assert next_state["relationships"][0]["npc"] == "陈雨桐"
    assert next_state["relationships"][0]["trust"] == 6
    assert len(next_state["relationships"]) == 1
    assert {"item": "罐头", "unit": "罐", "quantity": 10} in next_state["inventory"]
    assert {"item": "绷带", "quantity": 3} in next_state["inventory"]


def test_state_delta_merges_thread_updates_and_syncs_source_variables(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "variables": {"source_title": "旧剧本", "source_description": "旧简介"},
        "open_threads": [
            {
                "action": "update",
                "thread": {
                    "id": "hospital_exploration",
                    "title": "废弃医院探索与幸存者发现",
                    "status": "active",
                    "description": "发现幸存者",
                },
            },
            {
                "id": "hospital_exploration",
                "action": "update",
                "thread": {"description": "旧的重复更新"},
            },
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=4, player_input="", gm_output=""),
        {
            "variable_updates": {"source_title": "错误覆盖"},
            "open_thread_updates": [
                {
                    "id": "hospital_exploration",
                    "action": "update",
                    "thread": {"description": "已带回基地"},
                },
                {
                    "action": "add",
                    "thread": {
                        "id": "underground_hidden_chamber",
                        "title": "地下仓库隐藏暗格发现",
                        "description": "发现暗格和生物样品档案",
                    },
                },
                {
                    "action": "resolve",
                    "thread": {
                        "id": "hospital_exploration",
                        "description": "医院线已结束",
                    },
                },
            ],
        },
    )

    assert next_state["variables"]["source_title"] == game.title
    assert next_state["variables"]["source_description"] == game.description
    hospital_threads = [
        thread
        for thread in next_state["open_threads"]
        if thread.get("id") == "hospital_exploration"
    ]
    assert len(hospital_threads) == 1
    assert hospital_threads[0]["status"] == "resolved"
    assert hospital_threads[0]["description"] == "医院线已结束"
    assert any(
        thread.get("id") == "underground_hidden_chamber"
        for thread in next_state["open_threads"]
    )
    assert [
        thread["title"]
        for thread in next_state["v2"]["open_threads"]["active"]
    ] == ["地下仓库隐藏暗格发现"]
    assert [
        thread["title"]
        for thread in next_state["v2"]["open_threads"]["resolved"]
    ] == ["废弃医院探索与幸存者发现"]


def test_state_delta_applies_location_to_and_field_patch_updates(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点]地下仓库",
            "known_locations": ["[地点]地下仓库"],
        },
        "npcs": [
            {
                "name": "陈雨桐",
                "location": "废弃医院一楼放射科",
                "status": "alive",
            }
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=5, player_input="", gm_output=""),
        {
            "location_change": {
                "from": "[地点]地下仓库",
                "to": "[地点]主楼",
            },
            "npc_updates": [
                {
                    "name": "陈雨桐",
                    "field": "location",
                    "new_value": "[地点]主楼客厅",
                },
                {
                    "name": "陈雨桐",
                    "field": "attitude",
                    "value": "参与讨论",
                },
            ],
        },
    )

    assert next_state["location"]["current"] == "[地点]主楼"
    assert "[地点]主楼" in next_state["location"]["known_locations"]
    assert next_state["v2"]["active_scene"]["location"] == "[地点]主楼"
    assert "from" not in next_state["location"]
    assert "to" not in next_state["location"]
    assert "destination" not in next_state["location"]
    assert "name" not in next_state["location"]
    assert len(next_state["npcs"]) == 1
    assert next_state["npcs"][0]["location"] == "[地点]主楼客厅"
    assert next_state["npcs"][0]["attitude"] == "参与讨论"
    assert "field" not in next_state["npcs"][0]
    assert "new_value" not in next_state["npcs"][0]


def test_state_delta_clears_stale_location_movement_fields(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "旧工业园区",
            "from": "[地点]",
            "to": "旧工业园区",
            "destination": "旧目标点",
            "name": "旧地点别名",
            "npc": "旧随行角色",
            "reason": "旧移动原因",
            "known_locations": ["[地点]", "旧工业园区"],
            "region": "[地点]",
        },
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=6, player_input="", gm_output=""),
        {
            "location_change": {
                "from": "旧工业园区",
                "to": "[地点]庭院",
                "destination": "[地点]庭院",
                "name": "[地点]庭院",
                "npc": "角色D",
                "reason": "跟随玩家移动",
                "region": "[地点]",
            }
        },
    )

    assert next_state["location"]["current"] == "[地点]庭院"
    assert next_state["location"]["region"] == "[地点]"
    assert "[地点]庭院" in next_state["location"]["known_locations"]
    assert "from" not in next_state["location"]
    assert "to" not in next_state["location"]
    assert "destination" not in next_state["location"]
    assert "name" not in next_state["location"]
    assert "npc" not in next_state["location"]
    assert "reason" not in next_state["location"]
    assert next_state["v2"]["active_scene"]["location"] == "[地点]庭院"


def test_state_v2_does_not_treat_location_words_as_presence_markers() -> None:
    state = normalize_state_v2(
        {
            "current_turn": 80,
            "location": {"current": "[地点]·通讯塔下"},
            "npcs": [
                {
                    "name": "角色B",
                    "location": "[地点]·通讯塔塔顶",
                    "status": "正在塔顶休息",
                },
                {
                    "name": "主角",
                    "location": "[地点]·通讯塔下",
                },
            ],
        },
        80,
    )

    assert state["v2"]["active_scene"]["present_npcs"] == ["主角"]


def test_state_delta_applies_nested_fields_and_scene_presence(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "废弃医院二楼走廊及右侧第三间病房",
            "known_locations": ["废弃医院二楼走廊及右侧第三间病房"],
        },
        "npcs": [],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=6, player_input="", gm_output=""),
        {
            "npc_updates": [
                {
                    "name": "无名女性幸存者（二楼）",
                    "fields": {
                        "attitude": "恐惧警觉",
                        "location": "废弃医院二楼右侧第三间病房",
                        "condition": "瘦弱，手持手术刀自卫",
                    },
                }
            ]
        },
    )

    npc = next_state["npcs"][0]
    assert npc["location"] == "废弃医院二楼右侧第三间病房"
    assert npc["attitude"] == "恐惧警觉"
    assert npc["status"] == "瘦弱，手持手术刀自卫"
    assert "fields" not in npc
    assert next_state["v2"]["active_scene"]["present_npcs"] == ["无名女性幸存者（二楼）"]
    assert next_state["v2"]["npc_registry"][0]["status"] == "瘦弱，手持手术刀自卫"


def test_state_delta_applies_nested_changes_without_persisting_changes(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点][地点]",
            "known_locations": ["[地点][地点]"],
        },
        "npcs": [
            {
                "id": "无名女性幸存者（二楼）",
                "name": "角色F",
                "aliases": ["无名女性幸存者（二楼）"],
                "location": "废弃医院二楼右侧第三间病房",
                "status": "戒备",
            }
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=7, player_input="", gm_output=""),
        {
            "npc_updates": [
                {
                    "name": "角色F",
                    "changes": {
                        "status": "已加入[地点]",
                        "attitude": "信任初步建立",
                        "location": "[地点][地点]",
                    },
                }
            ]
        },
    )

    npc = next_state["npcs"][0]
    assert npc["location"] == "[地点][地点]"
    assert npc["status"] == "已加入[地点]"
    assert npc["attitude"] == "信任初步建立"
    assert "changes" not in npc
    assert next_state["v2"]["active_scene"]["present_npcs"] == ["角色F"]


def test_state_delta_places_single_brought_npc_at_changed_scene(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点]副楼门口",
            "known_locations": ["[地点]副楼门口"],
        },
        "npcs": [
            {
                "id": "无名女性幸存者（二楼）",
                "name": "角色F",
                "aliases": ["无名女性幸存者（二楼）"],
                "location": "[地点]副楼门口",
                "status": "休息中",
            }
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(
            game_id=game.id,
            turn_number=8,
            player_input="单独带角色F到主堡二层寝宫。",
            gm_output="主角把角色F带到主堡二层寝宫，完成体检后让她休息。",
        ),
        {
            "location_change": "[地点][地点]主堡二层寝宫",
            "npc_updates": [
                {
                    "name": "角色F",
                    "status": "体检后休息",
                }
            ],
        },
    )

    npc = next_state["npcs"][0]
    assert npc["location"] == "[地点][地点]主堡二层寝宫"
    assert next_state["v2"]["active_scene"]["present_npcs"] == ["角色F"]


def test_state_delta_merges_thread_changes_and_resolves_by_title_id(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "open_threads": [
            {
                "title": "废弃医院求救信号",
                "status": "active",
                "description": "收到求救信号",
            },
            {
                "title": "二楼病房幸存者发现",
                "status": "active",
                "description": "发现幸存者",
            },
        ],
    }

    next_state = apply_state_delta(
        state,
        Turn(game_id=game.id, turn_number=8, player_input="", gm_output=""),
        {
            "open_thread_updates": [
                {
                    "id": "二楼病房幸存者发现",
                    "changes": {"description": "身份确认并接受食物"},
                },
                {
                    "id": "废弃医院求救信号",
                    "status": "resolved",
                },
                {
                    "id": "二楼病房幸存者发现",
                    "status": "resolved",
                },
            ]
        },
    )

    threads = next_state["open_threads"]
    assert len(threads) == 2
    assert all("changes" not in thread for thread in threads)
    by_title = {thread["title"]: thread for thread in threads}
    assert by_title["废弃医院求救信号"]["status"] == "resolved"
    assert by_title["二楼病房幸存者发现"]["status"] == "resolved"
    assert by_title["二楼病房幸存者发现"]["description"] == "身份确认并接受食物"
    assert not next_state["v2"]["open_threads"]["active"]
    assert [
        thread["title"]
        for thread in next_state["v2"]["open_threads"]["resolved"]
    ] == ["废弃医院求救信号", "二楼病房幸存者发现"]


def test_state_v2_unwraps_legacy_thread_updates() -> None:
    state = normalize_state_v2(
        {
            "current_turn": 1,
            "open_threads": [
                {
                    "action": "add",
                    "thread": {
                        "id": "underground_hidden_chamber",
                        "title": "地下仓库隐藏暗格发现",
                        "description": "发现暗格",
                    },
                }
            ],
        },
        1,
    )

    assert state["v2"]["open_threads"]["active"][0]["title"] == "地下仓库隐藏暗格发现"


def test_rebuild_game_state_syncs_source_variables(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    game.state.initial_state_json = {
        **game.state.initial_state_json,
        "variables": {"source_title": "旧剧本", "source_description": "旧简介"},
    }
    game.state.state_json = {
        **game.state.state_json,
        "variables": {"source_title": "旧剧本", "source_description": "旧简介"},
    }
    db_session.add(game.state)
    db_session.commit()

    rebuilt_state = rebuild_game_state(db_session, game)

    assert rebuilt_state is not None
    assert rebuilt_state.initial_state_json["variables"]["source_title"] == game.title
    assert rebuilt_state.initial_state_json["variables"]["source_description"] == game.description
    assert rebuilt_state.state_json["variables"]["source_title"] == game.title
    assert rebuilt_state.state_json["variables"]["source_description"] == game.description


def test_create_game_overwrites_stale_initial_source_variables(db_session) -> None:
    config = build_generated_config()
    config.initial_state["variables"] = {
        "source_title": "旧剧本",
        "source_description": "旧简介",
    }

    game = create_game_from_config(db_session, config)

    assert game.state.state_json["variables"]["source_title"] == game.title
    assert game.state.state_json["variables"]["source_description"] == game.description


def test_turn_maintenance_success_clears_previous_extractor_failed_flag(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我检查门槛泥痕。",
        gm_output="门槛内侧有新鲜泥痕。",
        visible_summary="发现门槛泥痕。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.flush()
    job = TurnJob(
        game_id=game.id,
        status="completed",
        request_json={"player_input": turn.player_input},
        turn_id=turn.id,
        maintenance_status="failed",
        maintenance_stage="state_extract",
        extractor_failed=True,
    )
    db_session.add(job)
    db_session.commit()

    _apply_delta(job.id, {"new_known_facts": ["门槛内侧有新鲜泥痕。"]})

    db_session.expire_all()
    saved_job = db_session.get(TurnJob, job.id)
    saved_turn = db_session.get(Turn, turn.id)
    assert saved_job is not None
    assert saved_turn is not None
    assert saved_job.extractor_failed is False
    assert saved_turn.state_delta_json["new_known_facts"] == ["门槛内侧有新鲜泥痕。"]


def test_story_director_fallback_reads_runtime_story_current_act(db_session) -> None:
    class FailingRouter:
        async def use_flash(self, *args, **kwargs):
            raise ValueError("invalid model output")

    game = create_game_from_config(db_session, build_generated_config())
    director = StoryDirector(router=FailingRouter())

    async def run_plan():
        return await director.plan(
            game=game,
            player_input="我继续检查义庄。",
            selected_action_style=select_action_style(game.config, "我继续检查义庄。"),
            recent_turns=[],
            related_materials=[],
            summaries={},
        )

    decision = anyio.run(run_plan)

    assert decision.current_act == "act_1"
    assert decision.scene_objective == "找到旧案第一条线索。"
    assert decision.forbidden_reveals == ["账册真凶"]
    assert decision.gm_instruction


def test_gameplay_clamps_director_allowed_reveals_to_current_act() -> None:
    decision = StoryDirectorDecision(
        current_act="act_1",
        allowed_reveals=["门槛泥痕", "新势力登场"],
        forbidden_reveals=["自写禁忌"],
    )

    GameplayService._enforce_director_reveal_boundaries(
        decision,
        runtime_story={
            "current_act": {
                "allowed_reveals": ["门槛泥痕"],
                "forbidden_reveals": ["账册真凶"],
            },
            "story_core": {
                "forbidden_drift": ["不要跳到京城"],
                "must_not_become": ["不要变成修仙题材"],
            },
        },
    )

    assert decision.allowed_reveals == ["门槛泥痕"]
    assert decision.forbidden_reveals == [
        "自写禁忌",
        "账册真凶",
        "不要跳到京城",
        "不要变成修仙题材",
    ]


def test_story_director_disables_reasoning_for_json_payload(db_session) -> None:
    calls: list[dict[str, object]] = []

    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            return ChatCompletionResult(
                content='{"current_act":"act_1","scene_objective":"检查义庄门槛"}',
                model="deepseek-flash-test",
                raw={},
            )

    game = create_game_from_config(db_session, build_generated_config())
    director = StoryDirector(router=FakeRouter())

    async def run_plan():
        return await director.plan(
            game=game,
            player_input="我继续检查义庄。",
            selected_action_style=select_action_style(game.config, "我继续检查义庄。"),
            recent_turns=[],
            related_materials=[],
            summaries={},
        )

    decision = anyio.run(run_plan)

    assert decision.current_act == "act_1"
    assert calls[0]["task_type"] == "story_director"
    assert calls[0]["reasoning_effort"] is None


def test_state_extractor_payload_uses_runtime_story_not_legacy_contracts(db_session) -> None:
    calls: list[dict[str, object]] = []

    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            return ChatCompletionResult(content="{}", model="deepseek-flash-test", raw={})

    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我检查门槛泥痕。",
        gm_output="门槛内侧有新鲜泥痕。",
        visible_summary="发现门槛泥痕。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )

    anyio.run(StateExtractor(router=FakeRouter()).extract, game, turn)
    payload = json.loads(calls[0]["messages"][1]["content"])

    assert calls[0]["task_type"] == "state_delta_extract"
    assert calls[0]["reasoning_effort"] is None
    assert payload["runtime_story"]["current_act"]["id"] == "act_1"
    assert "script_outline" not in payload
    assert "campaign_contract" not in payload


def test_state_extractor_backfills_location_change_from_scene_heading(db_session) -> None:
    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            return ChatCompletionResult(
                content='{"npc_updates":[{"name":"主角","location":"[地点]庭院"}]}',
                model="deepseek-flash-test",
                raw={},
            )

    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "南坡西侧猎户小道",
            "known_locations": ["南坡西侧猎户小道", "[地点]庭院"],
        },
    }
    turn = Turn(
        game_id=game.id,
        turn_number=71,
        player_input="返回基地，在庭院古松下休整。",
        gm_output="### [地点]·庭院\n\n主角返回庭院，众人在古松下休整。",
        visible_summary="众人返回[地点]庭院休整。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )

    delta = anyio.run(StateExtractor(router=FakeRouter()).extract, game, turn)
    next_state = apply_state_delta(state, turn, delta)

    assert delta["location_change"] == {
        "from": "南坡西侧猎户小道",
        "to": "[地点]庭院",
    }
    assert next_state["location"]["current"] == "[地点]庭院"
    assert next_state["v2"]["active_scene"]["location"] == "[地点]庭院"


def test_state_extractor_backfills_location_from_hierarchical_scene_heading(
    db_session,
) -> None:
    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            return ChatCompletionResult(
                content='{"npc_updates":[{"name":"角色F","status":"分析样本"}]}',
                model="deepseek-flash-test",
                raw={},
            )

    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点]庭院",
            "known_locations": ["[地点]庭院"],
        },
    }
    turn = Turn(
        game_id=game.id,
        turn_number=72,
        player_input="派角色F分析金属装置碎片。",
        gm_output="### 副楼·医疗室\n\n角色F把碎片放在医疗台上分析。",
        visible_summary="角色F在副楼医疗室分析样本。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )

    delta = anyio.run(StateExtractor(router=FakeRouter()).extract, game, turn)
    next_state = apply_state_delta(state, turn, delta)

    assert delta["location_change"] == {
        "from": "[地点]庭院",
        "to": "副楼·医疗室",
    }
    assert next_state["location"]["current"] == "副楼·医疗室"
    assert next_state["v2"]["active_scene"]["location"] == "副楼·医疗室"


def test_state_extractor_does_not_backfill_location_from_time_heading(
    db_session,
) -> None:
    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            return ChatCompletionResult(content="{}", model="deepseek-flash-test", raw={})

    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点]庭院",
            "known_locations": ["[地点]庭院"],
        },
    }
    turn = Turn(
        game_id=game.id,
        turn_number=73,
        player_input="我等待天亮。",
        gm_output="### 清晨\n\n第一缕晨光落在庭院里。",
        visible_summary="时间来到清晨。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )

    delta = anyio.run(StateExtractor(router=FakeRouter()).extract, game, turn)

    assert delta["location_change"] is None


def test_state_extractor_backfills_location_from_common_npc_location(
    db_session,
) -> None:
    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            return ChatCompletionResult(
                content=json.dumps(
                    {
                        "npc_updates": [
                            {"name": "角色D", "location": "[地点]·[地点]内"},
                            {"name": "陈雨桐", "location": "[地点]·[地点]内"},
                            {"name": "角色F", "location": "[地点]·[地点]内"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                model="deepseek-flash-test",
                raw={},
            )

    game = create_game_from_config(db_session, build_generated_config())
    state = game.state
    state.state_json = {
        **state.state_json,
        "location": {
            "current": "[地点]·隧道入口（[组织][地点]）",
            "known_locations": ["[地点]·隧道入口（[组织][地点]）"],
        },
        "protagonist": {
            **state.state_json.get("protagonist", {}),
            "name": "主角",
        },
        "npcs": [
            {
                "name": "主角",
                "location": "[地点]·隧道入口",
            }
        ],
    }
    turn = Turn(
        game_id=game.id,
        turn_number=74,
        player_input="先调查陈列柜的录像带和文件夹。",
        gm_output="### [地点]·内部\n\n众人进入观察点内部调查陈列柜。",
        visible_summary="众人在[地点]内部调查。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )

    delta = anyio.run(StateExtractor(router=FakeRouter()).extract, game, turn)
    next_state = apply_state_delta(state, turn, delta)

    assert delta["location_change"] == {
        "from": "[地点]·隧道入口（[组织][地点]）",
        "to": "[地点]·[地点]内",
    }
    assert {"name": "主角", "location": "[地点]·[地点]内"} in delta[
        "npc_updates"
    ]
    assert next_state["location"]["current"] == "[地点]·[地点]内"
    assert set(next_state["v2"]["active_scene"]["present_npcs"]) == {
        "角色D",
        "陈雨桐",
        "角色F",
        "主角",
    }


def test_turn_job_stages_exclude_drift_validation() -> None:
    """Round 46：偏离校验移出玩家路径——stage_total=6、不含 drift。"""
    from app.services.turn_jobs import TURN_JOB_STAGE_TOTAL, TURN_JOB_STAGES

    stages = [stage for stage, _label in TURN_JOB_STAGES]
    assert TURN_JOB_STAGE_TOTAL == 6
    assert "drift_validation" not in stages
    assert stages.index("gm_runtime") + 1 == stages.index("persist_turn")


def test_redact_forbidden_reveals_no_hit_is_zero_cost() -> None:
    """剧透兜底（唯一防线）：无整串命中时零 LLM、原稿返回、不置 rewrite_triggered。"""
    from types import SimpleNamespace

    class _NoCallRouter:
        async def use_pro(self, *args, **kwargs):
            raise AssertionError("无命中时不应调用 GM 重写。")

        async def use_flash(self, *args, **kwargs):
            raise AssertionError("无命中时不应调用任何 LLM。")

    service = GameplayService(router=_NoCallRouter())
    telemetry = SimpleNamespace(
        output_observation={"forbidden_reveal_hits": []}, rewrite_triggered=False
    )
    context = SimpleNamespace(telemetry=telemetry, game=SimpleNamespace(id="g"))
    runtime_output = object()

    async def _run():
        return await service._redact_forbidden_reveals_if_hit(
            context=context,
            director_decision=None,
            runtime_output=runtime_output,
            model_used="deepseek-v4-pro-test",
        )

    result, model = anyio.run(_run)
    assert result is runtime_output
    assert model == "deepseek-v4-pro-test"
    assert telemetry.rewrite_triggered is False


def test_audit_drift_no_throw_on_missing_job(db_session) -> None:
    """异步偏离审计绝不拖垮维护：job 不存在时优雅跳过、不抛异常。"""
    from uuid import uuid4

    from app.services.turn_maintenance_jobs import _audit_drift

    anyio.run(_audit_drift, uuid4())  # 不抛即通过
