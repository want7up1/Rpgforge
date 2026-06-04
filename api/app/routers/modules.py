import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.setting_module import SettingModule
from app.schemas.module import (
    MODULE_EXPORT_FORMAT_VERSION,
    MergePreviewRequest,
    MergePreviewResult,
    ModuleImportFile,
    SettingModuleCreate,
    SettingModulePatch,
    SettingModuleRead,
)
from app.services.module_adapter import ModuleAdapter
from app.services.module_library import preview_module_merge

router = APIRouter(prefix="/api/modules", tags=["modules"])
DB_DEPENDENCY = Depends(get_db)


@router.get("", response_model=list[SettingModuleRead])
def list_modules(
    type: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    db: Session = DB_DEPENDENCY,
) -> list[SettingModule]:
    stmt = select(SettingModule).order_by(SettingModule.updated_at.desc())
    if type:
        stmt = stmt.where(SettingModule.module_type == type)
    rows = list(db.scalars(stmt).all())
    if tag:
        rows = [m for m in rows if tag in (m.tags or [])]
    if q:
        needle = q.strip().lower()
        rows = [
            m for m in rows
            if needle in m.name.lower() or needle in (m.description or "").lower()
        ]
    return rows


@router.post("", response_model=SettingModuleRead, status_code=status.HTTP_201_CREATED)
def create_module(payload: SettingModuleCreate, db: Session = DB_DEPENDENCY) -> SettingModule:
    module = SettingModule(
        name=payload.name,
        description=payload.description,
        module_type=payload.module_type,
        payload=payload.payload,
        tags=payload.tags,
        source_game_id=payload.source_game_id,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


@router.patch("/{module_id}", response_model=SettingModuleRead)
def patch_module(
    module_id: UUID, payload: SettingModulePatch, db: Session = DB_DEPENDENCY
) -> SettingModule:
    module = db.get(SettingModule, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="模块不存在。")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(module, key, value)
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(module_id: UUID, db: Session = DB_DEPENDENCY) -> None:
    module = db.get(SettingModule, module_id)
    if module is not None:
        db.delete(module)
        db.commit()
    return None


@router.get("/export")
def export_modules(ids: str = "", db: Session = DB_DEPENDENCY) -> Response:
    id_list = [UUID(x) for x in ids.split(",") if x.strip()]
    rows = (
        list(db.scalars(select(SettingModule).where(SettingModule.id.in_(id_list))).all())
        if id_list
        else []
    )
    body = {
        "format_version": MODULE_EXPORT_FORMAT_VERSION,
        "modules": [
            {
                "name": m.name, "description": m.description, "module_type": m.module_type,
                "payload": m.payload, "tags": m.tags,
            }
            for m in rows
        ],
    }
    content = json.dumps(body, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="rpgforge-modules.json"'},
    )


@router.post("/import", response_model=list[SettingModuleRead])
def import_modules(payload: ModuleImportFile, db: Session = DB_DEPENDENCY) -> list[SettingModule]:
    if payload.format_version != MODULE_EXPORT_FORMAT_VERSION:
        raise HTTPException(status_code=400, detail="模块文件 format_version 不受支持。")
    created: list[SettingModule] = []
    for spec in payload.modules:
        module = SettingModule(
            name=spec.name, description=spec.description, module_type=spec.module_type,
            payload=spec.payload, tags=spec.tags, source_game_id=None,
        )
        db.add(module)
        created.append(module)
    db.commit()
    for module in created:
        db.refresh(module)
    return created


@router.post("/merge-preview", response_model=MergePreviewResult)
async def merge_preview(
    payload: MergePreviewRequest, db: Session = DB_DEPENDENCY
) -> MergePreviewResult:
    rows = list(
        db.scalars(select(SettingModule).where(SettingModule.id.in_(payload.module_ids))).all()
    )
    by_id = {m.id: m for m in rows}
    modules = [
        {
            "id": str(mid), "name": by_id[mid].name,
            "module_type": by_id[mid].module_type, "payload": by_id[mid].payload,
        }
        for mid in payload.module_ids
        if mid in by_id
    ]
    try:
        result = await preview_module_merge(
            payload.target_settings, modules,
            adapt=payload.adapt, resolutions=payload.conflict_resolutions, adapter=ModuleAdapter(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MergePreviewResult(**result)
