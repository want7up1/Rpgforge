from app.services.prompt_loader import load_prompt_template


def test_gm_runtime_prompt_uses_story_settings_v2_runtime_contract() -> None:
    prompt = load_prompt_template("gm_runtime.md")

    assert "runtime_story 是唯一剧本设定运行视图" in prompt
    assert "story_settings v2" in prompt
    assert "A、B、C、D 四个具体行动选项" in prompt
    assert "generation_parameters" in prompt
    assert "script_outline" not in prompt
    assert "campaign_contract" not in prompt


def test_story_director_prompt_uses_current_act_anchors() -> None:
    prompt = load_prompt_template("story_director.md")

    assert "runtime_story 是唯一剧本设定运行视图" in prompt
    assert "completion_anchors" in prompt
    assert "required=true" in prompt
    assert "active_material_titles" in prompt
