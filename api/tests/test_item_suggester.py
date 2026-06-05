import asyncio

from app.services.deepseek_client import DeepSeekError
from app.services.item_suggester import ItemSuggester, build_outline


class _OkRouter:
    def __init__(self, content: str) -> None:
        self._content = content

    async def use_flash(self, *args, **kwargs):
        class R:
            content = self._content
            model = "test"
        return R()


class _FailRouter:
    async def use_flash(self, *args, **kwargs):
        raise DeepSeekError("boom")


OUTLINE_SETTINGS = {
    "game_profile": {"title": "占位剧名", "genre": "悬疑", "tone": "压抑"},
    "story_core": {"premise": "占位前提", "central_mystery": "占位悬念"},
    "worldview": {"summary": "占位世界观一句话"},
    "core_characters": [{"name": "不该进大纲"}],
}


def test_build_outline_only_includes_concise_fields():
    text = build_outline(OUTLINE_SETTINGS)
    assert "占位剧名" in text
    assert "占位悬念" in text
    assert "占位世界观一句话" in text
    # 不泄漏全量设定（如角色数组）
    assert "不该进大纲" not in text


def test_suggest_success_filters_to_allowed_fields():
    content = '{"role": "npc", "description": "占位描述", "title": "改不了", "evil": "x"}'
    out = asyncio.run(
        ItemSuggester(router=_OkRouter(content)).suggest(
            "core_characters", {"name": "占位角色"}, OUTLINE_SETTINGS
        )
    )
    assert out["role"] == "npc"
    assert out["description"] == "占位描述"
    assert "title" not in out  # 身份字段不回写
    assert "name" not in out   # 身份字段不回写
    assert "evil" not in out   # 越界字段被剔除


def test_suggest_unknown_array_key_returns_empty():
    out = asyncio.run(
        ItemSuggester(router=_OkRouter("{}")).suggest("nope", {"name": "x"}, OUTLINE_SETTINGS)
    )
    assert out == {}


def test_suggest_fallback_on_llm_failure():
    out = asyncio.run(
        ItemSuggester(router=_FailRouter()).suggest(
            "core_characters", {"name": "x"}, OUTLINE_SETTINGS
        )
    )
    assert out == {}


def test_suggest_fallback_on_bad_json():
    out = asyncio.run(
        ItemSuggester(router=_OkRouter("not json at all")).suggest(
            "core_characters", {"name": "x"}, OUTLINE_SETTINGS
        )
    )
    assert out == {}
