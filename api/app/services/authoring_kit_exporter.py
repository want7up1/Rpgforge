"""剧本创作包导出。

给外部 AI（Claude / ChatGPT）使用：把 RPGForge 的 story_settings v2 填写指南、
一份从头编写的完整范例剧本，以及「只输出合法 JSON」的硬指令打包成一份 Markdown。
用户下载后连同自己的想法喂给外部 AI，产出可直接导入的 story_settings JSON。

纯静态内容，无 LLM、无 DB 依赖。范例 AUTHORING_KIT_EXAMPLE 必须始终能过
validate_story_settings（由 tests/test_import_script.py 守护，防止字段腐烂）。
"""

from __future__ import annotations

import json

from app.services.generation_parameters import DEFAULT_GENERATION_PARAMETERS
from app.services.settings_guide_exporter import export_settings_guide_markdown

# 从头编写的通用范例剧本（侦探题材，绝不使用任何真实存档/剧本）。
# 既当「JSON 骨架」又当「完整样板」，让外部 AI 直接模仿，避免骨架与样板各写一份导致漂移。
AUTHORING_KIT_EXAMPLE: dict = {
    "format_version": "rpgforge.story.v2",
    "game_profile": {
        "title": "雾港灯塔失踪案",
        "genre": "悬疑推理",
        "description": "新到任的港务调查员追查灯塔看守人离奇失踪。",
        "tone": "阴郁、克制、注重细节",
        "logline": "一座停转的灯塔，一个消失的看守人，把新来的调查员拖进雾港的旧秘密。",
    },
    "worldview": {
        "summary": "雾港是常年大雾的边境渔港，灯塔是全镇唯一的航行依靠，最近无故熄灭。",
        "setting": "雾港码头与断崖灯塔",
        "public_facts": ["灯塔已熄灭三夜，渔船不敢出海。"],
        "hidden_facts": ["灯塔地下室藏有走私货物的旧账。"],
        "core_conflicts": ["真相被镇上有头脸的人遮掩。"],
        "factions": ["港务局", "渔民行会"],
        "locations": ["雾港码头", "断崖灯塔", "[地点]"],
    },
    "story_core": {
        "premise": "调查员林决奉命查清灯塔看守人失踪案。",
        "core_fantasy": "用观察、问询和危险抉择，一层层揭开小镇旧秘密。",
        "central_mystery": "看守人是逃走、被害，还是发现了不该看的东西？",
        "main_goal": "查清灯塔看守人失踪真相。",
        "emotional_arc": "从例行公事到被迫直面小镇的集体沉默。",
        "narrative_style": "冷静、细节密集、不给超自然答案。",
        "current_act": "act_1",
        "must_preserve": ["大雾笼罩的灯塔", "看守人失踪的悬念"],
        "must_not_become": ["不要变成超自然恐怖", "不要提前坐实凶手"],
        "forbidden_drift": ["不要引入魔法或怪物"],
        "canon_terms": ["雾港", "断崖灯塔", "看守人韩牧"],
    },
    "core_characters": [
        {
            "id": "lin_jue",
            "name": "林决",
            "role": "protagonist",
            "identity": "新到任的港务调查员",
            "description": "刚调来雾港、急于证明自己的调查员。",
            "appearance": "灰呢大衣，随身带一本翻旧的勘查手册。",
            "visibility": "visible",
            "dramatic_function": "推动调查的主角",
            "desire": "靠破案站稳脚跟",
            "fear": "发现真相牵连到自己的上级",
            "leverage": "对细节有近乎偏执的记忆力",
            "relationship_arc": "从孤身外来者到赢得部分镇民信任",
            "public_limit": "不能提前断定凶手",
        },
        {
            "id": "shen_lan",
            "name": "沈兰",
            "role": "npc",
            "identity": "灯塔看守人的女儿",
            "description": "守着空灯塔、对外来者警惕的年轻女子。",
            "appearance": "渔家粗布衣，袖口沾着灯油。",
            "visibility": "visible",
            "dramatic_function": "线索守门人",
            "desire": "找回失踪的父亲",
            "fear": "父亲卷入了见不得光的事",
            "leverage": "知道灯塔地下室的入口",
            "relationship_arc": "从敌意防备到有限合作",
            "public_limit": "尚未建立信任前，不愿提供额外线索",
        },
    ],
    "act_plan": [
        {
            "id": "act_1",
            "title": "熄灭的灯塔",
            "objective": "在灯塔现场找到失踪案的第一条线索。",
            "dramatic_question": "看守人是自己离开，还是出了事？",
            "pressure": "镇上有人希望此事尽快了结。",
            "must_hit_beats": ["勘查灯塔现场", "确认看守人最后的行踪"],
            "allowed_reveals": ["失踪当晚灯塔曾有第二个人"],
            "forbidden_reveals": ["走私旧账的存在"],
            "relationship_turn": "沈兰开始动摇是否信任林决。",
            "escalation_limit": "只推进到现场线索层，不引入凶手对峙。",
            "completion_anchors": [
                {
                    "id": "act_1_inspect_lamp",
                    "title": "勘查灯室",
                    "required": True,
                    "alternative_group": "",
                    "description": "确认灯塔是被人为熄灭。",
                    "completion_signal": "发现灯油被人为放空的痕迹。",
                },
                {
                    "id": "act_1_second_person_tracks",
                    "title": "核实现场痕迹",
                    "required": True,
                    "alternative_group": "second_person_evidence",
                    "description": "证明失踪当晚灯塔不止看守人一人。",
                    "completion_signal": "找到不属于看守人的脚印或物件。",
                },
                {
                    "id": "act_1_second_person_testimony",
                    "title": "核实证人证言",
                    "required": True,
                    "alternative_group": "second_person_evidence",
                    "description": "通过另一条调查路线确认当晚有来客。",
                    "completion_signal": "证人明确说出当晚见到另一人进入灯塔的时间和经过。",
                },
                {
                    "id": "act_1_help_fishermen",
                    "title": "帮助滞港渔民",
                    "required": False,
                    "alternative_group": "",
                    "description": "可选的人情支线，不是失踪案转幕条件。",
                    "completion_signal": "帮助渔民修好临时雾号，并得到他们的感谢。",
                },
            ],
            "transition_to_next_act": {
                "target_act": "act_2",
                "condition": "确认人为熄灯，并通过现场痕迹或证人证言核实当晚有来客。",
                "transition_style": "顺线索深入",
            },
        },
        {
            "id": "act_2",
            "title": "灯塔深处",
            "objective": "追查现场线索，取得能解释失踪案的关键证据。",
            "dramatic_question": "看守人是因为这本旧账才消失的吗？",
            "pressure": "港务局开始施压要求结案。",
            "must_hit_beats": ["进入地下室", "找到走私旧账残页"],
            "allowed_reveals": ["旧账牵连港务局旧人"],
            "forbidden_reveals": ["最终主使身份"],
            "relationship_turn": "沈兰与林决形成脆弱合作。",
            "escalation_limit": "只揭露旧账残页，不揭露最终主使。",
            "completion_anchors": [
                {
                    "id": "act_2_find_ledger",
                    "title": "取得关键证据",
                    "required": True,
                    "alternative_group": "",
                    "description": "拿到指向下一步的实物证据。",
                    "completion_signal": "获得走私旧账残页。",
                }
            ],
            "transition_to_next_act": {},
        },
    ],
    "main_quest_path": [
        {
            "id": "main_quest_1",
            "act_id": "act_1",
            "title": "勘查灯塔现场",
            "objective": "找到失踪案的第一条线索。",
            "player_visible": "检查熄灭的灯塔。",
            "completion_signal": "发现灯油被人为放空的痕迹。",
            "optional": False,
        },
        {
            "id": "main_quest_2",
            "act_id": "act_2",
            "title": "继续调查灯塔",
            "objective": "查清现场线索指向的后续真相。",
            "player_visible": "顺着已发现的线索继续调查。",
            "completion_signal": "获得走私旧账残页。",
            "optional": False,
        },
    ],
    "core_mechanics": [
        {
            "id": "investigation",
            "name": "调查推进",
            "rule": "给线索不给答案，隐藏真相必须通过可观察痕迹逐步揭露。",
            "progression": "本幕全部必需条件达成后自动转幕，同组替代路线任一完成即可。",
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
            "id": "lighthouse",
            "title": "断崖灯塔",
            "type": "location",
            "keywords": ["灯塔", "灯室", "断崖"],
            "triggers": ["灯塔", "灯室", "断崖"],
            "priority": "critical",
            "always_on": True,
            "visibility": "mixed",
            "public_info": "全镇唯一的航行依靠，已熄灭三夜。",
            "gm_secret": "灯塔地下室藏有走私货物旧账。",
            "content": "灯塔是第一幕核心地点，灯室痕迹和地下室入口指向失踪真相。",
            "usage": "玩家调查灯塔、灯室或断崖时注入，不直接说出地下室旧账。",
            "enabled": True,
        },
        {
            "id": "shen_lan_material",
            "title": "看守人之女沈兰",
            "type": "npc",
            "keywords": ["沈兰", "看守人", "灯油"],
            "triggers": ["沈兰", "看守人", "地下室"],
            "priority": "high",
            "always_on": False,
            "visibility": "mixed",
            "public_info": "守着空灯塔、对外来者警惕的年轻女子。",
            "gm_secret": "沈兰知道灯塔地下室的入口。",
            "content": "沈兰是关键线索人，会在被取得信任后透露地下室入口。",
            "usage": "玩家提到沈兰、看守人或地下室时注入。",
            "enabled": True,
        },
    ],
    "home_base": {
        "id": "home_base",
        "name": "[地点]",
        "role": "休整、情报整理与关系推进据点。",
        "public_functions": ["整理线索", "歇脚"],
        "hidden_hooks": ["据点旧航海图标注了灯塔地下室入口。"],
        "upgrade_paths": ["情报角", "档案柜"],
        "npc_services": ["老港工帮忙辨认旧账笔迹"],
        "scene_uses": ["回合间总结线索"],
    },
    "hard_rules": {
        "must_follow": ["每回合输出玩家可见剧情，并给出 A/B/C/D 四个具体行动选项。"],
        "must_not": ["不要引入超自然元素", "不要提前揭露最终主使"],
        "reveal_rules": ["隐藏真相只能通过线索逐步揭露。"],
        "continuity_rules": ["人物动机和地点状态必须保持一致。"],
        "gm_output_rules": ["正文不输出状态结算。"],
    },
    "generation_parameters": dict(DEFAULT_GENERATION_PARAMETERS),
}

_AI_INSTRUCTION = """\
## 给 AI 的硬指令

把上面的「字段填写指南」当规则，把「完整范例剧本」当模板，结合用户给你的剧情想法，
产出一份**全新的** `story_settings` JSON。务必遵守：

1. **只输出一个合法 JSON 对象**，不要解释、Markdown 代码围栏或注释。
2. `format_version` 必须是 `rpgforge.story.v2`。
3. 使用范例中的 `story_settings` 顶层键；生成参数放在 `generation_parameters`。
   不要自创顶层字段，不要套入 `config`、游戏存档或内部运行状态。
4. 标题、题材、简介写进 `game_profile`（不是顶层），它们决定游戏标题。
5. `core_characters[].name` 必须唯一且非空；`act_plan[].id` 与所有
   `completion_anchors[].id` 必须全局唯一。
6. 秘密、真凶、反转**不要**写进公开字段，尤其是玩家目标栏会显示的
   `act_plan[].title`、`act_plan[].objective`，以及任务名和 `player_visible`；
   秘密正文放进 `worldview.hidden_facts` 或 `story_material_library[].gm_secret`，
   再用 `act_plan[].forbidden_reveals`、`hard_rules.must_not` 约束揭露时机。
7. 本创作模板至少写 2 幕（`act_plan`），每幕至少 1 个 `required: true` 的完成锚点。
   同组替代路线是 OR，不同组及未分组的必需锚点之间是 AND；`required: false` 不阻塞。
   全部必需条件被结算确认为完成后，平台自动转幕；`transition_to_next_act.condition`
   仅作叙事说明，不是独立程序门，也不会额外等待玩家按“继续”或口头确认。
8. 不要输出 `initial_state`、`state_json`、`story_progress`、状态增量、回执或任务版本。
   初始设定和后续状态后果写进人物、世界观、机制规则及明确的叙事事件，
   让 GM 写出实际获得/失去物品、伤势解除、关系变化或事实揭露，再由平台结算。
9. 产出后自检：JSON 能被 `JSON.parse` 解析，且字段名与范例一致。
"""

_EXAMPLE_READING_NOTES = """\
## 如何阅读这个范例

- 幕标题、幕目标、任务标题与玩家提示都按可公开显示来写。
  第二幕使用“灯塔深处／追查现场线索”，不把尚未揭露的旧账写进目标栏。
- 第一幕的必需条件是：`act_1_inspect_lamp` **AND**
  （`act_1_second_person_tracks` **OR** `act_1_second_person_testimony`）。
  后两条都写 `required: true` 和同一个 `alternative_group`；不是把它们写成可选项。
  若另有一个替代组，该组也必须至少完成一条；不同组之间仍是 AND。
- `act_1_help_fishermen` 是 `required: false` 的可选支线。
  两条必需条件满足后，即使没帮助渔民、也没走另一条调查路线，平台仍会自动进入第二幕。
- `transition_to_next_act.condition` 复述同一组叙事前提，`transition_style` 描述转场写法。
  真正必须兑现的新前提应写成必需锚点及明确的 `completion_signal`，不能只藏在 condition 里。
- 这个 JSON 是设定源，不是开局状态或存档。比如“找到残页后将证据交给沈兰”应作为可观察的
  剧情后果写入机制或素材说明；不要在 JSON 顶层附带物品栏、`initial_state` 或结算回执。
"""


def export_authoring_kit_markdown() -> str:
    """组装「剧本创作包」Markdown：指南 + 完整范例 JSON + AI 指令。"""
    example_json = json.dumps(AUTHORING_KIT_EXAMPLE, ensure_ascii=False, indent=2)
    parts = [
        "# RPGForge 剧本创作包",
        "",
        (
            "> 把本文整篇连同你的剧情想法一起发给外部 AI（Claude / ChatGPT），"
            "让它产出一份 `story_settings` JSON，再回到 RPGForge「导入剧本」粘贴即可新建游戏。"
        ),
        "",
        "---",
        "",
        export_settings_guide_markdown(),
        "",
        "---",
        "",
        _EXAMPLE_READING_NOTES,
        "",
        "## 完整范例剧本（可直接导入，照此结构填写）",
        "",
        "```json",
        example_json,
        "```",
        "",
        "---",
        "",
        _AI_INSTRUCTION,
    ]
    return "\n".join(parts).rstrip() + "\n"
