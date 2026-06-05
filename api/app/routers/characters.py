from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.character import Character
from app.models.game import Game
from app.schemas.character import CharacterRead, CharacterSyncResponse, CharacterUpdate
from app.services.characters import (
    STORY_PROFILE_KEYS,
    character_portrait_thumb_url,
    character_portrait_url,
    clean_aliases,
    clean_manual_fields,
    sync_characters_from_game,
)
from app.services.game_activity import touch_game

router = APIRouter(prefix="/api/games/{game_id}/characters", tags=["characters"])
DB_DEPENDENCY = Depends(get_db)

MAX_PORTRAIT_BYTES = 8 * 1024 * 1024
MAX_PORTRAIT_PIXELS = 24_000_000
PORTRAIT_THUMB_SIZE = (480, 640)
PORTRAIT_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}


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


def character_payload(
    game_id: UUID,
    character: Character,
    *,
    scope: str = "director",
) -> CharacterRead:
    is_public_scope = scope == "public"
    is_visible = character.visibility == "visible"
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
            "story_profile": {} if is_public_scope else character.story_profile,
            "portrait_prompt": None if is_public_scope else character.portrait_prompt,
            "portrait_url": character_portrait_url(game_id, character),
            "portrait_thumb_url": character_portrait_thumb_url(game_id, character),
            "portrait_mime_type": character.portrait_mime_type,
            "portrait_thumb_mime_type": character.portrait_thumb_mime_type,
            "portrait_original_filename": character.portrait_original_filename,
            "portrait_uploaded_at": character.portrait_uploaded_at,
            "visibility": character.visibility,
            "is_visible": is_visible,
            "source": character.source,
            "created_at": character.created_at,
            "updated_at": character.updated_at,
        }
    )


def sorted_characters(characters: list[Character]) -> list[Character]:
    role_order = {"protagonist": 0, "antagonist": 1, "companion": 2, "npc": 3, "other": 4}
    return sorted(characters, key=lambda item: (role_order.get(item.role, 9), item.name))


@router.get("", response_model=list[CharacterRead])
def list_characters(
    game_id: UUID,
    scope: str = "director",
    db: Session = DB_DEPENDENCY,
) -> list[CharacterRead]:
    get_game_or_404(db, game_id)
    characters = list(
        db.scalars(select(Character).where(Character.game_id == game_id)).all()
    )
    if scope == "public":
        characters = [character for character in characters if character.visibility == "visible"]
    return [
        character_payload(game_id, character, scope=scope)
        for character in sorted_characters(characters)
    ]


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
    validate_visibility_update(updates)
    if "is_visible" in updates and "visibility" not in updates:
        updates["visibility"] = "visible" if updates["is_visible"] else "hidden"
    updates.pop("is_visible", None)

    manual_fields = set(clean_manual_fields(character.manual_fields or []))
    renamed_aliases: list[str] = []
    for key, value in updates.items():
        if key == "name":
            value = str(value).strip()
            if not value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="角色名称不能为空。",
            )
            if value != character.name:
                renamed_aliases = [character.name]
                character.aliases = clean_aliases([*(character.aliases or []), *renamed_aliases])
            setattr(character, key, value)
            manual_fields.add("name")
            continue
        if key == "aliases":
            character.aliases = clean_aliases([*renamed_aliases, *list(value or [])])
            manual_fields.add("aliases")
            continue
        if key == "story_profile":
            update_story_profile(character, value, manual_fields)
            continue
        if isinstance(value, str):
            value = value.strip()
            value = value or None
        setattr(character, key, value)
        manual_fields.add(key)
    character.is_visible = character.visibility == "visible"
    character.manual_fields = clean_manual_fields(manual_fields)

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

    content = await file.read(MAX_PORTRAIT_BYTES + 1)
    if len(content) > MAX_PORTRAIT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="立绘图片不能超过 8MB。",
        )
    image, extension, actual_mime_type = load_portrait_image(content)

    game_dir = portrait_root() / str(game_id)
    game_dir.mkdir(parents=True, exist_ok=True)
    portrait_path = game_dir / f"{character_id}{extension}"
    thumb_path = game_dir / f"{character_id}.thumb.webp"
    portrait_path.write_bytes(content)
    write_portrait_thumbnail(image, thumb_path)
    remove_old_portrait(character, keep=portrait_path)

    character.portrait_path = str(portrait_path)
    character.portrait_mime_type = actual_mime_type
    character.portrait_original_filename = file.filename
    character.portrait_uploaded_at = datetime.now(UTC)
    character.portrait_thumb_path = str(thumb_path)
    character.portrait_thumb_mime_type = "image/webp"
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
    character.portrait_thumb_path = None
    character.portrait_thumb_mime_type = None
    db.add(character)
    touch_game(db, game_id)
    db.commit()
    db.refresh(character)
    return character_payload(game_id, character)


@router.get("/{character_id}/portrait/thumb")
def get_portrait_thumb(
    game_id: UUID,
    character_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> FileResponse:
    get_game_or_404(db, game_id)
    character = get_character_or_404(db, game_id, character_id)
    if not character.portrait_thumb_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portrait thumb not found.",
        )
    path = Path(character.portrait_thumb_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portrait thumb file missing.",
        )
    return FileResponse(path, media_type=character.portrait_thumb_mime_type)


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
    for raw_path in (character.portrait_path, character.portrait_thumb_path):
        if not raw_path:
            continue
        old_path = Path(raw_path)
        if keep is not None and old_path == keep:
            continue
        if old_path.exists() and old_path.is_file():
            old_path.unlink()


def validate_visibility_update(updates: dict[str, object]) -> None:
    if "visibility" not in updates or "is_visible" not in updates:
        return
    visibility = updates["visibility"]
    is_visible = updates["is_visible"]
    if (visibility == "visible") != bool(is_visible):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="visibility 与 is_visible 不一致。",
        )


def update_story_profile(
    character: Character,
    value: object,
    manual_fields: set[str],
) -> None:
    incoming = value if isinstance(value, dict) else {}
    current = normalize_story_profile(character.story_profile)
    updated = {
        key: str(incoming.get(key) or "").strip()
        for key in STORY_PROFILE_KEYS
    }
    for key in STORY_PROFILE_KEYS:
        if current.get(key, "") != updated.get(key, ""):
            manual_fields.add(f"story_profile.{key}")
    character.story_profile = updated


def normalize_story_profile(value: object) -> dict[str, str]:
    record = value if isinstance(value, dict) else {}
    return {key: str(record.get(key) or "").strip() for key in STORY_PROFILE_KEYS}


def load_portrait_image(content: bytes) -> tuple[Image.Image, str, str]:
    try:
        with Image.open(BytesIO(content)) as raw_image:
            image_format = raw_image.format or ""
            if image_format not in PORTRAIT_FORMATS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="只支持 PNG、JPG、WEBP 立绘图片。",
                )
            raw_image.load()
            width, height = raw_image.size
            if width <= 0 or height <= 0 or width * height > MAX_PORTRAIT_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="立绘图片尺寸无效或过大。",
                )
            image = ImageOps.exif_transpose(raw_image).copy()
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法识别立绘图片内容。",
        ) from exc

    extension, mime_type = PORTRAIT_FORMATS[image_format]
    return image, extension, mime_type


def write_portrait_thumbnail(image: Image.Image, path: Path) -> None:
    thumb = ImageOps.fit(
        image.convert("RGB"),
        PORTRAIT_THUMB_SIZE,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    thumb.save(path, format="WEBP", quality=86, method=6)
