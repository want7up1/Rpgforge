import asyncio

from app.services.module_library import (
    merge_modules_into_settings,
    preview_module_merge,
    project_target_context,
)


def _base():
    return {
        "format_version": "rpgforge.story.v2",
        "core_characters": [{"name": "主角", "role": "protagonist"}],
        "story_core": {"canon_terms": ["旧城"]},
        "hard_rules": {"must_follow": ["细致描写"]},
    }


def test_string_bucket_dedup_and_append():
    items = [{"id": "m1", "payload": {"story_core": {"canon_terms": ["旧城", "新塔"]}}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    assert settings["story_core"]["canon_terms"] == ["旧城", "新塔"]  # 旧城去重
    assert report.deduped == 1
    assert report.entries[0]["action"] == "added"


def test_list_item_added_when_no_conflict():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "红伞客", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    names = [c["name"] for c in settings["core_characters"]]
    assert names == ["主角", "红伞客"]
    assert report.entries[0]["action"] == "added"


def test_identity_conflict_default_rename():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    names = [c["name"] for c in settings["core_characters"]]
    assert names == ["主角", "主角 (2)"]
    e = report.entries[0]
    assert e["action"] == "renamed" and e["conflict"] is True and e["renamed_to"] == "主角 (2)"


def test_identity_conflict_overwrite():
    items = [
        {
            "id": "m1",
            "payload": {"core_characters": [{"name": "主角", "role": "npc", "desire": "x"}]},
        }
    ]
    settings, report = merge_modules_into_settings(_base(), items, {"m1": "overwrite"})
    chars = settings["core_characters"]
    assert len(chars) == 1 and chars[0]["role"] == "npc" and chars[0]["desire"] == "x"
    assert report.entries[0]["action"] == "overwritten"


def test_identity_conflict_skip():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {"m1": "skip"})
    assert [c["name"] for c in settings["core_characters"]] == ["主角"]
    assert report.entries[0]["action"] == "skipped"


def test_scalar_game_profile_merges_fields():
    items = [{"id": "m1", "payload": {"game_profile": {"title": "新名", "tone": "阴郁"}}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    assert settings["game_profile"]["title"] == "新名"
    assert settings["game_profile"]["tone"] == "阴郁"


def test_scalar_story_core_central_mystery_merges():
    base = _base()
    base["story_core"]["central_mystery"] = "旧谜"
    items = [{"id": "m1", "payload": {"story_core": {"central_mystery": "新谜"}}}]
    settings, _ = merge_modules_into_settings(base, items, {})
    assert settings["story_core"]["central_mystery"] == "新谜"
    assert settings["story_core"]["canon_terms"] == ["旧城"]  # 同级桶不丢


def test_act_rename_reids_anchors_and_passes_validate():
    base = _base()
    base["act_plan"] = [{
        "id": "act_1", "title": "序",
        "completion_anchors": [{"id": "act_1_a1", "title": "锚", "required": True}],
    }]
    items = [{"id": "m1", "payload": {"act_plan": [{
        "id": "act_1", "title": "另一序",
        "completion_anchors": [{"id": "act_1_a1", "title": "锚2", "required": True}],
    }]}}]
    settings, report = merge_modules_into_settings(base, items, {})
    acts = settings["act_plan"]
    assert len(acts) == 2
    anchor_ids = [a["id"] for act in acts for a in act["completion_anchors"]]
    assert len(anchor_ids) == len(set(anchor_ids))  # 全局唯一，validate 不报错


class _IdentityAdapter:
    async def adapt(self, payload, context):
        return payload  # 不改


class _RenameAdapter:
    async def adapt(self, payload, context):
        # 模拟本地优化：把角色名改成贴合目标
        p = {k: v for k, v in payload.items()}
        p["core_characters"] = [{**c, "name": "红伞客"} for c in payload["core_characters"]]
        return p


def test_project_target_context_extracts_canon_and_characters():
    ctx = project_target_context(_base())
    assert ctx["canon_terms"] == ["旧城"]
    assert ctx["characters"] == [{"name": "主角", "role": "protagonist"}]


def test_preview_no_adapt_merges_directly():
    modules = [{"id": "m1", "name": "客", "module_type": "characters",
                "payload": {"core_characters": [{"name": "红伞客", "role": "npc"}]}}]
    out = asyncio.run(preview_module_merge(_base(), modules, adapt=False,
                                           resolutions={}, adapter=_IdentityAdapter()))
    assert [c["name"] for c in out["merged_settings"]["core_characters"]] == ["主角", "红伞客"]
    assert out["adapted"] == []


def test_preview_adapt_records_before_after():
    modules = [{"id": "m1", "name": "破晓", "module_type": "characters",
                "payload": {"core_characters": [{"name": "破晓", "role": "npc"}]}}]
    out = asyncio.run(preview_module_merge(_base(), modules, adapt=True,
                                           resolutions={}, adapter=_RenameAdapter()))
    assert out["adapted"][0]["before"]["core_characters"][0]["name"] == "破晓"
    assert out["adapted"][0]["after"]["core_characters"][0]["name"] == "红伞客"
    assert [c["name"] for c in out["merged_settings"]["core_characters"]] == ["主角", "红伞客"]
