from app.services.module_library import merge_modules_into_settings


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
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc", "desire": "x"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {"m1": "overwrite"})
    chars = settings["core_characters"]
    assert len(chars) == 1 and chars[0]["role"] == "npc" and chars[0]["desire"] == "x"
    assert report.entries[0]["action"] == "overwritten"


def test_identity_conflict_skip():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {"m1": "skip"})
    assert [c["name"] for c in settings["core_characters"]] == ["主角"]
    assert report.entries[0]["action"] == "skipped"


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
