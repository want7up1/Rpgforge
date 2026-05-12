from app.services.prompt_loader import load_prompt_template


def test_character_generation_prompt_omits_aliases_and_portrait_prompt() -> None:
    full_prompt = load_prompt_template("generate_game_config.md")
    section_prompt = load_prompt_template("generate_config_section.md")

    for prompt in (full_prompt, section_prompt):
        assert "aliases 必须使用空数组" in prompt
        assert "portrait_prompt 必须使用空字符串" in prompt
        assert "characters.appearance 必须详细" in prompt
