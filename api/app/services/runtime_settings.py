from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.db.session import SessionLocal
from app.models.runtime_settings import RuntimeSettings

RUNTIME_SETTINGS_ID = 1
ModelSlot = Literal["flash", "pro"]

DEFAULT_TASK_MODEL_ROUTES: dict[str, ModelSlot] = {
    "generator_interview": "pro",
    "generator_finalize": "pro",
    "generator_finalize_outline": "pro",
    "generator_finalize_core_characters": "pro",
    "generator_finalize_act_plan": "pro",
    "generator_finalize_main_quest_path": "pro",
    "generator_finalize_core_mechanics": "pro",
    "generator_finalize_action_style_rules": "pro",
    "generator_finalize_story_material_library": "pro",
    "generator_finalize_home_base": "pro",
    "generator_finalize_hard_rules": "pro",
    "generator_finalize_initial_state": "pro",
    "gm_runtime": "pro",
    "gm_runtime_rewrite": "pro",
    "story_director": "flash",
    "drift_validator": "flash",
    "state_delta_extract": "flash",
    "compress_context": "flash",
}


@dataclass(frozen=True)
class EffectiveDeepSeekSettings:
    api_key: str
    api_key_source: str
    base_url: str
    flash_model: str
    pro_model: str
    task_model_routes: dict[str, ModelSlot]


def get_or_create_runtime_settings(db: Session) -> RuntimeSettings:
    runtime_settings = db.get(RuntimeSettings, RUNTIME_SETTINGS_ID)
    if runtime_settings is not None:
        return runtime_settings

    runtime_settings = RuntimeSettings(id=RUNTIME_SETTINGS_ID)
    db.add(runtime_settings)
    db.commit()
    db.refresh(runtime_settings)
    return runtime_settings


def get_effective_deepseek_settings(
    app_settings: Settings = settings,
) -> EffectiveDeepSeekSettings:
    try:
        with SessionLocal() as db:
            runtime_settings = db.get(RuntimeSettings, RUNTIME_SETTINGS_ID)
            if runtime_settings is None:
                return _environment_deepseek_settings(app_settings)
            return _merge_deepseek_settings(runtime_settings, app_settings)
    except SQLAlchemyError:
        return _environment_deepseek_settings(app_settings)


def mask_secret(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def normalize_task_model_routes(value: object | None) -> dict[str, ModelSlot]:
    normalized = dict(DEFAULT_TASK_MODEL_ROUTES)
    if not isinstance(value, dict):
        return normalized

    for task_type in DEFAULT_TASK_MODEL_ROUTES:
        slot = value.get(task_type)
        if slot in ("flash", "pro"):
            normalized[task_type] = slot
    return normalized


def _merge_deepseek_settings(
    runtime_settings: RuntimeSettings,
    app_settings: Settings,
) -> EffectiveDeepSeekSettings:
    database_key = (runtime_settings.deepseek_api_key or "").strip()
    environment_key = app_settings.deepseek_api_key.strip()
    api_key = database_key or environment_key
    api_key_source = "database" if database_key else "environment" if environment_key else "missing"

    return EffectiveDeepSeekSettings(
        api_key=api_key,
        api_key_source=api_key_source,
        base_url=(
            (runtime_settings.deepseek_base_url or "").strip()
            or app_settings.deepseek_base_url.strip()
        ),
        flash_model=(
            (runtime_settings.deepseek_flash_model or "").strip()
            or app_settings.deepseek_flash_model
        ),
        pro_model=(
            (runtime_settings.deepseek_pro_model or "").strip()
            or app_settings.deepseek_pro_model
        ),
        task_model_routes=normalize_task_model_routes(
            runtime_settings.deepseek_task_model_routes
        ),
    )


def _environment_deepseek_settings(app_settings: Settings) -> EffectiveDeepSeekSettings:
    api_key = app_settings.deepseek_api_key.strip()
    return EffectiveDeepSeekSettings(
        api_key=api_key,
        api_key_source="environment" if api_key else "missing",
        base_url=app_settings.deepseek_base_url.strip(),
        flash_model=app_settings.deepseek_flash_model,
        pro_model=app_settings.deepseek_pro_model,
        task_model_routes=normalize_task_model_routes(None),
    )
