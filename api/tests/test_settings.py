import anyio
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.deepseek_client import ChatCompletionResult
from app.services.model_router import ModelRouter
from app.services.runtime_settings import get_effective_deepseek_settings


def test_get_deepseek_settings_without_saved_key(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    client = TestClient(app)

    response = client.get("/api/settings/deepseek")

    assert response.status_code == 200
    body = response.json()
    assert body["api_key_configured"] is False
    assert body["api_key_masked"] is None
    assert body["api_key_source"] == "missing"
    assert body["flash_model"] == settings.deepseek_flash_model
    assert body["pro_model"] == settings.deepseek_pro_model
    assert body["task_model_routes"]["generator_interview"] == "pro"
    assert body["task_model_routes"]["generator_finalize_outline"] == "pro"
    assert body["task_model_routes"]["state_delta_extract"] == "flash"


def test_update_deepseek_settings_persists_runtime_config(db_session) -> None:
    client = TestClient(app)

    response = client.patch(
        "/api/settings/deepseek",
        json={
            "api_key": "sk-test-runtime-key",
            "base_url": "https://example.invalid/v1",
            "flash_model": "deepseek-flash-test",
            "pro_model": "deepseek-pro-test",
            "task_model_routes": {
                "generator_interview": "flash",
                "state_delta_extract": "pro",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["api_key_configured"] is True
    assert body["api_key_masked"] == "sk-t...-key"
    assert body["api_key_source"] == "database"
    assert body["base_url"] == "https://example.invalid/v1"
    assert body["flash_model"] == "deepseek-flash-test"
    assert body["pro_model"] == "deepseek-pro-test"
    assert body["task_model_routes"]["generator_interview"] == "flash"
    assert body["task_model_routes"]["state_delta_extract"] == "pro"
    assert body["task_model_routes"]["gm_runtime"] == "pro"

    effective_settings = get_effective_deepseek_settings()
    assert effective_settings.api_key == "sk-test-runtime-key"
    assert effective_settings.flash_model == "deepseek-flash-test"
    assert effective_settings.pro_model == "deepseek-pro-test"
    assert effective_settings.task_model_routes["generator_interview"] == "flash"
    assert effective_settings.task_model_routes["state_delta_extract"] == "pro"


def test_update_deepseek_settings_requires_admin_token_when_configured(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "settings_admin_token", "secret-token")
    client = TestClient(app)

    unauthorized = client.patch(
        "/api/settings/deepseek",
        json={"api_key": "sk-blocked"},
    )
    authorized = client.patch(
        "/api/settings/deepseek",
        headers={"X-Settings-Admin-Token": "secret-token"},
        json={"api_key": "sk-allowed"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["api_key_source"] == "database"


def test_model_router_uses_saved_task_model_routes(db_session) -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        async def chat_completion(self, **kwargs):
            calls.append(kwargs)
            return ChatCompletionResult(content="{}", model=kwargs["model"], raw={})

    client = TestClient(app)
    response = client.patch(
        "/api/settings/deepseek",
        json={
            "flash_model": "deepseek-flash-test",
            "pro_model": "deepseek-pro-test",
            "task_model_routes": {
                "state_delta_extract": "pro",
                "generator_finalize": "flash",
                "generator_finalize_lore_entries": "flash",
            },
        },
    )
    assert response.status_code == 200

    router = ModelRouter(client=FakeClient(), app_settings=settings)
    anyio.run(
        router.use_flash,
        "state_delta_extract",
        [{"role": "user", "content": "test"}],
    )
    anyio.run(
        router.use_pro,
        "generator_finalize",
        [{"role": "user", "content": "test"}],
    )
    anyio.run(
        router.use_pro,
        "generator_finalize_lore_entries",
        [{"role": "user", "content": "test"}],
    )

    assert calls[0]["model"] == "deepseek-pro-test"
    assert calls[1]["model"] == "deepseek-flash-test"
    assert calls[2]["model"] == "deepseek-flash-test"
