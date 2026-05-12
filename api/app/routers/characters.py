from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.character import Character
from app.models.game import Game
from app.schemas.character import CharacterRead, CharacterSyncResponse, CharacterUpdate
from app.services.characters import character_portrait_url, sync_characters_from_game
from app.services.game_activity import touch_game

router = APIRouter(prefix="/api/games/{game_id}/characters", tags=["characters"])
DB_DEPENDENCY = Depends(get_db)

ALLOWED_PORTRAIT_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
MAX_PORTRAIT_BYTES = 8 * 1024 * 1024


def get_game_or_404(db: Session, game_id: UUID) -> Game:
    game = db.scalars(select(Game).where(Game.id == game_id)).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


def get_character_or_404(db: Session, game_id: UUID, character_id: UUID) -> Character:
    character = db.scalars(
        select(Character).where(Character.id == character_id, Character.game_id == game_id)
    ).first()
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found.")
    return character


def character_payload(game_id: UUID, character: Character) -> CharacterRead:
    return CharacterRead.model_validate(
        {
            "id": character.id,
            "game_id": character.game_id,
            "name": character.name,
            "aliases": character.aliases,
            "role": character.role,
            "identity": character.identity,
            "description": character.description,
            "appearance": character.appearance,
            "portrait_prompt": character.portrait_prompt,
            "portrait_url": character_portrait_url(game_id, character),
            "portrait_mime_type": character.portrait_mime_type,
            "portrait_original_filename": character.portrait_original_filename,
            "portrait_uploaded_at": character.portrait_uploaded_at,
            "visibility": character.visibility,
            "is_visible": character.is_visible,
            "source": character.source,
            "created_at": character.created_at,
            "updated_at": character.updated_at,
        }
    )


def sorted_characters(characters: list[Character]) -> list[Character]:
    role_order = {"protagonist": 0, "companion": 1, "npc": 2, "other": 3}
    return sorted(characters, key=lambda item: (role_order.get(item.role, 9), item.name))


@router.get("", response_model=list[CharacterRead])
def list_characters(game_id: UUID, db: Session = DB_DEPENDENCY) -> list[CharacterRead]:
    get_game_or_404(db, game_id)
    characters = list(
        db.scalars(select(Character).where(Character.game_id == game_id)).all()
    )
    return [character_payload(game_id, character) for character in sorted_characters(characters)]


@router.post("/sync", response_model=CharacterSyncResponse)
def sync_characters(game_id: UUID, db: Session = DB_DEPENDENCY) -> CharacterSyncResponse:
    game = get_game_or_404(db, game_id)
    created, updated, characters = sync_characters_from_game(db, game)
    if created or updated:
        touch_game(db, game_id)
        db.commit()
    ordered = sorted_characters(characters)
    return CharacterSyncResponse(
        total=len(ordered),
        created=created,
        updated=updated,
        characters=[character_payload(game_id, character) for character in ordered],
    )


@router.get("/{character_id}", response_model=CharacterRead)
def get_character(
    game_id: UUID,
    character_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> CharacterRead:
    get_game_or_404(db, game_id)
    character = get_character_or_404(db, game_id, character_id)
    return character_payload(game_id, character)


@router.patch("/{character_id}", response_model=CharacterRead)
def update_character(
    game_id: UUID,
    character_id: UUID,
    payload: CharacterUpdate,
    db: Session = DB_DEPENDENCY,
) -> CharacterRead:
    get_game_or_404(db, game_id)
    character = get_character_or_404(db, game_id, character_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
            if key == "name" and not value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="角色名称不能为空。",
                )
            value = value or None
        setattr(character, key, value)
    if character.visibility == "hidden":
        character.is_visible = False

    db.add(character)
    touch_game(db, game_id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="角色名称已存在。",
        ) from exc
    db.refresh(character)
    return character_payload(game_id, character)


@router.post("/{character_id}/portrait", response_model=CharacterRead)
async def upload_portrait(
    game_id: UUID,
    character_id: UUID,
    file: Annotated[UploadFile, File()],
    db: Session = DB_DEPENDENCY,
) -> CharacterRead:
    get_game_or_404(db, game_id)
    character = get_character_or_404(db, game_id, character_id)
    mime_type = file.content_type or ""
    extension = ALLOWED_PORTRAIT_MIME_TYPES.get(mime_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持 PNG、JPG、WEBP 立绘图片。",
        )

    content = await file.read(MAX_PORTRAIT_BYTES + 1)
    if len(content) > MAX_PORTRAIT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="立绘图片不能超过 8MB。",
        )

    game_dir = portrait_root() / str(game_id)
    game_dir.mkdir(parents=True, exist_ok=True)
    portrait_path = game_dir / f"{character_id}{extension}"
    portrait_path.write_bytes(content)
    remove_old_portrait(character, keep=portrait_path)

    character.portrait_path = str(portrait_path)
    character.portrait_mime_type = mime_type
    character.portrait_original_filename = file.filename
    character.portrait_uploaded_at = datetime.now(UTC)
    db.add(character)
    touch_game(db, game_id)
    db.commit()
    db.refresh(character)
    return character_payload(game_id, character)


@router.delete("/{character_id}/portrait", response_model=CharacterRead)
def delete_portrait(
    game_id: UUID,
    character_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> CharacterRead:
    get_game_or_404(db, game_id)
    character = get_character_or_404(db, game_id, character_id)
    remove_old_portrait(character)
    character.portrait_path = None
    character.portrait_mime_type = None
    character.portrait_original_filename = None
    character.portrait_uploaded_at = None
    db.add(character)
    touch_game(db, game_id)
    db.commit()
    db.refresh(character)
    return character_payload(game_id, character)


@router.get("/{character_id}/portrait")
def get_portrait(game_id: UUID, character_id: UUID, db: Session = DB_DEPENDENCY) -> FileResponse:
    get_game_or_404(db, game_id)
    character = get_character_or_404(db, game_id, character_id)
    if not character.portrait_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portrait not found.")
    path = Path(character.portrait_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portrait file missing.")
    return FileResponse(path, media_type=character.portrait_mime_type)


def portrait_root() -> Path:
    return Path(settings.portrait_storage_path)


def remove_old_portrait(character: Character, keep: Path | None = None) -> None:
    if not character.portrait_path:
        return
    old_path = Path(character.portrait_path)
    if keep is not None and old_path == keep:
        return
    if old_path.exists() and old_path.is_file():
        old_path.unlink()
