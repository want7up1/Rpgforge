from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.schemas.settings import (
    DeepSeekModelChoice,
    DeepSeekModelDiscoveryRead,
    DeepSeekModelDiscoveryRequest,
    DeepSeekSettingsRead,
    DeepSeekSettingsUpdate,
)
from app.services.model_discovery import (
    ModelDiscoveryError,
    discover_models,
    model_origin,
    normalize_model_base_url,
)
from app.services.runtime_settings import (
    get_effective_deepseek_settings,
    get_or_create_runtime_settings,
    mask_secret,
    normalize_task_model_routes,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
DB_DEPENDENCY = Depends(get_db)


@router.get("/deepseek", response_model=DeepSeekSettingsRead)
def get_deepseek_settings() -> DeepSeekSettingsRead:
    effective_settings = get_effective_deepseek_settings()
    return DeepSeekSettingsRead(
        api_key_configured=bool(effective_settings.api_key),
        api_key_masked=mask_secret(effective_settings.api_key),
        api_key_source=effective_settings.api_key_source,
        base_url=effective_settings.base_url,
        flash_model=effective_settings.flash_model,
        pro_model=effective_settings.pro_model,
        task_model_routes=effective_settings.task_model_routes,
        settings_protected=False,
    )


@router.patch(
    "/deepseek",
    response_model=DeepSeekSettingsRead,
)
def update_deepseek_settings(
    payload: DeepSeekSettingsUpdate,
    db: Session = DB_DEPENDENCY,
) -> DeepSeekSettingsRead:
    normalized_base_url = None
    if payload.base_url is not None:
        try:
            normalized_base_url = normalize_model_base_url(
                payload.base_url if payload.base_url.strip() else settings.deepseek_base_url
            )
            current = get_effective_deepseek_settings()
            supplied_key = (payload.api_key or "").strip() if not payload.clear_api_key else ""
            retained_key = settings.deepseek_api_key if payload.clear_api_key else current.api_key
            if (
                retained_key.strip() and not supplied_key
                and model_origin(normalized_base_url) != model_origin(current.base_url)
            ):
                raise ModelDiscoveryError(400, "服务地址已更换，请重新输入 API Key 后再保存。")
        except ModelDiscoveryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    runtime_settings = get_or_create_runtime_settings(db)

    if payload.clear_api_key:
        runtime_settings.deepseek_api_key = None
    elif payload.api_key is not None and payload.api_key.strip():
        runtime_settings.deepseek_api_key = payload.api_key.strip()

    if payload.base_url is not None:
        runtime_settings.deepseek_base_url = (
            normalized_base_url if payload.base_url.strip() else None
        )
    if payload.flash_model is not None:
        runtime_settings.deepseek_flash_model = payload.flash_model.strip()
    if payload.pro_model is not None:
        runtime_settings.deepseek_pro_model = payload.pro_model.strip()
    if payload.task_model_routes is not None:
        merged_routes = normalize_task_model_routes(
            runtime_settings.deepseek_task_model_routes
        )
        merged_routes.update(payload.task_model_routes)
        runtime_settings.deepseek_task_model_routes = normalize_task_model_routes(merged_routes)

    db.add(runtime_settings)
    db.commit()
    return get_deepseek_settings()


@router.post("/deepseek/models", response_model=DeepSeekModelDiscoveryRead)
async def list_deepseek_models(
    payload: DeepSeekModelDiscoveryRequest,
) -> DeepSeekModelDiscoveryRead:
    try:
        found = await discover_models(
            get_effective_deepseek_settings(), base_url=payload.base_url, api_key=payload.api_key
        )
    except ModelDiscoveryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return DeepSeekModelDiscoveryRead(
        models=[DeepSeekModelChoice(id=model_id) for model_id in found.models],
        flash_model=found.flash_model, pro_model=found.pro_model,
    )
