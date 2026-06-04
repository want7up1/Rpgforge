import asyncio

from app.services.deepseek_client import DeepSeekError
from app.services.module_adapter import ModuleAdapter


class _FailRouter:
    async def use_pro(self, *args, **kwargs):
        raise DeepSeekError("boom")


class _OkRouter:
    async def use_pro(self, *args, **kwargs):
        class R:
            content = '{"core_characters": [{"name": "红伞客", "role": "npc"}]}'
            model = "test"
        return R()


def test_adapt_fallback_returns_original_on_failure():
    payload = {"core_characters": [{"name": "破晓", "role": "npc"}]}
    out = asyncio.run(ModuleAdapter(router=_FailRouter()).adapt(payload, {"canon_terms": ["雁回镇"]}))
    assert out == payload  # 失败回退原样


def test_adapt_success_returns_adapted_same_shape():
    payload = {"core_characters": [{"name": "破晓", "role": "npc"}]}
    out = asyncio.run(ModuleAdapter(router=_OkRouter()).adapt(payload, {"canon_terms": ["雁回镇"]}))
    assert list(out.keys()) == ["core_characters"]
    assert out["core_characters"][0]["name"] == "红伞客"


def test_adapt_rejects_shape_change_falls_back():
    # LLM 返回顶层键集合不一致 → 回退原 payload
    class _DriftRouter:
        async def use_pro(self, *args, **kwargs):
            class R:
                content = '{"hard_rules": {"must_follow": ["x"]}}'
                model = "test"
            return R()
    payload = {"core_characters": [{"name": "破晓"}]}
    out = asyncio.run(ModuleAdapter(router=_DriftRouter()).adapt(payload, {}))
    assert out == payload
