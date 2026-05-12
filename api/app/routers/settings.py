from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.schemas.settings import DeepSeekSettingsRead, DeepSeekSettingsUpdate
from app.services.runtime_settings import (
    get_effective_deepseek_settings,
    get_or_create_runtime_settings,
    mask_secret,
    normalize_task_model_routes,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
DB_DEPENDENCY = Depends(get_db)


def verify_settings_token(
    x_settings_admin_token: str | None = Header(default=None),
) -> None:
    expected = settings.settings_admin_token.strip()
    if not expected and settings.app_env.lower() in {"production", "prod"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="生产环境未配置 SETTINGS_ADMIN_TOKEN，禁止从前端保存模型/API 设置。",
        )
    if expected and x_settings_admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="设置保存失败：管理 Token 无效。",
        )


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
        settings_protected=bool(settings.settings_admin_token.strip()),
    )


@router.patch(
    "/deepseek",
    response_model=DeepSeekSettingsRead,
    dependencies=[Depends(verify_settings_token)],
)
def update_deepseek_settings(
    payload: DeepSeekSettingsUpdate,
    db: Session = DB_DEPENDENCY,
) -> DeepSeekSettingsRead:
    runtime_settings = get_or_create_runtime_settings(db)

    if payload.clear_api_key:
        runtime_settings.deepseek_api_key = None
    elif payload.api_key is not None and payload.api_key.strip():
        runtime_settings.deepseek_api_key = payload.api_key.strip()

    if payload.base_url is not None:
        runtime_settings.deepseek_base_url = payload.base_url.strip() or None
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
