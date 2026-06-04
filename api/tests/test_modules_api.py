from fastapi.testclient import TestClient

from app.main import app


def _create(client, name="测试机制", mtype="mechanics", payload=None, tags=None):
    return client.post("/api/modules", json={
        "name": name, "module_type": mtype,
        "payload": payload or {"core_mechanics": [{"name": name, "rule": "占位规则"}]},
        "tags": tags or [],
    })


def test_create_list_patch_delete(reset_database):
    client = TestClient(app)
    created = _create(client).json()
    assert created["module_type"] == "mechanics"

    listing = client.get("/api/modules").json()
    assert len(listing) == 1

    patched = client.patch(f"/api/modules/{created['id']}", json={"tags": ["占位标签"]}).json()
    assert patched["tags"] == ["占位标签"]
    assert client.get("/api/modules?tag=占位标签").json()[0]["id"] == created["id"]

    assert client.delete(f"/api/modules/{created['id']}").status_code == 204
    assert client.get("/api/modules").json() == []


def test_export_then_import_roundtrip(reset_database):
    client = TestClient(app)
    created = _create(client).json()
    exported = client.get(f"/api/modules/export?ids={created['id']}").json()
    assert exported["format_version"] == "rpgforge.modules.v1"
    client.delete(f"/api/modules/{created['id']}")
    imported = client.post("/api/modules/import", json=exported).json()
    assert len(imported) == 1 and imported[0]["name"] == created["name"]


def test_merge_preview_no_adapt(reset_database):
    client = TestClient(app)
    module = _create(client, name="占位机制",
                     payload={"core_mechanics": [{"name": "占位机制", "rule": "占位"}]}).json()
    target = {
        "format_version": "rpgforge.story.v2",
        "core_characters": [{"name": "主角", "role": "protagonist"}],
    }
    resp = client.post("/api/modules/merge-preview", json={
        "target_settings": target, "module_ids": [module["id"]], "adapt": False,
    }).json()
    names = [m["name"] for m in resp["merged_settings"]["core_mechanics"]]
    assert "占位机制" in names
    assert resp["report"]["entries"][0]["action"] == "added"
