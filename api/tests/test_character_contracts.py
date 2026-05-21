from app.services.prompt_loader import load_prompt_template


def test_character_generation_prompt_keeps_portrait_fields_empty() -> None:
    outline_prompt = load_prompt_template("generate_config_outline.md")
    section_prompt = load_prompt_template("generate_config_section.md")

    assert "core_characters_outline" in outline_prompt
    assert "portrait_prompt" in section_prompt
    assert "aliases 一律为空数组" in section_prompt
    assert "portrait_prompt 一律为空字符串" in section_prompt
    assert "appearance" in section_prompt
