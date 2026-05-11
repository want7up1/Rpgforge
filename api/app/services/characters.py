from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.game import Game
from app.schemas.generator import GeneratedGameConfig, GeneratedLoreEntry

VISIBLE_LORE_TYPES = {"protagonist", "npc", "character", "companion"}
PLACEHOLDER_NAMES = {"", "未定", "未知", "无名", "待定"}


@dataclass
class CharacterProfile:
    name: str
    role: str = "npc"
    aliases: list[str] = field(default_factory=list)
    identity: str = ""
    description: str = ""
    appearance: str = ""
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
            portrait_prompt=profile.portrait_prompt or None,
            visibility=profile.visibility,
            is_visible=profile.visibility == "visible",
            source=profile.source,
        )
        for profile in extract_profiles_from_config(config)
    ]


def sync_characters_from_game(db: Session, game: Game) -> tuple[int, int, list[Character]]:
    profiles = extract_profiles_from_game(game)
    existing_by_name = {
        character.name: character
        for character in db.scalars(select(Character).where(Character.game_id == game.id)).all()
    }

    created = 0
    updated = 0
    for profile in profiles:
        character = existing_by_name.get(profile.name)
        if character is None:
            character = Character(game_id=game.id, name=profile.name, source=profile.source)
            db.add(character)
            existing_by_name[profile.name] = character
            created += 1
        else:
            updated += 1

        merge_profile_into_character(character, profile)

    db.commit()
    characters = list(
        db.scalars(
            select(Character).where(Character.game_id == game.id).order_by(Character.name.asc())
        ).all()
    )
    return created, updated, characters


def extract_profiles_from_config(config: GeneratedGameConfig) -> list[CharacterProfile]:
    profiles: list[CharacterProfile] = []
    state = config.initial_state if isinstance(config.initial_state, dict) else {}

    for item in config.characters:
        profiles.append(
            CharacterProfile(
                name=clean_text(item.name),
                role=normalize_role(item.role),
                aliases=clean_aliases(item.aliases),
                identity=clean_text(item.identity),
                description=clean_text(item.description),
                appearance=clean_text(item.appearance),
                portrait_prompt=clean_text(item.portrait_prompt),
                visibility=normalize_visibility(item.visibility),
                source="generated",
            )
        )

    profiles.extend(extract_profiles_from_state(state))
    profiles.extend(extract_profiles_from_lore(config.lore_entries))
    return merge_profiles(profiles)


def extract_profiles_from_game(game: Game) -> list[CharacterProfile]:
    profiles: list[CharacterProfile] = []
    if game.state and isinstance(game.state.state_json, dict):
        profiles.extend(extract_profiles_from_state(game.state.state_json))
    if game.lore_entries:
        profiles.extend(
            extract_profiles_from_lore(
                [
                    GeneratedLoreEntry.model_validate(
                        {
                            "title": entry.title,
                            "type": entry.type or "npc",
                            "keywords": entry.keywords,
                            "trigger_words": entry.trigger_words,
                            "priority": entry.priority or "medium",
                            "always_on": entry.always_on,
                            "visibility": entry.visibility or "mixed",
                            "public_info": entry.public_info or "",
                            "gm_secret": "",
                            "content": entry.public_info or entry.title,
                            "usage_note": entry.usage_note or "",
                        }
                    )
                    for entry in game.lore_entries
                ]
            )
        )
    return merge_profiles(profiles)


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
                    identity=clean_text(relation_map.get("stage")),
                    description=clean_text(
                        relation_map.get("relationship")
                        or relation_map.get("attitude")
                        or relation_map.get("recent_interaction")
                    ),
                    source="state",
                )
            )

    return profiles


def extract_profiles_from_lore(entries: list[GeneratedLoreEntry]) -> list[CharacterProfile]:
    profiles: list[CharacterProfile] = []
    for entry in entries:
        lore_type = clean_text(entry.type).lower()
        if lore_type not in VISIBLE_LORE_TYPES:
            continue
        if clean_text(entry.visibility).lower() == "hidden":
            continue

        name = clean_text(entry.title)
        if not name or name in PLACEHOLDER_NAMES:
            continue

        role = "companion" if lore_type == "companion" else "npc"
        if lore_type == "protagonist":
            role = "protagonist"
        profiles.append(
            CharacterProfile(
                name=name,
                role=role,
                aliases=clean_aliases([*entry.keywords, *entry.trigger_words]),
                description=clean_text(entry.public_info),
                portrait_prompt=build_portrait_prompt(
                    name=name,
                    identity="",
                    description=clean_text(entry.public_info),
                    appearance="",
                ),
                source="lore",
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
    portrait_prompt = clean_text(data.get("portrait_prompt") or data.get("portrait_reference"))
    if not portrait_prompt:
        portrait_prompt = build_portrait_prompt(
            name=name,
            identity=identity_value,
            description=description,
            appearance=appearance,
        )
    return CharacterProfile(
        name=name,
        role=role,
        aliases=clean_aliases(data.get("aliases") or data.get("alias") or []),
        identity=identity_value,
        description=description,
        appearance=appearance,
        portrait_prompt=portrait_prompt,
        visibility=normalize_visibility(data.get("visibility")),
        source="state",
    )


def merge_profiles(profiles: list[CharacterProfile]) -> list[CharacterProfile]:
    merged: dict[str, CharacterProfile] = {}
    for profile in profiles:
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
        current.portrait_prompt = current.portrait_prompt or profile.portrait_prompt
        if current.role == "npc" and profile.role in {"protagonist", "companion"}:
            current.role = profile.role
        if current.visibility == "hidden" and profile.visibility == "visible":
            current.visibility = "visible"
    return list(merged.values())


def merge_profile_into_character(character: Character, profile: CharacterProfile) -> None:
    character.aliases = clean_aliases([*(character.aliases or []), *profile.aliases])
    character.role = profile.role or character.role
    character.identity = character.identity or profile.identity or None
    character.description = character.description or profile.description or None
    character.appearance = character.appearance or profile.appearance or None
    character.portrait_prompt = character.portrait_prompt or profile.portrait_prompt or None
    character.visibility = profile.visibility or character.visibility
    character.is_visible = character.visibility == "visible"
    character.source = character.source or profile.source


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


def identity(data: dict[str, Any]) -> str:
    return clean_text(data.get("name") or data.get("id") or data.get("title") or data.get("npc"))


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
