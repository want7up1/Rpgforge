from dataclasses import replace
from functools import partial

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import settings as settings_router
from app.services.model_discovery import (
    MAX_MODEL_RESPONSE_BYTES,
    ModelDiscoveryError,
    discover_models,
    model_origin,
    normalize_model_base_url,
    recommend_model_slots,
)
from app.services.runtime_settings import EffectiveDeepSeekSettings

CURRENT = EffectiveDeepSeekSettings(
    api_key="saved-test-key-not-a-real-secret", api_key_source="database",
    base_url="https://models.example.invalid/v1",
    flash_model="deepseek-v4-flash", pro_model="deepseek-v4-pro", task_model_routes={},
)


def discover(handler, current=CURRENT, **kwargs):
    return anyio.run(partial(
        discover_models, current, transport=httpx.MockTransport(handler), **kwargs
    ))


def test_models_get_normalizes_chat_url_and_identifies_real_returned_slots():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [
            {"id": "deepseek-flash", "output_modalities": ["text"]},
            {"id": "deepseek-v4-pro", "output_modalities": ["text"]},
        ]})

    result = discover(handler, base_url="https://models.example.invalid/v1/chat/completions/")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "https://models.example.invalid/v1/models"
    assert requests[0].headers["Authorization"] == f"Bearer {CURRENT.api_key}"
    assert result.models == ["deepseek-flash", "deepseek-v4-pro"]
    assert result.flash_model == "deepseek-flash"
    assert result.pro_model == "deepseek-v4-pro"
    assert CURRENT.flash_model == "deepseek-v4-flash"


def test_discovery_filters_explicit_non_chat_but_preserves_text_multimodal_and_custom_ids():
    result = discover(lambda _request: httpx.Response(200, json={"data": [
        {"id": "text-embedding-3-small"}, {"id": "tts-1"}, {"id": "whisper-1"},
        {"id": "dall-e-3"}, {"id": "gpt-image-1"}, {"id": "provider/gpt-image-1"},
        {"id": "bge-reranker-v2"},
        {"id": "qwen3-embedding"},
        {"id": "opaque-picture", "output_modalities": ["image"]},
        {"id": "opaque-audio", "type": "audio"},
        {"id": "vision-chat", "input_modalities": ["text", "image"],
         "output_modalities": ["text"]},
        {"id": "text-and-audio-chat", "output_modalities": ["text", "audio"]},
        {"id": "custom-model"}, {"id": "custom-model"},
        {"id": "embedding-aware-chat", "capabilities": {"chat": True}},
    ]}))
    assert result.models == [
        "vision-chat", "text-and-audio-chat", "custom-model", "embedding-aware-chat",
    ]
    assert result.flash_model in result.models and result.pro_model in result.models


def test_existing_valid_choices_are_preserved_and_single_model_fills_both_slots():
    assert recommend_model_slots(
        ["custom-a", "custom-b", "deepseek-flash"],
        current_flash="custom-b", current_pro="custom-a",
    ) == ("custom-b", "custom-a")
    result = discover(lambda _request: httpx.Response(200, json={"data": [{"id": "only-chat"}]}))
    assert result.flash_model == result.pro_model == "only-chat"


@pytest.mark.parametrize("url", [
    "file:///tmp/models", "https://user:password@models.example.invalid/v1",
    "https://@models.example.invalid", "https://models.example.invalid/v1?secret=bad",
    "https://models.example.invalid/v1#fragment", "https://models.example.invalid:bad/v1",
    "https://models.example.invalid\\@other.example.invalid/v1", "https://models.\ninvalid/v1",
])
def test_invalid_urls_fail_safely_without_a_request(url):
    called = False

    def handler(_request):
        nonlocal called
        called = True
        raise AssertionError("invalid URL reached transport")

    with pytest.raises(ModelDiscoveryError) as error:
        discover(handler, base_url=url)
    assert error.value.status_code == 400
    assert CURRENT.api_key not in str(error.value)
    assert called is False


@pytest.mark.parametrize("url", [
    "https://other.example.invalid/v1", "http://models.example.invalid/v1",
    "https://models.example.invalid:8443/v1",
])
def test_saved_key_is_never_sent_to_a_different_origin(url):
    with pytest.raises(ModelDiscoveryError) as error:
        discover(lambda _request: pytest.fail("saved key crossed origin"), base_url=url)
    assert error.value.status_code == 400
    assert "重新输入" in str(error.value)


def test_explicit_new_key_allows_new_origin_and_blank_fields_reuse_current_values():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"id": "available"}]})

    discover(handler, base_url="https://other.example.invalid/v1", api_key="explicit-new-key")
    assert requests[0].url.host == "other.example.invalid"
    assert requests[0].headers["Authorization"] == "Bearer explicit-new-key"
    discover(handler, base_url=" ", api_key=" ")
    assert str(requests[1].url) == "https://models.example.invalid/v1/models"
    assert requests[1].headers["Authorization"] == f"Bearer {CURRENT.api_key}"
    assert model_origin("https://MODELS.example.invalid:443/v1") == model_origin(CURRENT.base_url)
    assert normalize_model_base_url("") == "https://api.deepseek.com"


def test_missing_key_and_invalid_header_characters_do_not_reach_transport():
    for current, supplied in (
        (replace(CURRENT, api_key=""), None), (CURRENT, "invalid\nkey"),
    ):
        with pytest.raises(ModelDiscoveryError) as error:
            discover(lambda _request: pytest.fail("bad key reached transport"),
                     current=current, api_key=supplied)
        assert error.value.status_code == 400


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_are_not_followed_and_do_not_echo_key_or_destination(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={
            "Location": f"https://unexpected.invalid/models?key={CURRENT.api_key}",
        }, text=CURRENT.api_key)

    with pytest.raises(ModelDiscoveryError) as error:
        discover(handler)
    assert len(requests) == 1
    assert error.value.status_code == 502
    assert CURRENT.api_key not in str(error.value)
    assert "unexpected.invalid" not in str(error.value)


@pytest.mark.parametrize("status,expected", [
    (401, 401), (403, 403), (404, 404), (429, 429), (500, 502),
])
def test_upstream_errors_have_safe_chinese_messages(status, expected):
    with pytest.raises(ModelDiscoveryError) as error:
        discover(lambda _request: httpx.Response(status, text=CURRENT.api_key + " PRIVATE_BODY"))
    assert error.value.status_code == expected
    assert CURRENT.api_key not in str(error.value) and "PRIVATE_BODY" not in str(error.value)


@pytest.mark.parametrize("kind,expected", [("timeout", 504), ("connection", 502), ("json", 502)])
def test_transport_and_json_errors_do_not_echo_exception_or_body(kind, expected):
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout(CURRENT.api_key, request=request)
        if kind == "connection":
            raise httpx.ConnectError(CURRENT.api_key, request=request)
        return httpx.Response(200, text=CURRENT.api_key + " invalid JSON")

    with pytest.raises(ModelDiscoveryError) as error:
        discover(handler)
    assert error.value.status_code == expected
    assert CURRENT.api_key not in str(error.value)


@pytest.mark.parametrize("body,expected", [
    ({"data": []}, 400), ({"data": [{"id": "tts-1"}]}, 400),
    ({"data": [{"id": CURRENT.api_key}]}, 400), ({"data": "invalid"}, 502), ([], 502),
])
def test_empty_nonchat_and_malformed_lists_fail_safely(body, expected):
    with pytest.raises(ModelDiscoveryError) as error:
        discover(lambda _request: httpx.Response(200, json=body))
    assert error.value.status_code == expected
    assert CURRENT.api_key not in str(error.value)


def test_http_contract_is_read_only_and_does_not_return_credentials(monkeypatch):
    monkeypatch.setattr(settings_router, "get_effective_deepseek_settings", lambda: CURRENT)
    monkeypatch.setattr(settings_router, "get_or_create_runtime_settings",
                        lambda *_args: pytest.fail("discovery tried to write settings"))
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"id": "only-chat"}]})

    async def mocked_discovery(current, **kwargs):
        return await discover_models(current, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(settings_router, "discover_models", mocked_discovery)
    with TestClient(app) as client:
        response = client.post("/api/settings/deepseek/models", json={})
        assert response.status_code == 200
        assert response.json() == {
            "models": [{"id": "only-chat"}], "flash_model": "only-chat", "pro_model": "only-chat",
        }
        assert CURRENT.api_key not in response.text
        assert client.get("/api/settings/deepseek").json()["settings_protected"] is False
    assert len(requests) == 1 and requests[0].method == "GET"


def test_patch_cannot_rebind_saved_key_without_explicit_new_key_or_persist_changes(monkeypatch):
    monkeypatch.setattr(settings_router, "get_effective_deepseek_settings", lambda: CURRENT)
    monkeypatch.setattr(settings_router, "get_or_create_runtime_settings",
                        lambda *_args: pytest.fail("rejected update wrote settings"))
    with TestClient(app) as client:
        response = client.patch("/api/settings/deepseek", json={
            "base_url": "https://other.example.invalid/v1",
        })
    assert response.status_code == 400
    assert "重新输入" in response.json()["detail"]
    assert CURRENT.api_key not in response.text


def test_returned_ids_fit_settings_save_limit():
    from app.schemas.settings import DeepSeekSettingsUpdate

    valid = "x" * 128
    result = discover(lambda _request: httpx.Response(200, json={"data": [
        {"id": "x" * 129}, {"id": valid},
    ]}))
    assert result.models == [valid]
    assert DeepSeekSettingsUpdate(flash_model=result.flash_model).flash_model == valid


def test_slot_identification_does_not_treat_provider_or_gemini_as_pro_or_mini():
    assert recommend_model_slots(
        ["provider/gemini-2.5-pro", "provider/gemini-2.5-flash"],
        current_flash="", current_pro="",
    ) == ("provider/gemini-2.5-flash", "provider/gemini-2.5-pro")


@pytest.mark.parametrize("has_content_length", [True, False])
def test_response_size_is_bounded_even_without_content_length(has_content_length):
    class LargeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(MAX_MODEL_RESPONSE_BYTES // (64 * 1024) + 1):
                yield b"x" * (64 * 1024)

    def handler(_request):
        headers = (
            {"Content-Length": str(MAX_MODEL_RESPONSE_BYTES + 1)} if has_content_length else {}
        )
        return httpx.Response(200, headers=headers, stream=LargeStream())

    with pytest.raises(ModelDiscoveryError) as error:
        discover(handler)
    assert error.value.status_code == 502
    assert "响应过大" in str(error.value)
