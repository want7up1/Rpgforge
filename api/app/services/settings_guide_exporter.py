# ruff: noqa: E501
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.models.game import Game
from app.services.story_settings import story_settings_from_config


def settings_guide_export_filename(title: str) -> str:
    safe_title = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", title).strip(" .-")
    return f"RPGForge-{safe_title or 'settings'}-设定填写说明.md"


def export_settings_guide_markdown(game: Game) -> str:
    story = story_settings_from_config(game.config)
    lines: list[str] = [
        f"# RPGForge 设定填写说明：{_text(game.title)}",
        "",
        (
            "> 这份文档是给创作者和 AI 使用的填写指南；它不是可导入 JSON。"
            "真正可导入的是同一页面导出的 `story_settings` JSON。"
        ),
        "",
        f"- 导出时间：{datetime.now(UTC).isoformat()}",
        f"- 游戏 ID：{game.id}",
        f"- JSON 格式版本：`{_text(story.get('format_version'))}`",
        "- 导入生效范围：只覆盖剧本设定源 `story_settings`，不覆盖回合历史、当前状态、摘要或存档进度。",
        "",
    ]
    _append_ai_instruction(lines)
    _append_workflow(lines)
    _append_current_summary(lines, story)
    _append_module_reference(lines)
    _append_field_reference(lines)
    _append_risk_rules(lines)
    return "\n".join(lines).rstrip() + "\n"


def _append_ai_instruction(lines: list[str]) -> None:
    lines.extend(
        [
            "## 给 AI 的修改指令模板",
            "",
            "把下面这段和导出的 JSON 一起发给 AI：",
            "",
            "```text",
            "你正在修改 RPGForge 的 story_settings v2 JSON。",
            "请严格保持 JSON 是完整合法对象，format_version 必须是 rpgforge.story.v2。",
            "可以完整修改世界观、核心人物、五幕主线、主线轨迹、核心机制、行动风格规则、剧本素材库、破晓基地、强制规则和生成参数。",
            "不要添加回合历史、当前状态、存档进度、摘要、AI 思考过程或 Markdown 注释。",
            "不要把隐藏真相写进 public_facts、public_info、player_visible、角色公开简介或玩家开局已知内容。",
            "所有数组条目请保留稳定 id；如果必须改 id，请同步修改引用它的 act_id、completion_anchor、trigger、quest 或素材关系。",
            "五幕主线的 completion_anchors 是推进到下一幕的软锚点，不是强制任务清单；每个锚点必须有可被状态提取器识别的 completion_signal。",
            "main_quest_path 是软主线轨迹，允许玩家自由探索、停留、社交和绕路，不要写成强制一本道。",
            "hard_rules 是最高优先级强约束，不能被临场剧情或风格描述覆盖。",
            "generation_parameters 只控制 GM 输出长度、格式节奏和上下文摘录长度，不要写剧情设定。",
            "修改完成后只输出完整 JSON，不要输出解释、代码块外文字或额外注释。",
            "```",
            "",
        ]
    )


def _append_workflow(lines: list[str]) -> None:
    lines.extend(
        [
            "## 推荐修改流程",
            "",
            "1. 先下载 `story_settings JSON` 和本说明文档。",
            "2. 把 JSON 与本说明一起交给 AI 或手动编辑。",
            "3. 重点检查 `format_version`、所有 `id`、`act_id`、`completion_anchors` 和 `generation_parameters`。",
            "4. 确认 JSON 可以被解析后，在 RPGForge 设置页导入。",
            "5. 导入成功即保存设定；不会改变当前存档、回合历史、摘要或状态。",
            "",
        ]
    )


def _append_current_summary(lines: list[str], story: dict[str, Any]) -> None:
    lines.extend(
        [
            "## 当前 JSON 结构概览",
            "",
            _summary_line("核心人物", story.get("core_characters")),
            _summary_line("幕结构", story.get("act_plan")),
            _summary_line("主线轨迹", story.get("main_quest_path")),
            _summary_line("核心机制", story.get("core_mechanics")),
            _summary_line("行动风格规则", story.get("action_style_rules")),
            _summary_line("剧本素材库", story.get("story_material_library")),
            "",
        ]
    )


def _append_module_reference(lines: list[str]) -> None:
    rows = [
        (
            "game_profile",
            "游戏档案",
            "标题、题材、简介、基调。影响游戏列表、导出文件名和 GM 对题材的第一判断。",
            "导入生效",
        ),
        (
            "worldview",
            "世界观",
            "世界舞台、公开事实、隐藏事实、势力、地点。影响 GM 的世界一致性和可观察线索来源。",
            "导入生效",
        ),
        (
            "story_core",
            "故事核心",
            "核心幻想、主线悬念、长期目标、当前幕、必须保留和禁止偏离。是防跑偏的最高层剧本承诺。",
            "导入生效",
        ),
        (
            "core_characters",
            "核心人物",
            "主角、同伴、NPC、反派和关系弧。导入后会同步角色档案。",
            "导入生效",
        ),
        (
            "act_plan",
            "五幕主线",
            "每幕目标、揭露范围、完成锚点和转场条件。决定什么时候允许推进到下一幕。",
            "导入生效",
        ),
        (
            "main_quest_path",
            "主线轨迹",
            "软主线节点。告诉 GM 如何保持长期方向，但不剥夺玩家自由探索。",
            "导入生效",
        ),
        (
            "core_mechanics",
            "核心机制",
            "成长、资源、调查、压力、判定、基地等长期玩法规则。",
            "导入生效",
        ),
        (
            "action_style_rules",
            "行动风格规则",
            "按玩家输入匹配调查、社交、探索、战斗等行动写法。",
            "导入生效",
        ),
        (
            "story_material_library",
            "剧本素材库",
            "按关键词召回地点、秘密、线索、势力、物品、压力和反转。",
            "导入生效",
        ),
        (
            "home_base",
            "破晓基地",
            "长期据点、安全屋、组织后台或移动基地。影响休整、升级、情报和关系推进。",
            "导入生效",
        ),
        (
            "hard_rules",
            "强制规则",
            "最高优先级硬约束，覆盖临场发挥和普通风格描述。",
            "导入生效",
        ),
        (
            "generation_parameters",
            "生成参数",
            "控制每回合输出长度、段落、标题、重点标记和近期回合摘录长度。",
            "导入生效",
        ),
    ]
    lines.extend(["## 一级模块说明", ""])
    lines.extend(_table(["模块", "中文含义", "用途和剧情影响", "导入是否生效"], rows))
    lines.append("")


def _append_field_reference(lines: list[str]) -> None:
    lines.extend(["## 字段填写说明", ""])
    _append_table_section(lines, "game_profile", [
        ("game_profile.title", "游戏标题", "1-40 字为宜；会同步到游戏标题。", "导入生效", "雁回镇旧案"),
        ("game_profile.genre", "题材类型", "写清时代、风格、玩法类型；不要堆太多标签。", "导入生效", "黑暗武侠调查"),
        ("game_profile.description", "一句话简介", "玩家和 GM 都可见的概述，不写隐藏真相。", "导入生效", "失忆镖师追查义庄旧案。"),
        ("game_profile.tone", "整体基调", "影响 GM 语言气质和场景氛围。", "导入生效", "冷峻、克制、悬疑"),
        ("game_profile.logline", "故事钩子", "给 GM 的一句话抓手，可比 description 更有戏剧性。", "导入生效", "雨夜义庄的一串泥痕，把主角拖回旧案中心。"),
    ])
    _append_table_section(lines, "worldview", [
        ("worldview.summary", "公开世界观摘要", "玩家可理解的世界描述；不要写最终真相。", "导入生效", "雁回镇靠山临水，义庄旧案多年未结。"),
        ("worldview.setting", "初始舞台", "开局常用地点或区域。", "导入生效", "雁回镇义庄"),
        ("worldview.public_facts[]", "公开事实", "玩家开局或常识可知的信息。", "导入生效", "镇外旧义庄多年无人敢近。"),
        ("worldview.hidden_facts[]", "隐藏事实", "只给 GM 保持一致性，不能直接剧透。", "导入生效", "义庄暗藏旧案账册。"),
        ("worldview.core_conflicts[]", "核心冲突", "推动世界和势力行动的长期矛盾。", "导入生效", "旧案证据被各方争夺。"),
        ("worldview.factions[]", "关键势力", "供 GM 安排冲突、压力和 NPC 立场。", "导入生效", "黑伞会"),
        ("worldview.locations[]", "关键地点", "供 GM 保持地点一致，避免凭空扩张。", "导入生效", "破晓基地"),
    ])
    _append_table_section(lines, "story_core", [
        ("story_core.premise", "剧本前提", "本局最核心的承诺；GM 不应偏离。", "导入生效", "失忆镖师追查义庄旧案。"),
        ("story_core.core_fantasy", "核心幻想", "玩家想体验的爽点或主题体验。", "导入生效", "以调查和江湖人情撬开旧案。"),
        ("story_core.central_mystery", "核心悬念", "贯穿全剧的问题；不要在前几回合直接解答。", "导入生效", "沈砚失忆前到底护送了什么？"),
        ("story_core.main_goal", "长期目标", "GM 拉回主线时使用的方向。", "导入生效", "查清义庄旧案。"),
        ("story_core.current_act", "默认当前幕", "新游戏初始幕；已有游戏实际进度优先看当前状态。", "导入生效", "act_1"),
        ("story_core.must_preserve[]", "必须保留", "用户强要求、正典设定、必须出现内容。", "导入生效", "雨夜义庄"),
        ("story_core.must_not_become[]", "禁止变成", "类型红线，防止题材变味。", "导入生效", "不要修仙"),
        ("story_core.forbidden_drift[]", "禁止偏离", "剧情长期不能滑向的方向。", "导入生效", "不要提前进入终局门派战争"),
        ("story_core.canon_terms[]", "正典词条", "重要专名，帮助 GM 保持命名一致。", "导入生效", "雁回镇"),
    ])
    _append_table_section(lines, "core_characters[]", [
        ("core_characters[].id", "稳定角色 id", "用英文或拼音 snake_case；不要随意改。", "导入生效", "shen_yan"),
        ("core_characters[].name", "角色名", "会同步到角色档案；不能为空。", "导入生效", "沈砚"),
        ("core_characters[].role", "角色类型", "建议 protagonist、companion、npc、antagonist、other。", "导入生效", "protagonist"),
        ("core_characters[].identity", "公开身份", "玩家可见身份，不写隐藏身份。", "导入生效", "失忆镖师"),
        ("core_characters[].description", "公开介绍", "玩家可见人物描述。", "导入生效", "追查义庄旧案的主角。"),
        ("core_characters[].appearance", "外貌", "用于角色展示和视觉一致性。", "导入生效", "旧青色短打，右手缠着褪色布带。"),
        ("core_characters[].dramatic_function", "戏剧功能", "告诉 GM 该角色在主线中的作用。", "导入生效", "线索守门人"),
        ("core_characters[].desire/fear/leverage", "动机组", "决定 NPC 行动、谈判筹码和关系变化。", "导入生效", "想拿回账册"),
        ("core_characters[].public_limit", "公开边界", "角色开局不会主动说出的秘密。", "导入生效", "不会承认知道账册"),
        ("core_characters[].visibility", "可见性", "visible 会展示给玩家；hidden 保留给 GM。", "导入生效", "visible"),
    ])
    _append_table_section(lines, "act_plan[]", [
        ("act_plan[].id", "幕 id", "必须唯一，建议 act_1 到 act_5；被状态推进引用。", "导入生效", "act_1"),
        ("act_plan[].title", "幕标题", "给 GM 识别阶段，不一定直接展示。", "导入生效", "义庄夜雨"),
        ("act_plan[].objective", "本幕目标", "当前幕 GM 的主要推进方向。", "导入生效", "找到旧案第一条线索。"),
        ("act_plan[].dramatic_question", "戏剧问题", "决定本幕张力，不等于任务清单。", "导入生效", "沈砚能否证明自己不是帮凶？"),
        ("act_plan[].allowed_reveals[]", "允许揭露", "本幕可以透露的信息边界。", "导入生效", "旧案仍有人遮掩"),
        ("act_plan[].forbidden_reveals[]", "禁止揭露", "本幕不能提前说出的真相。", "导入生效", "账册真凶"),
        ("act_plan[].completion_anchors[]", "完成锚点", "推进到下一幕前需要自然满足的条件。", "导入生效", "找到门槛泥痕"),
        ("completion_anchors[].id", "锚点 id", "必须全局唯一；状态提取器用它标记完成。", "导入生效", "act_1_find_mud"),
        ("completion_anchors[].completion_signal", "完成信号", "写成可从剧情文本识别的明确事件。", "导入生效", "发现门槛内侧的新鲜泥痕。"),
        ("transition_to_next_act.target_act", "下一幕目标", "只能指向存在的 act id；最后一幕可留空对象。", "导入生效", "act_2"),
    ])
    _append_table_section(lines, "main_quest_path[]", [
        ("main_quest_path[].id", "主线节点 id", "稳定唯一，便于 AI 修改和引用。", "导入生效", "main_quest_1"),
        ("main_quest_path[].act_id", "所属幕", "必须对应 act_plan[].id。", "导入生效", "act_1"),
        ("main_quest_path[].title", "任务标题", "可作为玩家可见任务名。", "导入生效", "查明义庄泥痕"),
        ("main_quest_path[].objective", "软目标", "给 GM 的推进方向，不强制玩家立刻执行。", "导入生效", "找到旧案第一条线索。"),
        ("main_quest_path[].player_visible", "玩家提示", "可公开显示，不写 GM 秘密。", "导入生效", "调查义庄异常痕迹。"),
        ("main_quest_path[].completion_signal", "完成信号", "和锚点一样，写可识别事件。", "导入生效", "发现门槛泥痕。"),
    ])
    _append_table_section(lines, "core_mechanics[]", [
        ("core_mechanics[].id", "机制 id", "稳定唯一。", "导入生效", "investigation"),
        ("core_mechanics[].name", "机制名", "简短说明机制。", "导入生效", "调查推进"),
        ("core_mechanics[].rule", "机制规则", "写 GM 必须长期遵守的可执行规则。", "导入生效", "给线索不给答案。"),
        ("core_mechanics[].progression", "推进方式", "数值、阶段、触发方式或代价。", "导入生效", "完成锚点后才允许切幕。"),
        ("core_mechanics[].visibility", "可见性", "public、mixed、gm_only。", "导入生效", "mixed"),
    ])
    _append_table_section(lines, "action_style_rules[]", [
        ("action_style_rules[].id", "行动风格 id", "稳定唯一。", "导入生效", "investigation"),
        ("action_style_rules[].triggers[]", "触发词", "玩家输入命中后更容易选中该风格。", "导入生效", "调查、检查、线索"),
        ("action_style_rules[].rule", "行动写法规则", "告诉 GM 该类行动怎么写结果、代价、线索。", "导入生效", "提供可验证线索，不直接泄露隐藏真相。"),
        ("action_style_rules[].priority", "优先级", "critical、high、medium、low；冲突时高优先。", "导入生效", "high"),
        ("action_style_rules[].enabled", "是否启用", "false 后不参与匹配。", "导入生效", "true"),
    ])
    _append_table_section(lines, "story_material_library[]", [
        ("story_material_library[].id", "素材 id", "稳定唯一，建议用可读英文或拼音。", "导入生效", "yizhuang"),
        ("story_material_library[].title", "素材标题", "GM 诊断和召回时显示。", "导入生效", "雁回镇义庄"),
        ("story_material_library[].type", "素材类型", "location、npc、item、secret、clue、pressure、twist 等。", "导入生效", "location"),
        ("story_material_library[].keywords[]", "关键词", "用于语义召回；写清专名和别名。", "导入生效", "义庄、泥痕、棺木"),
        ("story_material_library[].triggers[]", "触发词", "玩家输入直接命中时强召回。", "导入生效", "黑伞、陆沉舟"),
        ("story_material_library[].always_on", "常驻注入", "critical 核心设定可 true；太多会耗 token。", "导入生效", "false"),
        ("story_material_library[].public_info", "公开信息", "玩家可见，不写秘密。", "导入生效", "镇外旧义庄无人敢近。"),
        ("story_material_library[].gm_secret", "GM 秘密", "只供 GM 保持一致，不能直接剧透。", "导入生效", "义庄暗藏旧案账册。"),
        ("story_material_library[].content", "完整素材", "告诉 GM 这条素材如何影响剧情。", "导入生效", "门槛泥痕和伞骨划痕指向陆沉舟。"),
        ("story_material_library[].usage", "使用规则", "何时召回、如何给线索、不能揭露什么。", "导入生效", "玩家调查义庄时注入，不直接说真凶。"),
    ])
    _append_table_section(lines, "home_base", [
        ("home_base.id", "据点 id", "稳定唯一。", "导入生效", "home_base"),
        ("home_base.name", "据点名", "可以是基地、安全屋、组织后台或移动据点。", "导入生效", "破晓基地"),
        ("home_base.role", "剧情作用", "说明据点如何服务休整、情报、升级和关系推进。", "导入生效", "休整与情报整理据点。"),
        ("home_base.public_functions[]", "公开功能", "玩家可用的功能。", "导入生效", "整理线索"),
        ("home_base.hidden_hooks[]", "隐藏钩子", "GM 后续可用秘密。", "导入生效", "旧档案夹有账页拓印。"),
    ])
    _append_table_section(lines, "hard_rules", [
        ("hard_rules.must_follow[]", "必须遵守", "最高优先级正向规则。", "导入生效", "每回合给出 A/B/C/D 四个行动选项。"),
        ("hard_rules.must_not[]", "绝对禁止", "不能被剧情、风格或模型自由发挥覆盖。", "导入生效", "不要修仙"),
        ("hard_rules.reveal_rules[]", "揭露规则", "控制秘密怎么慢慢出现。", "导入生效", "隐藏真相只能通过线索逐步揭露。"),
        ("hard_rules.continuity_rules[]", "连续性规则", "控制人物、物品、地点、状态不乱变。", "导入生效", "人物动机和地点状态必须一致。"),
        ("hard_rules.gm_output_rules[]", "输出规则", "可以补充正文风格和显示边界，但不能破坏系统四选项契约。", "导入生效", "正文不输出状态结算。"),
    ])
    _append_table_section(lines, "generation_parameters", [
        ("narrative_target_min_chars", "目标最少字数", "影响剧情丰富度和 token 消耗。", "导入生效", "800"),
        ("narrative_target_max_chars", "目标最多字数", "越大越丰富也越耗 token。", "导入生效", "1200"),
        ("narrative_min_chars", "硬性最低字数", "避免 GM 回复过短。", "导入生效", "700"),
        ("paragraph_min / paragraph_max", "段落范围", "控制阅读节奏。", "导入生效", "3 / 6"),
        ("scene_heading_max", "标题数量上限", "0 表示不鼓励标题；过高会像大纲。", "导入生效", "1"),
        ("emphasis_min / emphasis_max", "重点标记数量", "控制 `**重点**` 数量。", "导入生效", "2 / 4"),
        ("recent_turn_excerpt_chars", "近期回合摘录长度", "越高上下文越完整，越低越省 token。", "导入生效", "420"),
    ])


def _append_table_section(lines: list[str], title: str, rows: list[tuple[str, str, str, str, str]]) -> None:
    lines.extend([f"### {title}", ""])
    lines.extend(_table(["字段路径", "作用", "填写规则和剧情影响", "导入是否生效", "示例"], rows))
    lines.append("")


def _append_risk_rules(lines: list[str]) -> None:
    lines.extend(
        [
            "## 修改风险和校验重点",
            "",
            "- `format_version` 必须保持 `rpgforge.story.v2`。",
            "- `act_plan[].id`、`main_quest_path[].act_id`、`transition_to_next_act.target_act` 必须互相对应。",
            "- `completion_anchors[].id` 必须全局唯一；重复会导致导入失败。",
            "- `completion_signal` 要写成剧情中能自然出现、状态提取器能识别的事件。",
            "- `public_*`、`player_visible`、角色公开字段不能写隐藏真相。",
            "- `gm_secret`、`hidden_facts` 可以写完整秘密，但 GM 只能转化成线索，不应直接剧透。",
            "- `story_material_library[].always_on=true` 的素材会更稳定进入上下文，但过多会增加 token 消耗。",
            "- `generation_parameters.recent_turn_excerpt_chars` 越大，近期回合上下文越完整；越小越省 token。",
            "- 存档、当前状态、回合历史和摘要不在这个 JSON 内；导入设定不会自动重写已经发生的剧情进度。",
            "",
        ]
    )


def _table(headers: list[str], rows: list[tuple[Any, ...]]) -> list[str]:
    rendered = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        rendered.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return rendered


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _summary_line(label: str, value: Any) -> str:
    count = len(value) if isinstance(value, list) else 1 if isinstance(value, dict) and value else 0
    return f"- {label}：{count} 项"


def _text(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value not in (None, "", [], {}):
        return str(value)
    return "未记录"
