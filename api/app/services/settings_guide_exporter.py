# ruff: noqa: E501
from __future__ import annotations

import re
from typing import Any

from app.services.story_settings import STORY_SETTINGS_FORMAT_VERSION


def settings_guide_export_filename(title: str) -> str:
    safe_title = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", title).strip(" .-")
    return f"RPGForge-{safe_title or 'settings'}-设定填写说明.md"


def export_settings_guide_markdown() -> str:
    """生成通用版填写说明：内容与具体游戏无关，对任意剧本一致。"""
    lines: list[str] = [
        "# RPGForge 设定填写说明",
        "",
        (
            "> 这份文档是给创作者和 AI 使用的通用填写指南；它不是可导入 JSON。"
            "真正可导入的是同一页面导出的 `story_settings` JSON。"
        ),
        "",
        f"- JSON 格式版本：`{STORY_SETTINGS_FORMAT_VERSION}`",
        "- 导入生效范围：只覆盖剧本设定源 `story_settings`，不覆盖回合历史、当前状态、摘要或存档进度。",
        "",
    ]
    _append_ai_instruction(lines)
    _append_workflow(lines)
    _append_author_notes(lines)
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
            "可以完整修改世界观、核心人物、分幕主线、主线轨迹、核心机制、行动风格规则、剧本素材库、[地点]、强制规则和生成参数。",
            "不要添加 initial_state、回合历史、当前状态、状态增量、结算回执、存档进度、摘要、任务版本或 AI 思考过程。",
            "不要把隐藏真相写进 public_facts、public_info、player_visible、角色公开简介或 act_plan 的 title/objective；幕标题和目标会进入玩家目标栏。",
            "所有数组条目请保留稳定 id；如果必须改 id，请同步修改引用它的 act_id、completion_anchor、trigger、quest 或素材关系。",
            "completion_anchors 的剧情达成方式可以自由，但 required 条件是自动转幕的实际判定依据；completion_signal 必须是可从已发生剧情识别的明确事件。",
            "同一幕同一 alternative_group 内的 required 锚点是 OR，不同组及未分组 required 锚点之间是 AND；required:false 不阻塞转幕。",
            "全部必需条件被结算确认为完成后会自动转幕，transition_to_next_act.condition 不是额外的程序门。",
            "main_quest_path 是软主线轨迹，允许玩家自由探索、停留、社交和绕路，不要写成强制一本道。",
            "hard_rules 是最高优先级强约束，不能被临场剧情或风格描述覆盖。",
            "generation_parameters 只控制 GM 输出长度、格式节奏和上下文摘录长度，不要写剧情设定。",
            "修改完成后只输出完整 JSON，不要解释、Markdown 代码围栏或注释。",
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


def _append_author_notes(lines: list[str]) -> None:
    lines.extend(
        [
            "## 作者须知：公开目标、转幕与状态后果",
            "",
            "### 公开目标不藏谜底",
            "",
            "`act_plan[].title` 和 `act_plan[].objective` 会用于玩家目标栏；任务标题、`player_visible` 和角色公开介绍也应按玩家可读内容填写。不要把尚未揭露的真凶、隐藏身份或关键证物直接写进这些字段。",
            "例如用“灯塔深处／追查现场线索”作为公开目标，把“地下室藏有走私旧账”放进 `worldview.hidden_facts` 或素材的 `gm_secret`，并说明何时才允许揭露。",
            "",
            "### 必需条件达成后自动转幕",
            "",
            "模型根据实际发生的正文显式上报已完成锚点，平台再按锚点 ID 校验和结算；`completion_signal` 是叙事完成信号，不是关键词触发器。",
            "",
            "- 每个没有替代组的 `required: true` 锚点都必须完成。",
            "- 同一幕内，填相同 `alternative_group` 的多个必需锚点组成 OR：任意完成一条即可满足该组。",
            "- 不同替代组之间、替代组与未分组必需锚点之间是 AND：每一项条件都要满足。",
            "- `required: false` 是可选内容，不阻塞转幕，也不能用它替代必需路线的 `required: true`。",
            "- 全部必需条件被结算确认为完成后自动进入下一幕；最后一幕的必需条件达成后进入通关结算。转幕是故事阶段变化，不等于必须立即换地点。",
            "",
            "例如“勘查灯室 A”独立必需，“找到脚印 B／取得证言 C”同属一个必需替代组，帮助渔民 D 可选；逻辑是 **A AND (B OR C)**，D 不参与门槛。若另有替代组 E/F，则变成 **A AND (B OR C) AND (E OR F)**。创作包完整范例提供 A/B/C/D 的合法 JSON。",
            "`transition_to_next_act.target_act` 指定下一幕；`condition` 只解释叙事前提，`transition_style` 只描述转场写法。平台不会把 condition 当成第二道独立程序门，也不会因为写了“玩家再次确认”就在条件达成后额外等待。真正必须发生的前提应写成必需锚点和可识别的 completion_signal。",
            "",
            "### 外部导入只接设定源",
            "",
            "创作 JSON 使用 `story_settings` v2 的人物、世界观、分幕、机制、素材及 `generation_parameters`；它不是游戏存档。不要附带 `initial_state`、`state_json`、`story_progress`、`state_delta_json`、`settlement_receipt`、回合、摘要、任务 ID、`revision` 或 `timeline_generation` 等内部运行数据；这些不是外部剧本导入的状态接口。格式版本 `format_version` 仍须保留。",
            "初始身份、开局已知信息和初始关系写进人物、世界观和故事前提；机制后果写成可观察的叙事事件，例如“沈兰把钥匙交给林决并说明用途”“接受包扎后伤口不再流血”“守门人因看到证据而由怀疑转为有限配合”。GM 写出实际后果后，平台再识别并结算物品、伤势、关系或已知事实；不要只写抽象的“关系升级”，也不要要求正文输出内部回执。",
            "`core_mechanics.rule` 等文字提供叙事约束，不是可执行脚本；导入设定不会直接注入物品栏或重写已发生的状态。",
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
            "分幕主线",
            "每幕公开目标、揭露范围和完成锚点。必需条件结算达成后自动转幕；condition 是叙事说明。",
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
            "[地点]",
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
        ("game_profile.title", "游戏标题", "1-40 字为宜；会同步到游戏标题。", "导入生效", "[游戏标题]"),
        ("game_profile.genre", "题材类型", "写清时代、风格、玩法类型；不要堆太多标签。", "导入生效", "[题材类型]"),
        ("game_profile.description", "一句话简介", "玩家和 GM 都可见的概述，不写隐藏真相。", "导入生效", "[一句话剧情简介]"),
        ("game_profile.tone", "整体基调", "影响 GM 语言气质和场景氛围。", "导入生效", "[基调关键词]"),
        ("game_profile.logline", "故事钩子", "给 GM 的一句话抓手，可比 description 更有戏剧性。", "导入生效", "[一句话故事钩子]"),
    ])
    _append_table_section(lines, "worldview", [
        ("worldview.summary", "公开世界观摘要", "玩家可理解的世界描述；不要写最终真相。", "导入生效", "[公开世界观摘要]"),
        ("worldview.setting", "初始舞台", "开局常用地点或区域。", "导入生效", "[初始地点]"),
        ("worldview.public_facts[]", "公开事实", "玩家开局或常识可知的信息。", "导入生效", "[一条公开事实]"),
        ("worldview.hidden_facts[]", "隐藏事实", "只给 GM 保持一致性，不能直接剧透。", "导入生效", "[一条隐藏事实，仅 GM 可见]"),
        ("worldview.core_conflicts[]", "核心冲突", "推动世界和势力行动的长期矛盾。", "导入生效", "[一条核心冲突]"),
        ("worldview.factions[]", "关键势力", "供 GM 安排冲突、压力和 NPC 立场。", "导入生效", "[势力名]"),
        ("worldview.locations[]", "关键地点", "供 GM 保持地点一致，避免凭空扩张。", "导入生效", "[地点名]"),
    ])
    _append_table_section(lines, "story_core", [
        ("story_core.premise", "剧本前提", "本局最核心的承诺；GM 不应偏离。", "导入生效", "[剧本前提]"),
        ("story_core.core_fantasy", "核心幻想", "玩家想体验的爽点或主题体验。", "导入生效", "[核心幻想/爽点]"),
        ("story_core.central_mystery", "核心悬念", "贯穿全剧的问题；不要在前几回合直接解答。", "导入生效", "[贯穿全剧的核心问题]"),
        ("story_core.main_goal", "长期目标", "GM 拉回主线时使用的方向。", "导入生效", "[长期目标]"),
        ("story_core.emotional_arc", "情感弧", "玩家情绪的长期走向，给 GM 把控基调推进。", "导入生效", "[情感走向，如从戒备到信任]"),
        ("story_core.narrative_style", "叙事风格", "GM 行文的语感取向，可比 tone 更具体。", "导入生效", "[叙事语感，如短句冷硬]"),
        ("story_core.current_act", "默认当前幕", "新游戏初始幕；已有游戏实际进度优先看当前状态。", "导入生效", "act_1"),
        ("story_core.must_preserve[]", "必须保留", "用户强要求、正典设定、必须出现内容。", "导入生效", "[必须保留的设定]"),
        ("story_core.must_not_become[]", "禁止变成", "类型红线，防止题材变味。", "导入生效", "[类型红线]"),
        ("story_core.forbidden_drift[]", "禁止偏离", "剧情长期不能滑向的方向。", "导入生效", "[禁止偏离的方向]"),
        ("story_core.canon_terms[]", "正典词条", "重要专名，帮助 GM 保持命名一致。", "导入生效", "[重要专名]"),
    ])
    _append_table_section(lines, "core_characters[]", [
        ("core_characters[].id", "稳定角色 id", "用英文或拼音 snake_case；不要随意改。", "导入生效", "main_char"),
        ("core_characters[].name", "角色名", "会同步到角色档案；不能为空。", "导入生效", "[角色名]"),
        ("core_characters[].aliases[]", "别名", "供 GM 识别同一角色的其他称呼，避免改名后认不出。", "导入生效", "[别名1]、[别名2]"),
        ("core_characters[].role", "角色类型", "建议 protagonist、companion、npc、antagonist、other。", "导入生效", "protagonist"),
        ("core_characters[].identity", "公开身份", "玩家可见身份，不写隐藏身份。", "导入生效", "[公开身份]"),
        ("core_characters[].description", "公开介绍", "玩家可见人物描述。", "导入生效", "[公开人物描述]"),
        ("core_characters[].appearance", "外貌", "用于角色展示和视觉一致性。", "导入生效", "[外貌描述]"),
        ("core_characters[].dramatic_function", "戏剧功能", "告诉 GM 该角色在主线中的作用。", "导入生效", "[戏剧功能，如线索守门人]"),
        ("core_characters[].desire/fear/leverage", "动机组", "决定 NPC 行动、谈判筹码和关系变化。", "导入生效", "[动机，如想夺回某物]"),
        ("core_characters[].relationship_arc", "关系弧", "该角色与主角关系的长期变化方向。", "导入生效", "[关系变化方向]"),
        ("core_characters[].public_limit", "公开边界", "按公开可观察的行为边界填写；完整秘密另放 gm_secret。", "导入生效", "没有可信证据前不肯提供帮助"),
        ("core_characters[].portrait_prompt", "立绘提示词", "用于生成角色立绘的描述；不写隐藏身份。", "导入生效", "[立绘描述，不含隐藏身份]"),
        ("core_characters[].visibility", "可见性", "visible 会展示给玩家；hidden 保留给 GM。", "导入生效", "visible"),
    ])
    _append_table_section(lines, "act_plan[]", [
        ("act_plan[].id", "幕 id", "必须唯一，建议 act_1、act_2 等；幕数按故事规模安排。", "导入生效", "act_1"),
        ("act_plan[].title", "幕标题", "会用于玩家目标栏；用不泄露未揭真相的公开标题。", "导入生效", "灯塔深处"),
        ("act_plan[].objective", "本幕目标", "会用于玩家目标栏；写当前可公开的方向，不写谜底。", "导入生效", "顺着已发现的线索继续调查"),
        ("act_plan[].dramatic_question", "戏剧问题", "决定本幕张力，不等于任务清单。", "导入生效", "[本幕戏剧问题]"),
        ("act_plan[].must_hit_beats[]", "必经节拍", "本幕希望出现的关键剧情节拍，给 GM 软引导。", "导入生效", "[关键节拍]"),
        ("act_plan[].allowed_reveals[]", "允许揭露", "本幕可以透露的信息边界。", "导入生效", "[本幕可揭露的信息]"),
        ("act_plan[].forbidden_reveals[]", "禁止揭露", "本幕不能提前说出的真相。", "导入生效", "[本幕禁止揭露的真相]"),
        ("act_plan[].completion_anchors[]", "完成锚点", "推进到下一幕前需要自然满足的条件。", "导入生效", "[完成条件]"),
        ("completion_anchors[].id", "锚点 id", "必须全局唯一；状态提取器用它标记完成。", "导入生效", "act_1_anchor_1"),
        ("completion_anchors[].title", "锚点标题", "供进度提示与 GM 识别，按可公开展示填写。", "导入生效", "取得关键证据"),
        ("completion_anchors[].required", "是否必达", "true 表示推进到下一幕前必须满足；默认 true。", "导入生效", "true"),
        ("completion_anchors[].alternative_group", "替代组", "同一幕多个 required 锚点填相同值时，完成其中任意一个即可满足该组；普通必达锚点留空。", "导入生效", "entry_path"),
        ("completion_anchors[].description", "锚点说明", "解释这个锚点要达成什么，给 GM 参考。", "导入生效", "[锚点要达成什么]"),
        ("completion_anchors[].completion_signal", "完成信号", "写成可从剧情文本识别的明确事件。", "导入生效", "[可识别的剧情事件]"),
        ("transition_to_next_act.target_act", "下一幕目标", "只能指向存在的 act id；最后一幕可留空对象。", "导入生效", "act_2"),
        ("transition_to_next_act.condition", "叙事转场说明", "不是独立程序门；真正的必需前提应写成 required 锚点。", "导入生效", "现场证据齐备后顺线索深入"),
        ("transition_to_next_act.transition_style", "转场写法", "给 GM 的叙事衔接建议，不改变锚点判定。", "导入生效", "顺线索深入"),
    ])
    _append_table_section(lines, "main_quest_path[]", [
        ("main_quest_path[].id", "主线节点 id", "稳定唯一，便于 AI 修改和引用。", "导入生效", "main_quest_1"),
        ("main_quest_path[].act_id", "所属幕", "必须对应 act_plan[].id。", "导入生效", "act_1"),
        ("main_quest_path[].title", "任务标题", "可作为玩家可见任务名。", "导入生效", "[任务标题]"),
        ("main_quest_path[].objective", "软目标", "给 GM 的推进方向，不强制玩家立刻执行。", "导入生效", "[软目标]"),
        ("main_quest_path[].player_visible", "玩家提示", "可公开显示，不写 GM 秘密。", "导入生效", "[玩家可见提示]"),
        ("main_quest_path[].completion_signal", "完成信号", "和锚点一样，写可识别事件。", "导入生效", "[可识别事件]"),
        ("main_quest_path[].optional", "是否支线", "true 表示可选支线，不阻塞主线推进；默认 false。", "导入生效", "false"),
    ])
    _append_table_section(lines, "core_mechanics[]", [
        ("core_mechanics[].id", "机制 id", "稳定唯一。", "导入生效", "investigation"),
        ("core_mechanics[].name", "机制名", "简短说明机制。", "导入生效", "[机制名]"),
        ("core_mechanics[].rule", "机制规则", "写 GM 必须长期遵守的可执行规则。", "导入生效", "[GM 长期遵守的规则]"),
        ("core_mechanics[].progression", "推进方式", "阶段、触发方式或叙事代价。", "导入生效", "[推进方式]"),
        ("core_mechanics[].visibility", "可见性", "public、mixed、gm_only。", "导入生效", "mixed"),
    ])
    _append_table_section(lines, "action_style_rules[]", [
        ("action_style_rules[].id", "行动风格 id", "稳定唯一。", "导入生效", "investigation"),
        ("action_style_rules[].name", "风格名", "简短标识该行动风格，便于诊断。", "导入生效", "[风格名]"),
        ("action_style_rules[].triggers[]", "触发词", "玩家输入命中后更容易选中该风格。", "导入生效", "[触发词1]、[触发词2]"),
        ("action_style_rules[].rule", "行动写法规则", "告诉 GM 该类行动怎么写结果、代价、线索。", "导入生效", "[该类行动的写法规则]"),
        ("action_style_rules[].priority", "优先级", "critical、high、medium、low；冲突时高优先。", "导入生效", "high"),
        ("action_style_rules[].enabled", "是否启用", "false 后不参与匹配。", "导入生效", "true"),
    ])
    _append_table_section(lines, "story_material_library[]", [
        ("story_material_library[].id", "素材 id", "稳定唯一，建议用可读英文或拼音。", "导入生效", "material_1"),
        ("story_material_library[].title", "素材标题", "GM 诊断和召回时显示。", "导入生效", "[素材标题]"),
        ("story_material_library[].type", "素材类型", "location、npc、item、secret、clue、pressure、twist 等。", "导入生效", "location"),
        ("story_material_library[].keywords[]", "关键词", "用于语义召回；写清专名和别名。", "导入生效", "[关键词1]、[关键词2]"),
        ("story_material_library[].triggers[]", "触发词", "玩家输入直接命中时强召回。", "导入生效", "[触发词]"),
        ("story_material_library[].priority", "召回优先级", "critical/high/medium/low；越高越容易被召回打分选中。", "导入生效", "high"),
        ("story_material_library[].always_on", "常驻注入", "critical 核心设定可 true；太多会耗 token。", "导入生效", "false"),
        ("story_material_library[].visibility", "可见性", "public、mixed、gm_only，控制素材信息暴露范围。", "导入生效", "mixed"),
        ("story_material_library[].public_info", "公开信息", "玩家可见，不写秘密。", "导入生效", "[玩家可见信息]"),
        ("story_material_library[].gm_secret", "GM 秘密", "只供 GM 保持一致，不能直接剧透。", "导入生效", "[仅 GM 可见的秘密]"),
        ("story_material_library[].content", "完整素材", "告诉 GM 这条素材如何影响剧情。", "导入生效", "[这条素材如何影响剧情]"),
        ("story_material_library[].usage", "使用规则", "何时召回、如何给线索、不能揭露什么。", "导入生效", "[何时召回、怎么给线索]"),
        ("story_material_library[].enabled", "是否启用", "false 后不参与召回匹配。", "导入生效", "true"),
    ])
    _append_table_section(lines, "home_base", [
        ("home_base.id", "据点 id", "稳定唯一。", "导入生效", "home_base"),
        ("home_base.name", "据点名", "可以是基地、安全屋、组织后台或移动据点。", "导入生效", "[据点名]"),
        ("home_base.role", "剧情作用", "说明据点如何服务休整、情报、升级和关系推进。", "导入生效", "[据点的剧情作用]"),
        ("home_base.public_functions[]", "公开功能", "玩家可用的功能。", "导入生效", "[玩家可用功能]"),
        ("home_base.hidden_hooks[]", "隐藏钩子", "GM 后续可用秘密。", "导入生效", "[GM 隐藏钩子]"),
    ])
    _append_table_section(lines, "hard_rules", [
        ("hard_rules.must_follow[]", "必须遵守", "最高优先级正向规则。", "导入生效", "每回合给出 A/B/C/D 四个行动选项。"),
        ("hard_rules.must_not[]", "绝对禁止", "不能被剧情、风格或模型自由发挥覆盖。", "导入生效", "[绝对禁止的内容]"),
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
            "- `public_*`、`player_visible`、角色公开字段及 `act_plan[].title/objective` 不能写隐藏真相。",
            "- `gm_secret`、`hidden_facts` 可以写完整秘密，但 GM 只能转化成线索，不应直接剧透。",
            "- `story_material_library[].always_on=true` 的素材会更稳定进入上下文，但过多会增加 token 消耗。",
            "- `generation_parameters.recent_turn_excerpt_chars` 越大，近期回合上下文越完整；越小越省 token。",
            "- `initial_state`、状态增量、回执、存档、当前状态、回合历史和摘要不在这个 JSON 内；状态后果应写为明确叙事，导入设定不会自动重写已经发生的剧情进度。",
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
