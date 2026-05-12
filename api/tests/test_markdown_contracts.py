from app.schemas.generator import GeneratedGameConfig
from app.services.game_generator import _system_prompt
from app.services.prompt_loader import load_prompt_template


def test_gm_runtime_prompt_contains_story_markdown_contract() -> None:
    prompt = load_prompt_template("gm_runtime.md")

    assert "RPGForge 剧情 Markdown 契约" in prompt
    assert "优先于当前游戏 system_prompt" in prompt
    assert "不要把 A/B/C/D 选项写进正文" in prompt
    assert "不在 narrative 输出 XP、技能、关系、物品得失等结算内容" in prompt
    assert "`` `编号/密码/坐标` ``" in prompt


def test_generated_game_config_default_system_prompt_uses_contract() -> None:
    config = GeneratedGameConfig(
        title="测试冒险",
        system_prompt=None,
        lore_entries=[],
        modes=[],
        initial_state={},
    )

    assert "RPGForge 剧情 Markdown 契约" in config.system_prompt
    assert "A/B/C/D" in config.system_prompt


def test_game_generator_fallback_system_prompt_uses_contract() -> None:
    prompt = _system_prompt({}, {})

    assert "RPGForge 剧情 Markdown 契约" in prompt
    assert "campaign_contract" in prompt
