# 剧本炼金工坊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把优秀剧本的单个看板 block 提炼成可复用「模块」存进个人工坊（Postgres），再并入新剧本生成草稿或已有剧本设定页——并入时可选 AI「本地优化」把模块改写得贴合目标剧本，全程预览+冲突可控+可回滚。

**Architecture:** 后端新表 `setting_modules` + 纯函数合并引擎（字符串桶去重 + 身份冲突 rename/overwrite/skip + validate）+ AI 适配器（独立 timeout + 失败回退）+ `/api/modules` 路由（CRUD/导入导出/merge-preview）。前端 `/workshop` 管理页 + 看板「存为模块」+ 共享并入面板（设定页 & 生成页）。复用特性1 的看板与 story_settings 归一/校验。

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Postgres + pytest（容器内）；Next.js + React + TS + vitest（纯函数）。

**设计依据：** `docs/superpowers/specs/2026-06-04-script-alchemy-workshop-design.md`

> 依赖特性1（已 merge 进 main）：`web/lib/generatorBoard.ts`（`BoardBlock.address`/`buildBoardModel`）、`components/board/`、`updateGameConfig`、设定页/生成页看板。本计划从当前 `main` 切新分支执行（如 `feat/script-alchemy-workshop`）。

---

## 文件结构

**后端新增**
- `api/app/models/setting_module.py` — `SettingModule` 模型
- `api/migrations/versions/20260604_0029_setting_modules.py` — 建表迁移
- `api/app/services/module_library.py` — 合并引擎（纯函数，可单测）
- `api/app/services/module_adapter.py` — AI 本地优化（LLM + timeout + fallback）
- `api/app/prompts/adapt_module.md` — 适配 prompt
- `api/app/schemas/module.py` — Pydantic schema
- `api/app/routers/modules.py` — `/api/modules` 路由
- `api/tests/test_module_library.py` / `test_module_adapter.py` / `test_modules_api.py`

**后端修改**
- `api/app/models/__init__.py`（注册 `SettingModule`）、`api/app/main.py`（挂路由）

**前端新增**
- `web/app/workshop/page.tsx` — 工坊管理页
- `web/components/workshop/ModuleMergePanel.tsx` — 共享并入面板
- `web/lib/moduleFragment.ts` — 由 `BoardBlock` 还原模块 payload（纯函数 + vitest）

**前端修改**
- `web/lib/types.ts`（模块类型）、`web/lib/api.ts`（模块 API）
- `web/components/board/BlockDetailModal.tsx`（加「存为模块」）+ `SettingsBoard.tsx`/`BoardBlockGrid.tsx`（透传 onSaveAsModule + gameId）
- `web/app/games/[id]/settings/page.tsx`（挂并入面板）、`web/app/games/new/page.tsx`（挂并入面板）
- `docs/OPTIMIZATION_PLAN.md`（追加 Round）

---

## Phase A — 后端

### Task 1: setting_modules 表 + 模型 + 迁移

**Files:**
- Create: `api/app/models/setting_module.py`、`api/migrations/versions/20260604_0029_setting_modules.py`
- Modify: `api/app/models/__init__.py`

- [ ] **Step 1: 写模型**

Create `api/app/models/setting_module.py`：

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SettingModule(Base):
    """可复用「设定模块」。payload 是最小 story_settings 片段，并入逻辑只认这个结构。

    隐私：payload 多来自精修剧本，仅存 Postgres，严禁进仓库/测试/文档（占位符）。
    """

    __tablename__ = "setting_modules"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_game_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: 注册模型**

`api/app/models/__init__.py`：加 `from app.models.setting_module import SettingModule`（放在 setting_version 之后），并在 `__all__` 加 `"SettingModule",`。

- [ ] **Step 3: 写迁移**

Create `api/migrations/versions/20260604_0029_setting_modules.py`：

```python
"""Add setting_modules table for the script alchemy workshop.

Revision ID: 20260604_0029
Revises: 20260601_0028
Create Date: 2026-06-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260604_0029"
down_revision: str | None = "20260601_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "setting_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("module_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_game_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_game_id"], ["games.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_setting_modules_module_type", "setting_modules", ["module_type"])


def downgrade() -> None:
    op.drop_index("ix_setting_modules_module_type", table_name="setting_modules")
    op.drop_table("setting_modules")
```

- [ ] **Step 4: 应用迁移并验证导入**

Run: `docker compose exec api alembic upgrade head`
Expected: 迁移到 20260604_0029 无错。
Run: `docker compose exec api python -c "from app.models import SettingModule; print(SettingModule.__tablename__)"`
Expected: 打印 `setting_modules`。

- [ ] **Step 5: Commit**

```bash
git add api/app/models/setting_module.py api/app/models/__init__.py api/migrations/versions/20260604_0029_setting_modules.py
git commit -m "feat(api): setting_modules 表+模型+迁移（炼金工坊）"
```

---

### Task 2: 合并引擎 module_library（核心，TDD）

**Files:**
- Create: `api/app/services/module_library.py`、`api/tests/test_module_library.py`

- [ ] **Step 1: 写失败测试**

Create `api/tests/test_module_library.py`（占位符数据，遵剧本隐私）：

```python
from app.services.module_library import merge_modules_into_settings


def _base():
    return {
        "format_version": "rpgforge.story.v2",
        "core_characters": [{"name": "主角", "role": "protagonist"}],
        "story_core": {"canon_terms": ["旧城"]},
        "hard_rules": {"must_follow": ["细致描写"]},
    }


def test_string_bucket_dedup_and_append():
    items = [{"id": "m1", "payload": {"story_core": {"canon_terms": ["旧城", "新塔"]}}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    assert settings["story_core"]["canon_terms"] == ["旧城", "新塔"]  # 旧城去重
    assert report.deduped == 1
    assert report.entries[0]["action"] == "added"


def test_list_item_added_when_no_conflict():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "红伞客", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    names = [c["name"] for c in settings["core_characters"]]
    assert names == ["主角", "红伞客"]
    assert report.entries[0]["action"] == "added"


def test_identity_conflict_default_rename():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {})
    names = [c["name"] for c in settings["core_characters"]]
    assert names == ["主角", "主角 (2)"]
    e = report.entries[0]
    assert e["action"] == "renamed" and e["conflict"] is True and e["renamed_to"] == "主角 (2)"


def test_identity_conflict_overwrite():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc", "desire": "x"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {"m1": "overwrite"})
    chars = settings["core_characters"]
    assert len(chars) == 1 and chars[0]["role"] == "npc" and chars[0]["desire"] == "x"
    assert report.entries[0]["action"] == "overwritten"


def test_identity_conflict_skip():
    items = [{"id": "m1", "payload": {"core_characters": [{"name": "主角", "role": "npc"}]}}]
    settings, report = merge_modules_into_settings(_base(), items, {"m1": "skip"})
    assert [c["name"] for c in settings["core_characters"]] == ["主角"]
    assert report.entries[0]["action"] == "skipped"


def test_act_rename_reids_anchors_and_passes_validate():
    base = _base()
    base["act_plan"] = [{
        "id": "act_1", "title": "序",
        "completion_anchors": [{"id": "act_1_a1", "title": "锚", "required": True}],
    }]
    items = [{"id": "m1", "payload": {"act_plan": [{
        "id": "act_1", "title": "另一序",
        "completion_anchors": [{"id": "act_1_a1", "title": "锚2", "required": True}],
    }]}}]
    settings, report = merge_modules_into_settings(base, items, {})
    acts = settings["act_plan"]
    assert len(acts) == 2
    anchor_ids = [a["id"] for act in acts for a in act["completion_anchors"]]
    assert len(anchor_ids) == len(set(anchor_ids))  # 全局唯一，validate 不报错
```

- [ ] **Step 2: 运行验证失败**

Run: `docker compose exec api pytest tests/test_module_library.py -v`
Expected: FAIL（`merge_modules_into_settings` 未定义）。

- [ ] **Step 3: 实现 module_library.py**

Create `api/app/services/module_library.py`：

```python
"""炼金工坊并入引擎：把模块 payload（最小 story_settings 片段）深合并进目标 settings。

字符串桶静默去重；列表条目身份冲突按 resolution（rename 默认 / overwrite / skip）处理；
合并后过 validate_story_settings 保证 schema 合法（同名/同 id/同 anchor 唯一）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from app.services.story_settings import normalize_story_settings, validate_story_settings

# 列表字段 → 身份键（按顺序取首个非空）
_LIST_IDENTITY: dict[str, tuple[str, ...]] = {
    "core_characters": ("name",),
    "core_mechanics": ("id", "name"),
    "action_style_rules": ("id", "name"),
    "story_material_library": ("id", "title"),
    "main_quest_path": ("id",),
    "act_plan": ("id",),
}
_STRING_BUCKETS: dict[str, tuple[str, ...]] = {
    "hard_rules": ("must_follow", "must_not", "reveal_rules", "continuity_rules"),
    "story_core": ("canon_terms", "forbidden_drift", "must_not_become", "must_preserve"),
    "worldview": ("public_facts", "hidden_facts"),
}


@dataclass
class MergeReport:
    entries: list[dict[str, Any]] = field(default_factory=list)  # 每模块一条
    deduped: int = 0


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _identity(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        t = _text(item.get(key))
        if t:
            return t
    return None


def _collect_anchor_ids(act_plan: list[Any]) -> set[str]:
    ids: set[str] = set()
    for act in act_plan:
        if isinstance(act, dict):
            for anchor in act.get("completion_anchors") or []:
                if isinstance(anchor, dict) and _text(anchor.get("id")):
                    ids.add(_text(anchor["id"]))
    return ids


def _unique_name(existing: set[str], base: str) -> str:
    if base not in existing:
        return base
    i = 2
    while f"{base} ({i})" in existing:
        i += 1
    return f"{base} ({i})"


def _reid_act(act: dict[str, Any], new_id: str) -> None:
    """act 改名后重写其 id 与全部 anchor id，保证全局唯一（title 不受唯一约束，保留原值）。"""
    act["id"] = new_id
    for index, anchor in enumerate(act.get("completion_anchors") or []):
        if isinstance(anchor, dict):
            anchor["id"] = f"{new_id}_anchor_{index + 1}"


def _merge_string_buckets(
    merged: dict[str, Any], parent: str, incoming: dict[str, Any], report: MergeReport
) -> bool:
    parent_obj = merged.setdefault(parent, {})
    if not isinstance(parent_obj, dict):
        return False
    touched = False
    for bucket, values in incoming.items():
        if not isinstance(values, list):
            continue
        target = parent_obj.setdefault(bucket, [])
        if not isinstance(target, list):
            continue
        existing = {_text(v) for v in target if _text(v)}
        for value in values:
            t = _text(value)
            if not t:
                continue
            if t in existing:
                report.deduped += 1
            else:
                target.append(t)
                existing.add(t)
                touched = True
    return touched


def _merge_list_item(
    merged: dict[str, Any], field_name: str, item: dict[str, Any],
    resolution: str, entry: dict[str, Any],
) -> None:
    keys = _LIST_IDENTITY[field_name]
    target = merged.setdefault(field_name, [])
    existing_ids = {ident for it in target if isinstance(it, dict) and (ident := _identity(it, keys))}
    ident = _identity(item, keys)
    new_item = copy.deepcopy(item)

    if ident and ident in existing_ids:
        entry["conflict"] = True
        if resolution == "skip":
            entry["action"] = "skipped"
            return
        if resolution == "overwrite":
            idx = next(i for i, it in enumerate(target)
                       if isinstance(it, dict) and _identity(it, keys) == ident)
            target[idx] = new_item
            entry["action"] = "overwritten"
            return
        # rename（默认）
        id_key = next(k for k in keys if _text(item.get(k)))
        new_id = _unique_name(existing_ids, ident)
        if field_name == "act_plan":
            anchor_ids = _collect_anchor_ids(target)
            new_id = _unique_name(existing_ids, ident)
            _reid_act(new_item, new_id)
            # 若 anchor 仍冲突，继续后缀
            while _collect_anchor_ids([new_item]) & anchor_ids:
                new_id = _unique_name(existing_ids | {new_id}, ident)
                _reid_act(new_item, new_id)
        else:
            new_item[id_key] = new_id
        target.append(new_item)
        entry["action"] = "renamed"
        entry["renamed_to"] = new_id
        return

    target.append(new_item)
    entry["action"] = "added"


def merge_modules_into_settings(
    target_settings: dict[str, Any],
    items: list[dict[str, Any]],
    resolutions: dict[str, str],
) -> tuple[dict[str, Any], MergeReport]:
    """items: [{"id": str, "payload": dict}]；resolutions: {module_id: rename|overwrite|skip}。"""
    merged = copy.deepcopy(normalize_story_settings(target_settings))
    report = MergeReport()
    for item in items:
        module_id = str(item.get("id"))
        payload = item.get("payload")
        entry: dict[str, Any] = {"module_id": module_id, "action": "added", "conflict": False}
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in _LIST_IDENTITY and isinstance(value, list):
                    for sub in value:
                        if isinstance(sub, dict):
                            _merge_list_item(merged, key, sub, resolutions.get(module_id, "rename"), entry)
                elif key in _STRING_BUCKETS and isinstance(value, dict):
                    _merge_string_buckets(merged, key, value, report)
        report.entries.append(entry)
    settings = validate_story_settings(merged)
    return settings, report
```

> 注：act 唯一性只约束 id 与 anchor id（不约束 title），故 `_reid_act` 只重写这两者。

- [ ] **Step 4: 运行验证通过**

Run: `docker compose exec api pytest tests/test_module_library.py -v`
Expected: 6 passed。

- [ ] **Step 5: Commit**

```bash
git add api/app/services/module_library.py api/tests/test_module_library.py
git commit -m "feat(api): module_library 并入引擎（去重+冲突 rename/overwrite/skip+validate）"
```

---

### Task 3: AI 本地优化 module_adapter（TDD with mock）

**Files:**
- Create: `api/app/services/module_adapter.py`、`api/app/prompts/adapt_module.md`、`api/tests/test_module_adapter.py`

- [ ] **Step 1: 写失败测试（mock LLM 失败 → 回退原 payload）**

Create `api/tests/test_module_adapter.py`：

```python
import asyncio

from app.services.deepseek_client import DeepSeekError
from app.services.module_adapter import ModuleAdapter


class _FailRouter:
    async def use_pro(self, *args, **kwargs):
        raise DeepSeekError("boom")


class _OkRouter:
    async def use_pro(self, *args, **kwargs):
        class R:
            content = '{"core_characters": [{"name": "红伞客", "role": "npc"}]}'
            model = "test"
        return R()


def test_adapt_fallback_returns_original_on_failure():
    payload = {"core_characters": [{"name": "破晓", "role": "npc"}]}
    out = asyncio.run(ModuleAdapter(router=_FailRouter()).adapt(payload, {"canon_terms": ["雁回镇"]}))
    assert out == payload  # 失败回退原样


def test_adapt_success_returns_adapted_same_shape():
    payload = {"core_characters": [{"name": "破晓", "role": "npc"}]}
    out = asyncio.run(ModuleAdapter(router=_OkRouter()).adapt(payload, {"canon_terms": ["雁回镇"]}))
    assert list(out.keys()) == ["core_characters"]
    assert out["core_characters"][0]["name"] == "红伞客"


def test_adapt_rejects_shape_change_falls_back():
    # LLM 返回顶层键集合不一致 → 回退原 payload
    class _DriftRouter:
        async def use_pro(self, *args, **kwargs):
            class R:
                content = '{"hard_rules": {"must_follow": ["x"]}}'
                model = "test"
            return R()
    payload = {"core_characters": [{"name": "破晓"}]}
    out = asyncio.run(ModuleAdapter(router=_DriftRouter()).adapt(payload, {}))
    assert out == payload
```

- [ ] **Step 2: 运行验证失败**

Run: `docker compose exec api pytest tests/test_module_adapter.py -v`
Expected: FAIL（`ModuleAdapter` 未定义）。

- [ ] **Step 3: 写 prompt**

Create `api/app/prompts/adapt_module.md`：

```
你是 RPGForge 的「设定模块本地化适配器」。用户要把一个可复用设定模块并入一个目标剧本，请把模块改写得贴合目标剧本，但保留模块的功能内核。

输入是一个 JSON：
{
  "module_payload": <最小 story_settings 片段，只有一个顶层键>,
  "target_context": <目标剧本投影：题材/基调、世界观概述、专名表、已有角色名与定位>
}

要求：
1. 严格保留 module_payload 的顶层键和数组/对象结构、保留机制/能力/功能性字段的内核。
2. 改写专名、人名、地名、出身、与现有角色的关系、用词基调，使其贴合 target_context（如沿用目标专名表、避免与已有角色重名、匹配题材基调）。
3. 不要新增或删除顶层键；不要把单条目变多条。
4. 只输出改写后的 module_payload JSON（与输入 module_payload 同结构），不要输出 target_context，不要解释，不要 Markdown。
```

- [ ] **Step 4: 实现 module_adapter.py**

Create `api/app/services/module_adapter.py`：

```python
"""AI 本地优化：把模块 payload 改写得贴合目标剧本。

独立 timeout + fallback：失败/超时/解析失败/结构漂移 → 返回原 payload（退化为直接并入）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.services.deepseek_client import DeepSeekError
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template

logger = logging.getLogger(__name__)

MODULE_ADAPT_TIMEOUT_SECONDS = 120.0


class ModuleAdapter:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def adapt(self, payload: dict[str, Any], target_context: dict[str, Any]) -> dict[str, Any]:
        """返回改写后的 payload；任何异常/结构漂移回退原 payload。"""
        if not isinstance(payload, dict) or not payload:
            return payload
        messages = [
            {"role": "system", "content": load_prompt_template("adapt_module.md")},
            {
                "role": "user",
                "content": json.dumps(
                    {"module_payload": payload, "target_context": target_context},
                    ensure_ascii=False, default=str,
                ),
            },
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_pro("module_adapt", messages, json_mode=True,
                                    max_tokens=4000, reasoning_effort=None),
                timeout=MODULE_ADAPT_TIMEOUT_SECONDS,
            )
            adapted = parse_json_object(result.content)
        except (TimeoutError, DeepSeekError, ValueError) as exc:
            logger.warning("Module adapt failed, fallback to original: %s", exc)
            return payload
        except Exception:
            logger.exception("Unexpected module adapt failure")
            return payload
        # 结构护栏：顶层键集合必须一致，否则回退
        if not isinstance(adapted, dict) or set(adapted.keys()) != set(payload.keys()):
            logger.warning("Module adapt shape drift, fallback to original")
            return payload
        return adapted
```

- [ ] **Step 5: 运行验证通过**

Run: `docker compose exec api pytest tests/test_module_adapter.py -v`
Expected: 3 passed。

- [ ] **Step 6: Commit**

```bash
git add api/app/services/module_adapter.py api/app/prompts/adapt_module.md api/tests/test_module_adapter.py
git commit -m "feat(api): module_adapter AI本地优化（独立timeout+失败/漂移回退）"
```

---

### Task 4: 预览编排 + schemas + 路由 + 注册（含 API 测试）

**Files:**
- Modify: `api/app/services/module_library.py`（加 `project_target_context` + `preview_module_merge`）
- Create: `api/app/schemas/module.py`、`api/app/routers/modules.py`
- Modify: `api/app/main.py`
- Test: `api/tests/test_module_library.py`（加 preview 用例）、`api/tests/test_modules_api.py`

- [ ] **Step 1: 加 preview 编排测试（无 DB，注入假 adapter）**

在 `api/tests/test_module_library.py` 追加：

```python
import asyncio

from app.services.module_library import preview_module_merge, project_target_context


class _IdentityAdapter:
    async def adapt(self, payload, context):
        return payload  # 不改


class _RenameAdapter:
    async def adapt(self, payload, context):
        # 模拟本地优化：把角色名改成贴合目标
        p = {k: v for k, v in payload.items()}
        p["core_characters"] = [{**c, "name": "红伞客"} for c in payload["core_characters"]]
        return p


def test_project_target_context_extracts_canon_and_characters():
    ctx = project_target_context(_base())
    assert ctx["canon_terms"] == ["旧城"]
    assert ctx["characters"] == [{"name": "主角", "role": "protagonist"}]


def test_preview_no_adapt_merges_directly():
    modules = [{"id": "m1", "name": "客", "module_type": "characters",
                "payload": {"core_characters": [{"name": "红伞客", "role": "npc"}]}}]
    out = asyncio.run(preview_module_merge(_base(), modules, adapt=False,
                                           resolutions={}, adapter=_IdentityAdapter()))
    assert [c["name"] for c in out["merged_settings"]["core_characters"]] == ["主角", "红伞客"]
    assert out["adapted"] == []


def test_preview_adapt_records_before_after():
    modules = [{"id": "m1", "name": "破晓", "module_type": "characters",
                "payload": {"core_characters": [{"name": "破晓", "role": "npc"}]}}]
    out = asyncio.run(preview_module_merge(_base(), modules, adapt=True,
                                           resolutions={}, adapter=_RenameAdapter()))
    assert out["adapted"][0]["before"]["core_characters"][0]["name"] == "破晓"
    assert out["adapted"][0]["after"]["core_characters"][0]["name"] == "红伞客"
    assert [c["name"] for c in out["merged_settings"]["core_characters"]] == ["主角", "红伞客"]
```

- [ ] **Step 2: 实现 preview 编排**

在 `api/app/services/module_library.py` 末尾追加：

```python
def project_target_context(settings: dict[str, Any]) -> dict[str, Any]:
    """目标剧本投影，供 AI 适配参考（控 token）。"""
    s = normalize_story_settings(settings)
    core = s.get("story_core") or {}
    profile = s.get("game_profile") or {}
    world = s.get("worldview") or {}
    return {
        "genre": profile.get("genre"),
        "tone": profile.get("tone"),
        "premise": core.get("premise"),
        "central_mystery": core.get("central_mystery"),
        "canon_terms": core.get("canon_terms") or [],
        "worldview_summary": world.get("summary"),
        "characters": [
            {"name": c.get("name"), "role": c.get("role")}
            for c in (s.get("core_characters") or [])
            if isinstance(c, dict)
        ],
    }


async def preview_module_merge(
    target_settings: dict[str, Any],
    modules: list[dict[str, Any]],
    *,
    adapt: bool,
    resolutions: dict[str, str],
    adapter: Any,
) -> dict[str, Any]:
    """编排：可选 AI 适配每个模块 payload，再合并，返回预览（不落地）。

    modules: [{"id","name","module_type","payload"}]；adapter 需有 async adapt(payload, ctx)。
    """
    context = project_target_context(target_settings) if adapt else {}
    items: list[dict[str, Any]] = []
    adapted: list[dict[str, Any]] = []
    for module in modules:
        payload = module["payload"]
        if adapt:
            new_payload = await adapter.adapt(payload, context)
            if new_payload != payload:
                adapted.append({"module_id": module["id"], "before": payload, "after": new_payload})
            payload = new_payload
        items.append({"id": module["id"], "payload": payload})
    settings, report = merge_modules_into_settings(target_settings, items, resolutions)
    return {
        "merged_settings": settings,
        "report": {"entries": report.entries, "deduped": report.deduped},
        "adapted": adapted,
    }
```

- [ ] **Step 3: 运行 preview 测试通过**

Run: `docker compose exec api pytest tests/test_module_library.py -v`
Expected: 全部 passed（含新 3 个）。

- [ ] **Step 4: 写 schemas**

Create `api/app/schemas/module.py`：

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

MODULE_EXPORT_FORMAT_VERSION = "rpgforge.modules.v1"


class SettingModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    module_type: str = Field(min_length=1, max_length=32)
    payload: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    source_game_id: UUID | None = None


class SettingModulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] | None = None


class SettingModuleRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    module_type: str
    payload: dict[str, Any]
    tags: list[str]
    source_game_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModuleImportFile(BaseModel):
    format_version: str
    modules: list[SettingModuleCreate]


class MergePreviewRequest(BaseModel):
    target_settings: dict[str, Any]
    module_ids: list[UUID]
    adapt: bool = False
    conflict_resolutions: dict[str, str] = Field(default_factory=dict)


class MergePreviewResult(BaseModel):
    merged_settings: dict[str, Any]
    report: dict[str, Any]
    adapted: list[dict[str, Any]]
```

- [ ] **Step 5: 写路由**

Create `api/app/routers/modules.py`：

```python
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
        rows = [m for m in rows if needle in m.name.lower() or needle in (m.description or "").lower()]
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
def patch_module(module_id: UUID, payload: SettingModulePatch, db: Session = DB_DEPENDENCY) -> SettingModule:
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
    rows = list(db.scalars(select(SettingModule).where(SettingModule.id.in_(id_list))).all()) if id_list else []
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
async def merge_preview(payload: MergePreviewRequest, db: Session = DB_DEPENDENCY) -> MergePreviewResult:
    rows = list(db.scalars(select(SettingModule).where(SettingModule.id.in_(payload.module_ids))).all())
    by_id = {m.id: m for m in rows}
    modules = [
        {"id": str(mid), "name": by_id[mid].name, "module_type": by_id[mid].module_type, "payload": by_id[mid].payload}
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
```

- [ ] **Step 6: 注册路由**

`api/app/main.py`：import 区加 `from app.routers import modules`（并到现有 `from app.routers import ...` 那批），并在其它 `app.include_router(...)` 后加 `app.include_router(modules.router)`。

- [ ] **Step 7: 写 API 测试**

Create `api/tests/test_modules_api.py`：

```python
from fastapi.testclient import TestClient

from app.main import app


def _create(client, name="测试机制", mtype="mechanics", payload=None, tags=None):
    return client.post("/api/modules", json={
        "name": name, "module_type": mtype,
        "payload": payload or {"core_mechanics": [{"name": name, "rule": "占位规则"}]},
        "tags": tags or [],
    })


def test_create_list_patch_delete(reset_database):
    client = TestClient(app)
    created = _create(client).json()
    assert created["module_type"] == "mechanics"

    listing = client.get("/api/modules").json()
    assert len(listing) == 1

    patched = client.patch(f"/api/modules/{created['id']}", json={"tags": ["占位标签"]}).json()
    assert patched["tags"] == ["占位标签"]
    assert client.get("/api/modules?tag=占位标签").json()[0]["id"] == created["id"]

    assert client.delete(f"/api/modules/{created['id']}").status_code == 204
    assert client.get("/api/modules").json() == []


def test_export_then_import_roundtrip(reset_database):
    client = TestClient(app)
    created = _create(client).json()
    exported = client.get(f"/api/modules/export?ids={created['id']}").json()
    assert exported["format_version"] == "rpgforge.modules.v1"
    client.delete(f"/api/modules/{created['id']}")
    imported = client.post("/api/modules/import", json=exported).json()
    assert len(imported) == 1 and imported[0]["name"] == created["name"]


def test_merge_preview_no_adapt(reset_database):
    client = TestClient(app)
    module = _create(client, name="占位机制",
                     payload={"core_mechanics": [{"name": "占位机制", "rule": "占位"}]}).json()
    target = {
        "format_version": "rpgforge.story.v2",
        "core_characters": [{"name": "主角", "role": "protagonist"}],
    }
    resp = client.post("/api/modules/merge-preview", json={
        "target_settings": target, "module_ids": [module["id"]], "adapt": False,
    }).json()
    names = [m["name"] for m in resp["merged_settings"]["core_mechanics"]]
    assert "占位机制" in names
    assert resp["report"]["entries"][0]["action"] == "added"
```

- [ ] **Step 8: 运行全部后端测试通过**

Run: `docker compose exec api pytest tests/test_module_library.py tests/test_module_adapter.py tests/test_modules_api.py -v`
Expected: 全部 passed。

- [ ] **Step 9: Commit**

```bash
git add api/app/schemas/module.py api/app/routers/modules.py api/app/main.py api/app/services/module_library.py api/tests/test_module_library.py api/tests/test_modules_api.py
git commit -m "feat(api): 模块路由 CRUD/导入导出/merge-preview + 预览编排"
```

## Phase B — 前端

> 验证每个 Task 提交前必须 `cd web && npm run lint`（CI 跑 eslint . 含测试文件/未使用符号）+ `npx tsc --noEmit`；UI 任务末尾 `npm run build`。复用既有 CSS 类。

### Task 5: moduleFragment.ts —— 由 BoardBlock 还原模块 payload（纯函数，vitest）

**Files:**
- Create: `web/lib/moduleFragment.ts`、`web/lib/moduleFragment.test.ts`

- [ ] **Step 1: 写失败测试**

Create `web/lib/moduleFragment.test.ts`：

```ts
import { describe, it, expect } from "vitest";
import { buildModulePayload, moduleTypeFromBlock } from "@/lib/moduleFragment";
import { buildBoardModel, type BoardBlock } from "@/lib/generatorBoard";

const settings = {
  core_characters: [{ name: "主角", role: "protagonist" }, { name: "红伞女人", role: "npc", desire: "复仇" }],
  story_core: { canon_terms: ["雁回镇", "红伞"] },
  hard_rules: { must_follow: ["战斗须详细", "不剧透身世"], must_not: [] },
  core_mechanics: [{ name: "检定", rule: "d20" }]
};
function block(title: string): BoardBlock {
  const model = buildBoardModel({ source: "settings", settings });
  return model.categories.flatMap((c) => c.blocks).find((b) => b.title === title)!;
}

describe("buildModulePayload", () => {
  it("settingsItem 角色 → 完整条目片段", () => {
    expect(buildModulePayload(settings, block("红伞女人"))).toEqual({
      core_characters: [{ name: "红伞女人", role: "npc", desire: "复仇" }]
    });
  });
  it("settingsStringList 约束 → 桶片段", () => {
    expect(buildModulePayload(settings, block("必须遵守"))).toEqual({
      hard_rules: { must_follow: ["战斗须详细", "不剧透身世"] }
    });
  });
  it("settingsStringList 专名 → story_core 桶", () => {
    expect(buildModulePayload(settings, block("专名表"))).toEqual({
      story_core: { canon_terms: ["雁回镇", "红伞"] }
    });
  });
  it("module_type = block.category", () => {
    expect(moduleTypeFromBlock(block("红伞女人"))).toBe("characters");
    expect(moduleTypeFromBlock(block("检定"))).toBe("mechanics");
  });
});
```

- [ ] **Step 2: 运行验证失败** — Run: `cd web && npm test` — Expected: FAIL（未定义）。

- [ ] **Step 3: 实现**

Create `web/lib/moduleFragment.ts`：

```ts
import type { BoardBlock } from "@/lib/generatorBoard";

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}
function asArray(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v) ? (v as Record<string, unknown>[]) : [];
}
function readPath(root: Record<string, unknown>, path: string[]): unknown {
  let node: unknown = root;
  for (const seg of path) {
    if (node && typeof node === "object" && !Array.isArray(node)) {
      node = (node as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return node;
}
function setPath(value: unknown, path: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  let node = out;
  for (let i = 0; i < path.length - 1; i += 1) {
    node[path[i]] = {};
    node = node[path[i]] as Record<string, unknown>;
  }
  node[path[path.length - 1]] = value;
  return out;
}
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v ?? null)) as T;
}

// module_type 直接取看板分类（world/characters/plot/mechanics/constraints/materials）
export function moduleTypeFromBlock(block: BoardBlock): string {
  return block.category;
}

// 从源 story_settings 按 block.address 读出完整数据，组装最小片段 payload。
export function buildModulePayload(
  storySettings: Record<string, unknown>,
  block: BoardBlock
): Record<string, unknown> {
  const a = block.address;
  if (a.kind === "settingsItem") {
    const item = asArray(storySettings[a.arrayKey]).find((it) => str(it[a.idKey]) === a.idValue);
    return item ? { [a.arrayKey]: [clone(item)] } : {};
  }
  if (a.kind === "settingsStringList") {
    const value = readPath(storySettings, a.path);
    return setPath(Array.isArray(value) ? clone(value) : [], a.path);
  }
  if (a.kind === "settingsScalar") {
    const value = readPath(storySettings, a.path);
    return setPath(value === undefined ? "" : clone(value), a.path);
  }
  return {}; // confirmedField 不支持提取（提取仅在 settings 形态看板）
}

// block 是否可提取为模块（仅 settings 形态地址）
export function isExtractable(block: BoardBlock): boolean {
  return block.address.kind !== "confirmedField";
}
```

- [ ] **Step 4: 运行验证通过** — Run: `cd web && npm test` — Expected: 全部 passing。
- [ ] **Step 5: lint + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/lib/moduleFragment.ts web/lib/moduleFragment.test.ts && git commit -m "feat(web): moduleFragment 由 BoardBlock 还原模块 payload"`

---

### Task 6: types + api.ts 模块函数

**Files:**
- Modify: `web/lib/types.ts`、`web/lib/api.ts`

- [ ] **Step 1: types.ts 加类型**

在 `web/lib/types.ts` 末尾追加：

```ts
export type SettingModule = {
  id: string;
  name: string;
  description: string | null;
  module_type: string;
  payload: Record<string, unknown>;
  tags: string[];
  source_game_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ModuleMergeReportEntry = {
  module_id: string;
  action: "added" | "renamed" | "overwritten" | "skipped";
  conflict: boolean;
  renamed_to?: string;
};

export type ModuleMergePreview = {
  merged_settings: Record<string, unknown>;
  report: { entries: ModuleMergeReportEntry[]; deduped: number };
  adapted: { module_id: string; before: Record<string, unknown>; after: Record<string, unknown> }[];
};
```

- [ ] **Step 2: api.ts 加函数**

在 `web/lib/api.ts` 末尾追加（`requestJson`/`getApiBaseUrl`/`downloadBlob` 风格已存在）：

```ts
import type { SettingModule, ModuleMergePreview } from "@/lib/types"; // 若顶部已集中 import，则并入而非重复

export async function listModules(params: { type?: string; tag?: string; q?: string } = {}): Promise<SettingModule[]> {
  const qs = new URLSearchParams();
  if (params.type) qs.set("type", params.type);
  if (params.tag) qs.set("tag", params.tag);
  if (params.q) qs.set("q", params.q);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return requestJson<SettingModule[]>(`/api/modules${suffix}`);
}

export async function createModule(body: {
  name: string; description?: string | null; module_type: string;
  payload: Record<string, unknown>; tags?: string[]; source_game_id?: string | null;
}): Promise<SettingModule> {
  return requestJson<SettingModule>("/api/modules", { method: "POST", body: JSON.stringify(body) });
}

export async function patchModule(id: string, body: { name?: string; description?: string | null; tags?: string[] }): Promise<SettingModule> {
  return requestJson<SettingModule>(`/api/modules/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteModule(id: string): Promise<void> {
  await fetch(`${getApiBaseUrl()}/api/modules/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function importModules(file: unknown): Promise<SettingModule[]> {
  return requestJson<SettingModule[]>("/api/modules/import", { method: "POST", body: JSON.stringify(file) });
}

export async function mergePreviewModules(body: {
  target_settings: Record<string, unknown>; module_ids: string[];
  adapt: boolean; conflict_resolutions?: Record<string, string>;
}): Promise<ModuleMergePreview> {
  return requestJson<ModuleMergePreview>("/api/modules/merge-preview", { method: "POST", body: JSON.stringify(body) });
}

export function moduleExportUrl(ids: string[]): string {
  return `${getApiBaseUrl()}/api/modules/export?ids=${encodeURIComponent(ids.join(","))}`;
}
```

> 注：若 `web/lib/api.ts` 顶部是集中 import 区，把 `SettingModule, ModuleMergePreview` 并入既有 `@/lib/types` import，不要重复 import 行（否则 lint 报 duplicate）。导出下载直接用 `moduleExportUrl` 触发浏览器下载（`window.location.href` 或 `<a download>`）。

- [ ] **Step 3: lint + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/lib/types.ts web/lib/api.ts && git commit -m "feat(web): 模块 API 类型与函数"`

---

### Task 7: 工坊管理页 /workshop

**Files:**
- Create: `web/app/workshop/page.tsx`

- [ ] **Step 1: 写页面**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { deleteModule, importModules, listModules, moduleExportUrl, patchModule } from "@/lib/api";
import type { SettingModule } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  world: "世界与基调", characters: "角色", plot: "剧情结构",
  mechanics: "玩法机制", constraints: "约束与红线", materials: "素材库", advanced: "高级"
};

export default function WorkshopPage() {
  const [modules, setModules] = useState<SettingModule[]>([]);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setModules(await listModules({ type: type || undefined, q: q || undefined }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取失败");
    }
  }
  useEffect(() => { void refresh(); }, [type]); // q 通过按钮触发

  function toggle(id: string) {
    setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  async function handleDelete(id: string) {
    if (!window.confirm("删除该模块？")) return;
    await deleteModule(id); void refresh();
  }
  async function handleRename(m: SettingModule) {
    const name = window.prompt("模块名", m.name);
    if (name && name.trim()) { await patchModule(m.id, { name: name.trim() }); void refresh(); }
  }
  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await importModules(JSON.parse(await file.text()));
      void refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally { e.target.value = ""; }
  }

  return (
    <AppShell>
      <section className="game-page-hero">
        <h1 className="game-page-title">剧本炼金工坊</h1>
        <p className="mt-2 text-sm text-[color:var(--muted)]">可复用设定模块的个人库（仅本地，文件导入导出）。</p>
      </section>
      {error ? <section className="app-alert">{error}</section> : null}

      <section className="surface-panel">
        <div className="flex flex-wrap items-center gap-2">
          <input className="app-input max-w-xs" placeholder="搜索名称/描述…" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && refresh()} />
          <button className="app-button" type="button" onClick={() => void refresh()}>搜索</button>
          <select className="app-input max-w-[10rem]" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">全部类型</option>
            {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="flex-1" />
          <button className="app-button" type="button" onClick={() => fileRef.current?.click()}>⬆ 导入工坊文件</button>
          <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={handleImport} />
          <a className={`app-button ${selected.size ? "" : "pointer-events-none opacity-50"}`}
            href={moduleExportUrl([...selected])}>⬇ 导出所选（{selected.size}）</a>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {modules.length === 0 ? (
            <p className="surface-subtle">暂无模块。去任意剧本设定页的看板「存为模块」。</p>
          ) : modules.map((m) => (
            <article key={m.id} className={`archive-card ${selected.has(m.id) ? "ring-2 ring-[#4a9a6f]" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 font-semibold">
                  <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />
                  {m.name}
                </label>
                <span className="app-pill">{TYPE_LABELS[m.module_type] ?? m.module_type}</span>
              </div>
              {m.description ? <p className="mt-1 text-xs text-[color:var(--muted)]">{m.description}</p> : null}
              {m.tags.length ? <p className="mt-1 text-xs text-[color:var(--muted)]">{m.tags.map((t) => `#${t}`).join(" ")}</p> : null}
              <div className="mt-2 flex gap-2">
                <button className="app-button" type="button" onClick={() => void handleRename(m)}>改名</button>
                <button className="app-button" type="button" onClick={() => void handleDelete(m.id)}>删除</button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
```

- [ ] **Step 2: lint + build** — Run: `cd web && npm run lint && npx tsc --noEmit && npm run build` — Expected: 通过，`/workshop` 路由生成。
- [ ] **Step 3: Commit** — `git add web/app/workshop/page.tsx && git commit -m "feat(web): 工坊管理页 /workshop（列表/搜索/筛选/删除/改名/导入导出）"`

---

### Task 8: 看板「存为模块」入口

**Files:**
- Modify: `web/components/board/BlockDetailModal.tsx`、`web/components/board/SettingsBoard.tsx`
- Create: `web/components/workshop/SaveAsModuleDialog.tsx`

- [ ] **Step 1: BlockDetailModal 加按钮**

`web/components/board/BlockDetailModal.tsx`：props 加 `onSaveAsModule?: () => void;`。在底部按钮区（保存旁）加：

```tsx
          {onSaveAsModule ? (
            <button className="app-button" type="button" onClick={onSaveAsModule} title="把这个设定存为可复用模块">
              ⚗ 存为模块
            </button>
          ) : null}
```

- [ ] **Step 2: SettingsBoard 透传**

`web/components/board/SettingsBoard.tsx`：props 加 `onSaveAsModule?: (block: BoardBlock) => void;`。把它条件透传给 `BlockDetailModal`：

```tsx
          onSaveAsModule={
            onSaveAsModule ? () => { onSaveAsModule(openBlock); setOpenBlock(null); } : undefined
          }
```

- [ ] **Step 3: SaveAsModuleDialog**

Create `web/components/workshop/SaveAsModuleDialog.tsx`：

```tsx
"use client";

import { useState } from "react";

import { createModule } from "@/lib/api";

export function SaveAsModuleDialog({
  defaultName,
  moduleType,
  payload,
  sourceGameId,
  onClose,
  onSaved
}: {
  defaultName: string;
  moduleType: string;
  payload: Record<string, unknown>;
  sourceGameId: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createModule({
        name: name.trim(), description: description.trim() || null, module_type: moduleType,
        payload, tags: tags.split(",").map((t) => t.trim()).filter(Boolean), source_game_id: sourceGameId,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="surface-panel surface-panel-strong w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="surface-title">⚗ 存为模块</h3>
        <div className="mt-3 grid gap-3">
          <label className="grid gap-1 text-sm"><span className="font-semibold">名称</span>
            <input className="app-input" value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="grid gap-1 text-sm"><span className="font-semibold">描述（可选）</span>
            <textarea className="app-input min-h-16" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <label className="grid gap-1 text-sm"><span className="font-semibold">标签（逗号分隔）</span>
            <input className="app-input" value={tags} onChange={(e) => setTags(e.target.value)} /></label>
        </div>
        {error ? <p className="app-alert mt-2">{error}</p> : null}
        <div className="mt-4 flex gap-2">
          <button className="app-button app-button-primary" disabled={saving || !name.trim()} type="button" onClick={handleSave}>
            {saving ? "保存中..." : "存入工坊"}
          </button>
          <button className="app-button" type="button" onClick={onClose}>取消</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: lint + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/components/board/BlockDetailModal.tsx web/components/board/SettingsBoard.tsx web/components/workshop/SaveAsModuleDialog.tsx && git commit -m "feat(web): 看板「存为模块」按钮 + SaveAsModuleDialog"`

---

### Task 9: 共享并入面板 ModuleMergePanel

**Files:**
- Create: `web/components/workshop/ModuleMergePanel.tsx`

- [ ] **Step 1: 写组件**

```tsx
"use client";

import { useEffect, useState } from "react";

import { listModules, mergePreviewModules } from "@/lib/api";
import type { ModuleMergePreview, SettingModule } from "@/lib/types";

type Resolution = "rename" | "overwrite" | "skip";

export function ModuleMergePanel({
  targetSettings,
  onApply
}: {
  targetSettings: Record<string, unknown>;
  onApply: (merged: Record<string, unknown>) => Promise<void> | void;
}) {
  const [modules, setModules] = useState<SettingModule[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adapt, setAdapt] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [preview, setPreview] = useState<ModuleMergePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void listModules().then(setModules).catch(() => {}); }, []);

  function toggle(id: string) {
    setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
    setPreview(null);
  }

  async function runPreview() {
    setBusy(true); setError(null);
    try {
      setPreview(await mergePreviewModules({
        target_settings: targetSettings, module_ids: [...selected],
        adapt, conflict_resolutions: resolutions,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "预览失败");
    } finally { setBusy(false); }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true); setError(null);
    try {
      await onApply(preview.merged_settings);
      setPreview(null); setSelected(new Set()); setResolutions({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "并入失败");
    } finally { setBusy(false); }
  }

  return (
    <section className="surface-panel">
      <h2 className="surface-title">从工坊并入</h2>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {modules.length === 0 ? <p className="surface-subtle">工坊暂无模块。</p> :
          modules.map((m) => (
            <label key={m.id} className={`archive-card flex items-center gap-2 ${selected.has(m.id) ? "ring-2 ring-[#4a9a6f]" : ""}`}>
              <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />
              <span className="font-semibold">{m.name}</span>
              <span className="app-pill ml-auto">{m.module_type}</span>
            </label>
          ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={adapt} onChange={(e) => { setAdapt(e.target.checked); setPreview(null); }} />
          ⭐ AI 本地优化（改写贴合当前剧本）
        </label>
        <button className="app-button app-button-primary" type="button" disabled={busy || selected.size === 0} onClick={() => void runPreview()}>
          {busy ? "处理中..." : "生成并入预览"}
        </button>
      </div>
      {error ? <p className="app-alert mt-2">{error}</p> : null}

      {preview ? (
        <div className="mt-4 border-t border-[color:var(--border)] pt-3">
          <h3 className="font-semibold">并入预览</h3>
          <p className="text-xs text-[color:var(--muted)]">去重跳过 {preview.report.deduped} 条重复字符串。</p>
          <div className="mt-2 grid gap-2">
            {preview.report.entries.map((e) => {
              const mod = modules.find((m) => m.id === e.module_id);
              return (
                <div key={e.module_id} className="archive-card text-sm">
                  <b>{mod?.name ?? e.module_id}</b> — {actionLabel(e.action)}{e.renamed_to ? `（→ ${e.renamed_to}）` : ""}
                  {e.conflict ? (
                    <span className="ml-2">
                      冲突处理：
                      {(["rename", "overwrite", "skip"] as Resolution[]).map((r) => (
                        <button key={r}
                          className={`app-button ml-1 ${(resolutions[e.module_id] ?? "rename") === r ? "app-button-primary" : ""}`}
                          type="button"
                          onClick={() => { setResolutions((s) => ({ ...s, [e.module_id]: r })); setPreview(null); }}>
                          {resLabel(r)}
                        </button>
                      ))}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
          {preview.adapted.length ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-sm text-[color:var(--muted)]">⭐ AI 改写前后对比（{preview.adapted.length}）</summary>
              <div className="mt-2 grid gap-2">
                {preview.adapted.map((a) => (
                  <div key={a.module_id} className="grid gap-1 sm:grid-cols-2">
                    <pre className="app-wrap-text rounded border border-[#f0c2bb] bg-[#fff0ee] p-2 text-xs">{JSON.stringify(a.before, null, 1)}</pre>
                    <pre className="app-wrap-text rounded border border-[#bfe0c8] bg-[#eef7f0] p-2 text-xs">{JSON.stringify(a.after, null, 1)}</pre>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button className="app-button app-button-primary" type="button" disabled={busy} onClick={() => void confirm()}>确认并入</button>
            <button className="app-button" type="button" onClick={() => setPreview(null)}>取消</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function actionLabel(a: string): string {
  return ({ added: "新增", renamed: "改名并入", overwritten: "覆盖现有", skipped: "跳过" } as Record<string, string>)[a] ?? a;
}
function resLabel(r: Resolution): string {
  return ({ rename: "改名", overwrite: "覆盖", skip: "跳过" } as Record<Resolution, string>)[r];
}
```

> 交互：改 resolution 或 adapt 会清空 preview，需重新点「生成并入预览」——保证预览与选择一致。

- [ ] **Step 2: lint + commit** — `cd web && npm run lint && npx tsc --noEmit` 后 `git add web/components/workshop/ModuleMergePanel.tsx && git commit -m "feat(web): 共享并入面板 ModuleMergePanel（选模块/AI优化/预览/冲突/确认）"`

---

### Task 10: 挂到设定页(🅱) + 生成页(🅰) + 看板提取接线

**Files:**
- Modify: `web/app/games/[id]/settings/page.tsx`、`web/app/games/new/page.tsx`

- [ ] **Step 1: 设定页接入提取 + 并入**

在 `web/app/games/[id]/settings/page.tsx` 的 `SettingsView`：

1. import：`import { ModuleMergePanel } from "@/components/workshop/ModuleMergePanel";`、`import { SaveAsModuleDialog } from "@/components/workshop/SaveAsModuleDialog";`、`import { buildModulePayload, moduleTypeFromBlock, isExtractable } from "@/lib/moduleFragment";`、`import type { BoardBlock } from "@/lib/generatorBoard";`。
2. state：`const [moduleBlock, setModuleBlock] = useState<BoardBlock | null>(null);`
3. 给 `<SettingsBoard>` 加：`onSaveAsModule={(block) => { if (isExtractable(block)) setModuleBlock(block); }}`。
4. 在 `<SettingsAdvanced .../>` 之后加并入面板（onApply = 复用 persist，已并入整份 settings）：

```tsx
      <ModuleMergePanel
        targetSettings={settings}
        onApply={async (merged) => { await persist(merged); }}
      />
      {moduleBlock ? (
        <SaveAsModuleDialog
          defaultName={moduleBlock.title}
          moduleType={moduleTypeFromBlock(moduleBlock)}
          payload={buildModulePayload(settings, moduleBlock)}
          sourceGameId={game.id}
          onClose={() => setModuleBlock(null)}
          onSaved={() => setModuleBlock(null)}
        />
      ) : null}
```

> `persist(merged)` 已存在（Task 4/特性1：PATCH config + 刷新 + 409 处理），直接复用即可落地并入结果并存版本快照。

- [ ] **Step 2: 生成页接入并入（草稿）**

在 `web/app/games/new/page.tsx`：当 `generatedConfig` 存在时，在生成结果区下方挂并入面板，`onApply` = 把并入结果写回本地草稿：

1. import `ModuleMergePanel`。
2. 渲染（`generatedConfig` 非空时）：

```tsx
      {generatedConfig ? (
        <ModuleMergePanel
          targetSettings={generatedConfig.story_settings}
          onApply={(merged) => { setGeneratedConfig({ ...generatedConfig, story_settings: merged }); }}
        />
      ) : null}
```

> 生成草稿并入只改本地 `generatedConfig`，「确认并开始冒险」时随草稿一起落库（复用特性1 的 createGeneratedGame 路径）。生成页看板的「存为模块」P1 不接（提取主场景是已有剧本设定页）。

- [ ] **Step 3: lint + build** — Run: `cd web && npm run lint && npx tsc --noEmit && npm run build` — Expected: 通过。
- [ ] **Step 4: Commit** — `git add web/app/games/\[id\]/settings/page.tsx web/app/games/new/page.tsx && git commit -m "feat(web): 设定页(提取+并入) + 生成页(草稿并入) 接入炼金工坊"`

---

## Phase C — 部署、验证、文档

### Task 11: 迁移 + 重建 + 全量验证 + 文档

**Files:**
- Modify: `docs/OPTIMIZATION_PLAN.md`

- [ ] **Step 1: 迁移 + 重建（Docker 不挂源码，api/worker/web 都要重建）**

Run: `docker compose exec api alembic upgrade head`（若 Task 1 已做则确认在 head）
Run: `docker compose up -d --build api worker web`
然后 `docker images | grep rpgforge` 核实三者构建时间是刚刚（别只信命令输出）。

- [ ] **Step 2: 后端全量回归** — Run: `docker compose exec api pytest tests/` — Expected: 既有全过 + 新增（module_library/adapter/api）。

- [ ] **Step 3: 前端验证** — Run: `cd web && npm run lint && npm test && npx tsc --noEmit && npm run build` — Expected: 全过，路由含 `/workshop`。

- [ ] **Step 4: 手动走查（待用户）**

1. 任意剧本设定页看板 → 点 block →「⚗ 存为模块」→ 填名/标签 → 存入；`/workshop` 能看到。
2. `/workshop`：搜索/类型筛选/改名/删除；选中导出文件、再导入回来。
3. 另一剧本设定页 →「从工坊并入」→ 选模块 → 不开 AI →「生成并入预览」→ 看新增/去重/同名冲突选项 → 确认 → 看板出现并入内容、版本历史多一条快照（可回滚）。
4. 开「AI 本地优化」→ 预览出现改写前后对比、专名/名字贴合当前剧本 → 确认并入。
5. 新建剧本生成出草稿后 →「从工坊并入」→ 确认 → 草稿看板更新 →「确认并开始冒险」入库为并入后的设定。

- [ ] **Step 5: OPTIMIZATION_PLAN 追加 Round**

`docs/OPTIMIZATION_PLAN.md` §0/§1 追加 `### Round N (2026-06-04)`：剧本炼金工坊——`setting_modules` 表 + 合并引擎 + AI 适配（新 prompt `adapt_module.md`）+ `/api/modules` 路由 + `/workshop` 页 + 看板存为模块 + 设定页/生成页并入。记新 LLM 调用（module_adapt，独立 timeout+fallback）。不改历史 Round。

- [ ] **Step 6: Commit** — `git add docs/OPTIMIZATION_PLAN.md && git commit -m "docs: OPTIMIZATION_PLAN 追加炼金工坊 Round 条目"`

---

## 自审（Self-Review）

**Spec 覆盖：**
- §3 表 → Task 1 ✓；§4 payload 片段（提取还原）→ Task 5（moduleFragment）✓
- §5 合并引擎（桶去重 + 冲突 rename/overwrite/skip + validate）→ Task 2 ✓
- §6 AI 本地优化（timeout+fallback+结构护栏）→ Task 3 ✓
- §7 API（CRUD/导入导出/merge-preview，merge-preview 用 target_settings 统一两入口）→ Task 4 + Task 6 ✓
- §8 前端（/workshop + 看板存为模块 + 共享并入面板，挂设定页&生成页）→ Task 7/8/9/10 ✓
- §10 错误边界（adapt 回退、validate 失败 400、409、导入 format_version）→ Task 3/4 ✓
- §11 测试 → Task 2/3/4 pytest + Task 5 vitest + Task 11 lint/build ✓
- §12 遵 CLAUDE.md（新 LLM timeout+fallback、新 prompt 记录、迁移、隐私占位符）→ Task 3/11 ✓

**Placeholder 扫描：** 新代码均完整；接线类（Task 10）给精确 import/state/render 片段；删改无。无 TBD/TODO。

**类型一致性：**
- 合并 `merge_modules_into_settings(target, items=[{id,payload}], resolutions)` 在 Task 2 定义、Task 4 preview 调用一致。
- `preview_module_merge(target, modules=[{id,name,module_type,payload}], *, adapt, resolutions, adapter)` 在 Task 4 定义、路由调用一致；返回 `{merged_settings, report{entries,deduped}, adapted}` 与 schema `MergePreviewResult` 及前端 `ModuleMergePreview` 三处一致。
- `ModuleAdapter.adapt(payload, context)` async，Task 3 定义、Task 4 preview 调用、测试假 adapter 同签名。
- 前端 `buildModulePayload(storySettings, block)` / `moduleTypeFromBlock(block)` / `isExtractable(block)` Task 5 定义、Task 10 调用一致。
- `SettingsBoard.onSaveAsModule?(block)` Task 8 定义、Task 10 传入；`BlockDetailModal.onSaveAsModule?()` Task 8 定义、SettingsBoard 透传一致。
- api 函数名 `listModules/createModule/patchModule/deleteModule/importModules/mergePreviewModules/moduleExportUrl` Task 6 定义、Task 7/8/9 调用一致。

**依赖一致性：** 顶部声明从合并了特性1的 main 切分支；复用 `BoardBlock.address`/`buildBoardModel`/`writeBlockFields`(间接)/`updateGameConfig`/`SettingsBoard`/设定页 persist。
