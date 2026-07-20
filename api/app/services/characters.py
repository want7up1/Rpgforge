from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.game import Game
from app.schemas.generator import GeneratedGameConfig
from app.services.story_settings import story_settings_from_config

PLACEHOLDER_NAMES = {"", "未定", "未知", "无名", "待定"}
ROLE_PRIORITY = {"protagonist": 0, "companion": 1, "npc": 2, "other": 3}
SYNC_FIELDS = ("role", "identity", "description", "appearance", "portrait_prompt", "visibility")
STORY_PROFILE_KEYS = (
    "dramatic_function",
    "desire",
    "fear",
    "leverage",
    "relationship_arc",
    "public_limit",
)


@dataclass
class CharacterProfile:
    name: str
    role: str = "npc"
    aliases: list[str] = field(default_factory=list)
    identity: str = ""
    description: str = ""
    appearance: str = ""
    story_profile: dict[str, str] = field(default_factory=dict)
    portrait_prompt: str = ""
    visibility: str = "visible"
    source: str = "generated"


def build_character_records_from_config(config: GeneratedGameConfig) -> list[Character]:
    return [
        Character(
            name=profile.name,
            aliases=profile.aliases,
            role=profile.role,
            identity=profile.identity or None,
            description=profile.description or None,
            appearance=profile.appearance or None,
            story_profile=profile.story_profile,
            portrait_prompt=profile.portrait_prompt or None,
            visibility=profile.visibility,
            is_visible=profile.visibility == "visible",
            source=profile.source,
            sync_meta=build_sync_meta(profile),
            manual_fields=[],
        )
        for profile in extract_profiles_from_config(config)
    ]


def sync_characters_from_game(
    db: Session,
    game: Game,
    *,
    commit: bool = True,
) -> tuple[int, int, list[Character]]:
    profiles = extract_profiles_from_game(game)
    existing = list(db.scalars(select(Character).where(Character.game_id == game.id)).all())
    existing_by_key: dict[str, Character] = {}

    created = 0
    updated = 0
    for character in sorted(existing, key=character_merge_priority):
        key = canonical_character_name(character.name)
        current = existing_by_key.get(key)
        if current is None:
            if character.name != key:
                character.aliases = clean_aliases([*(character.aliases or []), character.name])
                character.name = key
                updated += 1
            existing_by_key[key] = character
            continue
        merge_character_into_character(current, character)
        db.delete(character)
        updated += 1

    updated += merge_existing_profile_aliases(db, existing_by_key, profiles)

    for profile in profiles:
        profile.name = canonical_character_name(profile.name)
        character = existing_by_key.get(profile.name)
        if character is None:
            character = Character(
                game_id=game.id,
                name=profile.name,
                aliases=profile.aliases,
                role=profile.role,
                identity=profile.identity or None,
                description=profile.description or None,
                appearance=profile.appearance or None,
                story_profile=profile.story_profile,
                portrait_prompt=profile.portrait_prompt or None,
                visibility=profile.visibility,
                is_visible=profile.visibility == "visible",
                source=profile.source,
                sync_meta=build_sync_meta(profile),
                manual_fields=[],
            )
            db.add(character)
            existing_by_key[profile.name] = character
            created += 1
            continue
        else:
            updated += 1

        merge_profile_into_character(character, profile)

    if commit:
        db.commit()
    else:
        db.flush()
    characters = list(
        db.scalars(
            select(Character).where(Character.game_id == game.id).order_by(Character.name.asc())
        ).all()
    )
    return created, updated, characters


def merge_existing_profile_aliases(
    db: Session,
    existing_by_key: dict[str, Character],
    profiles: list[CharacterProfile],
) -> int:
    updated = 0
    for profile in profiles:
        target_key = canonical_character_name(profile.name)
        if not target_key or target_key in PLACEHOLDER_NAMES:
            continue
        for alias in profile.aliases:
            alias_key = canonical_character_name(alias)
            if not alias_key or alias_key == target_key or alias_key in PLACEHOLDER_NAMES:
                continue
            duplicate = existing_by_key.get(alias_key)
            if duplicate is None:
                continue
            target = existing_by_key.get(target_key)
            if target is None:
                duplicate.aliases = clean_aliases(
                    [*(duplicate.aliases or []), duplicate.name, *profile.aliases]
                )
                duplicate.name = target_key
                existing_by_key.pop(alias_key, None)
                existing_by_key[target_key] = duplicate
                updated += 1
                continue
            if duplicate is target:
                continue
            merge_character_into_character(target, duplicate)
            db.delete(duplicate)
            existing_by_key.pop(alias_key, None)
            updated += 1
    return updated


def extract_profiles_from_config(config: GeneratedGameConfig) -> list[CharacterProfile]:
    profiles: list[CharacterProfile] = []
    state = config.initial_state if isinstance(config.initial_state, dict) else {}

    settings = config.story_settings if isinstance(config.story_settings, dict) else {}
    for item in settings.get("core_characters") or []:
        data = as_mapping(item)
        if data:
            profiles.append(profile_from_story_settings_character(data))

    profiles.extend(extract_profiles_from_state(state))
    return merge_profiles(profiles)


def extract_profiles_from_game(game: Game) -> list[CharacterProfile]:
    profiles: list[CharacterProfile] = []
    settings = story_settings_from_config(game.config)
    for item in settings.get("core_characters") or []:
        data = as_mapping(item)
        if data:
            profiles.append(profile_from_story_settings_character(data))
    if game.state and isinstance(game.state.state_json, dict):
        profiles.extend(extract_profiles_from_state(game.state.state_json))
    return merge_profiles(profiles)


def profile_from_story_settings_character(item: dict[str, Any]) -> CharacterProfile:
    return CharacterProfile(
        name=clean_text(item.get("name")) or "未命名角色",
        aliases=clean_aliases(as_list(item.get("aliases"))),
        role=normalize_role(clean_text(item.get("role"))),
        identity=clean_text(item.get("identity")),
        description=clean_text(item.get("description")),
        appearance=clean_text(item.get("appearance")),
        portrait_prompt=clean_text(item.get("portrait_prompt")),
        visibility=normalize_visibility(clean_text(item.get("visibility"))),
        story_profile={
            key: clean_text(item.get(key))
            for key in STORY_PROFILE_KEYS
        },
        source="story_settings",
    )


def extract_profiles_from_state(state: dict[str, Any]) -> list[CharacterProfile]:
    profiles: list[CharacterProfile] = []
    protagonist = as_mapping(
        first_present(state.get("protagonist"), nested(state, "v2", "protagonist_sheet"))
    )
    protagonist_name = identity(protagonist)
    if protagonist_name:
        profiles.append(profile_from_mapping(protagonist, protagonist_name, role="protagonist"))

    for item in as_list(first_present(state.get("npcs"), nested(state, "v2", "npc_registry"))):
        npc = as_mapping(item)
        name = identity(npc)
        if name:
            profiles.append(profile_from_mapping(npc, name, role=normalize_role(npc.get("role"))))

    for relation in as_list(
        first_present(state.get("relationships"), nested(state, "v2", "relationship_tracks"))
    ):
        relation_map = as_mapping(relation)
        name = clean_text(relation_map.get("npc") or relation_map.get("name"))
        if name:
            profiles.append(
                CharacterProfile(
                    name=name,
                    role="npc",
                    identity=clean_text(relation_map.get("status") or relation_map.get("stage")),
                    description=clean_text(
                        relation_map.get("note")
                        or relation_map.get("status")
                        or relation_map.get("relationship")
                        or relation_map.get("attitude")
                        or relation_map.get("recent_interaction")
                    ),
                    source="state",
                )
            )

    return profiles


def profile_from_mapping(data: dict[str, Any], name: str, role: str) -> CharacterProfile:
    identity_value = clean_text(data.get("identity") or data.get("title") or data.get("type"))
    description = clean_text(
        data.get("description")
        or data.get("public_info")
        or data.get("status")
        or data.get("relationship")
        or data.get("attitude")
    )
    appearance = clean_text(
        data.get("appearance")
        or data.get("look")
        or data.get("visual")
        or data.get("visual_description")
    )
    return CharacterProfile(
        name=name,
        role=role,
        aliases=profile_aliases_from_mapping(data, name),
        identity=identity_value,
        description=description,
        appearance=appearance,
        story_profile=story_profile_from_mapping(data),
        portrait_prompt="",
        visibility=normalize_visibility(data.get("visibility")),
        source="state",
    )


def profile_aliases_from_mapping(data: dict[str, Any], name: str) -> list[str]:
    aliases = list(as_list(data.get("aliases")))
    for key in ("id", "key", "title", "npc"):
        value = clean_text(data.get(key))
        if value and value != name:
            aliases.append(value)
    return clean_aliases(aliases)


def merge_profiles(profiles: list[CharacterProfile]) -> list[CharacterProfile]:
    merged: dict[str, CharacterProfile] = {}
    for profile in profiles:
        profile.name = canonical_character_name(profile.name)
        if not profile.name or profile.name in PLACEHOLDER_NAMES:
            continue
        current = merged.get(profile.name)
        if current is None:
            merged[profile.name] = profile
            continue
        current.aliases = clean_aliases([*current.aliases, *profile.aliases])
        current.identity = current.identity or profile.identity
        current.description = current.description or profile.description
        current.appearance = current.appearance or profile.appearance
        current.story_profile = merge_story_profiles(current.story_profile, profile.story_profile)
        current.portrait_prompt = current.portrait_prompt or profile.portrait_prompt
        if current.role == "npc" and profile.role in {"protagonist", "companion"}:
            current.role = profile.role
        if current.visibility == "hidden" and profile.visibility == "visible":
            current.visibility = "visible"
    return list(merged.values())


def character_merge_priority(character: Character) -> tuple[int, int, int, int, str]:
    exact_name_priority = 0 if character.name == canonical_character_name(character.name) else 1
    source_priority = 1 if character.source == "lore" else 0
    return (
        exact_name_priority,
        source_priority,
        ROLE_PRIORITY.get(character.role, 9),
        len(character.name),
        character.name,
    )


def merge_character_into_character(target: Character, duplicate: Character) -> None:
    target.aliases = clean_aliases(
        [*(target.aliases or []), duplicate.name, *(duplicate.aliases or [])]
    )
    if not target.identity and duplicate.identity:
        target.identity = duplicate.identity
    if not target.description and duplicate.description:
        target.description = duplicate.description
    if not target.appearance and duplicate.appearance:
        target.appearance = duplicate.appearance
    target.story_profile = merge_story_profiles(
        as_mapping(target.story_profile),
        as_mapping(duplicate.story_profile),
    )
    if not target.portrait_prompt and duplicate.portrait_prompt:
        target.portrait_prompt = duplicate.portrait_prompt
    if not target.portrait_path and duplicate.portrait_path:
        target.portrait_path = duplicate.portrait_path
        target.portrait_mime_type = duplicate.portrait_mime_type
        target.portrait_original_filename = duplicate.portrait_original_filename
        target.portrait_uploaded_at = duplicate.portrait_uploaded_at
    if ROLE_PRIORITY.get(duplicate.role, 9) < ROLE_PRIORITY.get(target.role, 9):
        target.role = duplicate.role
    if target.source == "lore" and duplicate.source != "lore":
        target.source = duplicate.source
    if target.visibility == "hidden" and duplicate.visibility == "visible":
        target.visibility = "visible"
        target.is_visible = True
    target.sync_meta = merge_sync_meta(
        as_mapping(target.sync_meta),
        as_mapping(duplicate.sync_meta),
    )
    target.manual_fields = clean_manual_fields(
        [*(target.manual_fields or []), *(duplicate.manual_fields or [])]
    )


def merge_profile_into_character(character: Character, profile: CharacterProfile) -> None:
    character.aliases = clean_aliases([*(character.aliases or []), *profile.aliases])
    manual_fields = set(clean_manual_fields(character.manual_fields or []))
    sync_meta = as_mapping(character.sync_meta)
    for field_name in SYNC_FIELDS:
        incoming = getattr(profile, field_name)
        if field_name == "role":
            incoming = normalize_role(incoming)
        if field_name == "visibility":
            incoming = normalize_visibility(incoming)
        apply_synced_field(character, field_name, incoming, manual_fields, sync_meta)
    apply_synced_story_profile(character, profile.story_profile, manual_fields, sync_meta)
    character.is_visible = character.visibility == "visible"
    character.source = character.source or profile.source
    character.sync_meta = sync_meta
    character.manual_fields = clean_manual_fields(manual_fields)


def build_portrait_prompt(
    *,
    name: str,
    identity: str,
    description: str,
    appearance: str,
) -> str:
    parts = [name, identity, appearance, description]
    visible_parts = [part for part in parts if part]
    if not visible_parts:
        return ""
    return "，".join(visible_parts)


def build_sync_meta(profile: CharacterProfile) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for field_name in SYNC_FIELDS:
        value = getattr(profile, field_name)
        if isinstance(value, str) and value:
            meta[field_name] = value
    story_profile = normalize_story_profile(profile.story_profile)
    if any(story_profile.values()):
        meta["story_profile"] = story_profile
    return meta


def merge_sync_meta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = value
        elif key == "story_profile":
            merged[key] = merge_story_profiles(as_mapping(merged[key]), as_mapping(value))
    return merged


def apply_synced_field(
    character: Character,
    field_name: str,
    incoming: Any,
    manual_fields: set[str],
    sync_meta: dict[str, Any],
) -> None:
    if field_name in manual_fields:
        return
    current = getattr(character, field_name, None)
    value = clean_text(incoming)
    if not value:
        return

    should_apply = value_is_empty(current)
    previous = sync_meta.get(field_name)
    if previous is not None and (
        normalized_compare_value(current) == normalized_compare_value(previous)
    ):
        should_apply = True
    if field_name == "role" and not should_apply:
        should_apply = role_should_upgrade(clean_text(current), value)

    if should_apply:
        setattr(character, field_name, value)
        sync_meta[field_name] = value
    elif normalized_compare_value(current) == normalized_compare_value(value):
        sync_meta[field_name] = value


def apply_synced_story_profile(
    character: Character,
    incoming_profile: dict[str, Any],
    manual_fields: set[str],
    sync_meta: dict[str, Any],
) -> None:
    incoming = normalize_story_profile(incoming_profile)
    if not any(incoming.values()):
        return

    current = normalize_story_profile(character.story_profile)
    previous = normalize_story_profile(as_mapping(sync_meta.get("story_profile")))
    changed = False
    meta_changed = False
    for key, value in incoming.items():
        if not value or f"story_profile.{key}" in manual_fields or "story_profile" in manual_fields:
            continue
        current_value = current.get(key, "")
        previous_value = previous.get(key, "")
        if not current_value or (previous_value and current_value == previous_value):
            current[key] = value
            previous[key] = value
            changed = True
            meta_changed = True
        elif current_value == value:
            previous[key] = value
            meta_changed = True

    if changed:
        character.story_profile = current
    if meta_changed:
        sync_meta["story_profile"] = previous


def role_should_upgrade(current: str, incoming: str) -> bool:
    if current == incoming:
        return True
    if current == "npc" and incoming in {"protagonist", "companion"}:
        return True
    if not current:
        return True
    return False


def value_is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def normalized_compare_value(value: Any) -> str:
    return clean_text(value)


def story_profile_from_mapping(data: dict[str, Any]) -> dict[str, str]:
    profile = normalize_story_profile(as_mapping(data.get("story_profile")))
    for key in STORY_PROFILE_KEYS:
        if not profile.get(key):
            profile[key] = clean_text(data.get(key))
    return profile


def normalize_story_profile(value: Any) -> dict[str, str]:
    record = as_mapping(value)
    return {key: clean_text(record.get(key)) for key in STORY_PROFILE_KEYS}


def merge_story_profiles(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, str]:
    current_profile = normalize_story_profile(current)
    incoming_profile = normalize_story_profile(incoming)
    return {
        key: current_profile.get(key) or incoming_profile.get(key) or ""
        for key in STORY_PROFILE_KEYS
    }


def identity(data: dict[str, Any]) -> str:
    return clean_text(data.get("name") or data.get("id") or data.get("title") or data.get("npc"))


def canonical_character_name(value: Any) -> str:
    text = clean_text(value)
    for separator in ("——", "--", "：", ":"):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
            break
    return text


def normalize_role(value: Any) -> str:
    role = clean_text(value).lower()
    if role in {"protagonist", "主角", "pc", "player"}:
        return "protagonist"
    if role in {"companion", "party", "ally", "同伴", "队友"}:
        return "companion"
    if role in {"npc", "character", "角色"}:
        return "npc"
    if role in {"other", "其他"}:
        return "other"
    return "npc"


def normalize_visibility(value: Any) -> str:
    visibility = clean_text(value).lower()
    return "hidden" if visibility in {"hidden", "secret", "gm", "隐藏"} else "visible"


def clean_aliases(value: Any) -> list[str]:
    aliases: list[str] = []
    for item in as_list(value):
        text = clean_text(item)
        if text and text not in PLACEHOLDER_NAMES and text not in aliases:
            aliases.append(text)
    return aliases[:12]


def clean_manual_fields(value: Any) -> list[str]:
    fields: list[str] = []
    source = value if isinstance(value, (list, set, tuple)) else as_list(value)
    for item in source:
        text = clean_text(item)
        if text and text not in fields:
            fields.append(text)
    return fields


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def character_portrait_url(game_id: UUID, character: Character) -> str | None:
    if not character.portrait_path:
        return None
    return f"/api/games/{game_id}/characters/{character.id}/portrait"


def character_portrait_thumb_url(game_id: UUID, character: Character) -> str | None:
    if not character.portrait_thumb_path:
        return None
    return f"/api/games/{game_id}/characters/{character.id}/portrait/thumb"
