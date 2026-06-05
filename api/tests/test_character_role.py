from typing import get_args

from app.routers.games import CHARACTER_ROLES
from app.schemas.character import CharacterRole

# 配置生成 prompt（generate_config_section.md / generate_config_outline.md）
# 允许的角色 role 枚举。schema / 兜底集合必须与之一致，否则 LLM 合法输出会被拒。
PROMPT_ROLES = {"protagonist", "antagonist", "npc", "companion", "other"}


def test_character_role_schema_covers_prompt_enum():
    assert PROMPT_ROLES <= set(get_args(CharacterRole))


def test_character_roles_set_covers_prompt_enum():
    assert PROMPT_ROLES <= CHARACTER_ROLES
