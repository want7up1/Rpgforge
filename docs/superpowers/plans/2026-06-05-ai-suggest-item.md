# 新增设定 AI 补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 游戏设定页「新增设定」弹窗里，用户只填标题/名称，AI 按精简剧本大纲补全其余字段并填入表单（可改）。

**Architecture:** 后端新增 `ItemSuggester` service（仿 `module_adapter.py`：单次 DeepSeek 调用 + 独立 timeout + 多重 fallback）+ 一个 `POST /api/games/{id}/settings/suggest-item` 端点。前端在 `BlockDetailModal` 新增态加「✨ AI 补全」按钮，仅游戏设定页传 `aiSuggest` 回调（工坊不传 → 不显示）。

**Tech Stack:** FastAPI + SQLAlchemy + DeepSeek（ModelRouter.use_flash）；Next.js + React + TypeScript；pytest（容器内）/ vitest。

参考设计文档：`docs/superpowers/specs/2026-06-05-ai-suggest-item-design.md`

**全局约定（实现者必读）：**
- **docker 不挂载源码**：改任何 `api/` 代码后，跑后端测试前必须 `docker compose up -d --build api`（否则容器里是旧代码）。前端命令在 `web/` 下。
- 后端 LLM 调用统一走 `ModelRouter`；本功能用 `use_flash`（轻量、省钱）+ `reasoning_effort=None`（关闭推理，省 token）。
- mock 测试模式见 `api/tests/test_module_adapter.py`：定义带 `async def use_flash(self, *a, **k)` 的假 router，返回带 `.content`/`.model` 的对象，用 `asyncio.run`。
- `game.config.story_settings` 是 JSONB `dict`（`api/app/models/game.py:95`）。

---

## File Structure

- **Create** `api/app/prompts/suggest_item.md` —— 固定系统提示（吃前缀缓存）。
- **Create** `api/app/services/item_suggester.py` —— 补全 service：字段表、大纲组装、LLM 调用、timeout/fallback、结果过滤。
- **Create** `api/tests/test_item_suggester.py` —— service 单测（mock router）。
- **Modify** `api/app/schemas/game.py` —— `SuggestItemRequest` / `SuggestItemResponse`。
- **Modify** `api/app/routers/games.py` —— `POST /{game_id}/settings/suggest-item`。
- **Modify** `web/lib/api.ts` —— `suggestItem`。
- **Modify** `web/components/board/BlockDetailModal.tsx` —— 「✨ AI 补全」按钮 + loading/失败态。
- **Modify** `web/components/board/SettingsBoard.tsx` / `PlotMasterDetail.tsx` —— 透传 `onSuggestItem`。
- **Modify** `web/app/games/[id]/settings/page.tsx` —— 注入 `onSuggestItem`（调 `suggestItem(gameId, …)`）。
- **Modify** `docs/OPTIMIZATION_PLAN.md` —— Round 条目 + 记录新 prompt。

---

## Task 1: 后端 ItemSuggester service + prompt + 测试

**Files:**
- Create: `api/app/prompts/suggest_item.md`
- Create: `api/app/services/item_suggester.py`
- Test: `api/tests/test_item_suggester.py`

- [ ] **Step 1: 写 prompt 文件**

Create `api/app/prompts/suggest_item.md`:

```markdown
你是 TRPG 剧本设定助手。根据给定的「剧本大纲」(outline)、条目类型 (item_type)、用户已填的标题 (title)，为 fields_to_fill 中列出的每个字段生成**简洁、贴合剧本**的中文内容。

要求：
- 只返回严格 JSON 对象，键为 fields_to_fill 的字段名，值为该字段内容。
- 字段语义见 fields_to_fill 的中文说明；数组字段返回 JSON 数组，布尔字段返回 true/false。
- 不要包含 title、id、act_id 等身份/引用字段。
- 不要输出解释、注释或额外文字，只输出 JSON。
- 内容简短克制，宁缺毋滥；无把握的字段可给空字符串或空数组。
```

- [ ] **Step 2: 写失败测试**

Create `api/tests/test_item_suggester.py`:

```python
import asyncio

from app.services.deepseek_client import DeepSeekError
from app.services.item_suggester import ItemSuggester, build_outline


class _OkRouter:
    def __init__(self, content: str) -> None:
        self._content = content

    async def use_flash(self, *args, **kwargs):
        class R:
            content = self._content
            model = "test"
        return R()


class _FailRouter:
    async def use_flash(self, *args, **kwargs):
        raise DeepSeekError("boom")


OUTLINE_SETTINGS = {
    "game_profile": {"title": "占位剧名", "genre": "悬疑", "tone": "压抑"},
    "story_core": {"premise": "占位前提", "central_mystery": "占位悬念"},
    "worldview": {"summary": "占位世界观一句话"},
    "core_characters": [{"name": "不该进大纲"}],
}


def test_build_outline_only_includes_concise_fields():
    text = build_outline(OUTLINE_SETTINGS)
    assert "占位剧名" in text
    assert "占位悬念" in text
    assert "占位世界观一句话" in text
    # 不泄漏全量设定（如角色数组）
    assert "不该进大纲" not in text


def test_suggest_success_filters_to_allowed_fields():
    content = '{"role": "npc", "description": "占位描述", "title": "改不了", "evil": "x"}'
    out = asyncio.run(
        ItemSuggester(router=_OkRouter(content)).suggest(
            "core_characters", {"name": "占位角色"}, OUTLINE_SETTINGS
        )
    )
    assert out["role"] == "npc"
    assert out["description"] == "占位描述"
    assert "title" not in out  # 身份字段不回写
    assert "name" not in out   # 身份字段不回写
    assert "evil" not in out   # 越界字段被剔除


def test_suggest_unknown_array_key_returns_empty():
    out = asyncio.run(
        ItemSuggester(router=_OkRouter("{}")).suggest("nope", {"name": "x"}, OUTLINE_SETTINGS)
    )
    assert out == {}


def test_suggest_fallback_on_llm_failure():
    out = asyncio.run(
        ItemSuggester(router=_FailRouter()).suggest("core_characters", {"name": "x"}, OUTLINE_SETTINGS)
    )
    assert out == {}


def test_suggest_fallback_on_bad_json():
    out = asyncio.run(
        ItemSuggester(router=_OkRouter("not json at all")).suggest(
            "core_characters", {"name": "x"}, OUTLINE_SETTINGS
        )
    )
    assert out == {}
```

- [ ] **Step 3: 重建 api 镜像并跑测试，确认失败**

Run:
```bash
docker compose up -d --build api && docker compose exec api pytest tests/test_item_suggester.py -v
```
Expected: FAIL（`ModuleNotFoundError: app.services.item_suggester`）

- [ ] **Step 4: 写 service 实现**

Create `api/app/services/item_suggester.py`:

```python
"""新增设定项 AI 补全：用户给标题/名称，按精简剧本大纲补全其余字段。

独立 timeout + fallback：失败/超时/解析失败/结构漂移 → 返回空 dict（前端提示手动填）。
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

SUGGEST_ITEM_TIMEOUT_SECONDS = 40.0

# 各数组的身份字段（用户必填，AI 不覆盖）。
IDENTITY_FIELD: dict[str, str] = {
    "core_characters": "name",
    "act_plan": "title",
    "main_quest_path": "title",
    "core_mechanics": "name",
    "action_style_rules": "name",
    "story_material_library": "title",
}

# 各数组的待补字段 → 中文说明（不含 id / 身份字段 / act_id）。
SUGGEST_FIELDS: dict[str, dict[str, str]] = {
    "core_characters": {
        "role": "定位：protagonist/npc/companion/other",
        "identity": "身份背景",
        "aliases": "别名（字符串数组）",
        "description": "人物描述",
        "appearance": "外貌",
        "desire": "欲望/目标",
        "fear": "恐惧",
        "leverage": "把柄/弱点",
        "relationship_arc": "与主角的关系弧",
        "dramatic_function": "戏剧功能",
        "public_limit": "公开限度",
        "portrait_prompt": "立绘提示词",
        "visibility": "可见性",
    },
    "act_plan": {
        "objective": "本幕目标",
        "dramatic_question": "本幕戏剧问题",
        "must_hit_beats": "必经节点（字符串数组）",
        "allowed_reveals": "允许揭示（字符串数组）",
        "forbidden_reveals": "禁止揭示（字符串数组）",
        "completion_anchors": "完成锚点（对象数组，可留空[]）",
        "transition_to_next_act": "转场到下一幕的条件（对象，可留空{}）",
    },
    "main_quest_path": {
        "objective": "节点目标",
        "player_visible": "玩家是否可见",
        "completion_signal": "完成信号",
        "optional": "是否可选（布尔）",
    },
    "core_mechanics": {
        "rule": "机制规则说明",
        "visibility": "可见性",
    },
    "action_style_rules": {
        "triggers": "触发词（字符串数组）",
        "rule": "行文风格规则",
        "priority": "优先级",
        "enabled": "是否启用（布尔）",
    },
    "story_material_library": {
        "type": "素材类型",
        "keywords": "关键词（字符串数组）",
        "triggers": "触发词（字符串数组）",
        "priority": "优先级",
        "always_on": "是否常驻（布尔）",
        "visibility": "可见性",
        "public_info": "公开信息",
        "gm_secret": "GM 秘密",
        "content": "素材内容",
        "usage": "用法",
        "enabled": "是否启用（布尔）",
    },
}


def build_outline(story_settings: dict[str, Any]) -> str:
    """拼装精简剧本大纲（控制 token）：只取 profile + story_core + worldview 概要。"""
    profile = story_settings.get("game_profile") or {}
    core = story_settings.get("story_core") or {}
    worldview = story_settings.get("worldview") or {}
    parts: list[str] = []
    for key, lbl in (("title", "作品"), ("genre", "类型"), ("tone", "基调")):
        v = str(profile.get(key) or "").strip()
        if v:
            parts.append(f"{lbl}：{v}")
    for key, lbl in (
        ("premise", "前提"),
        ("central_mystery", "核心悬念"),
        ("main_goal", "主目标"),
        ("emotional_arc", "情感弧"),
        ("narrative_style", "叙事风格"),
    ):
        v = str(core.get(key) or "").strip()
        if v:
            parts.append(f"{lbl}：{v}")
    summary = str(worldview.get("summary") or "").strip()
    if summary:
        parts.append(f"世界观：{summary[:120]}")
    return "\n".join(parts)


class ItemSuggester:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def suggest(
        self, array_key: str, draft: dict[str, Any], story_settings: dict[str, Any]
    ) -> dict[str, Any]:
        """返回补全字段 dict；任何异常/漂移回退空 dict。"""
        fields = SUGGEST_FIELDS.get(array_key)
        if not fields:
            return {}
        identity_key = IDENTITY_FIELD.get(array_key, "title")
        title = str((draft or {}).get(identity_key) or "")
        messages = [
            {"role": "system", "content": load_prompt_template("suggest_item.md")},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "outline": build_outline(story_settings or {}),
                        "item_type": array_key,
                        "title": title,
                        "fields_to_fill": fields,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_flash(
                    "suggest_item", messages, json_mode=True,
                    max_tokens=1500, reasoning_effort=None,
                ),
                timeout=SUGGEST_ITEM_TIMEOUT_SECONDS,
            )
            parsed = parse_json_object(result.content)
        except (TimeoutError, DeepSeekError, ValueError) as exc:
            logger.warning("Item suggest failed, fallback to empty: %s", exc)
            return {}
        except Exception:
            logger.exception("Unexpected item suggest failure")
            return {}
        if not isinstance(parsed, dict):
            return {}
        # 过滤：只保留待补字段，剔除身份字段，防越界/覆盖
        allowed = set(fields.keys())
        return {k: v for k, v in parsed.items() if k in allowed and k != identity_key}
```

- [ ] **Step 5: 重建并跑测试，确认通过**

Run:
```bash
docker compose up -d --build api && docker compose exec api pytest tests/test_item_suggester.py -v
```
Expected: PASS（5 个用例全绿）

- [ ] **Step 6: ruff 检查**

Run: `docker compose exec api ruff check app/services/item_suggester.py tests/test_item_suggester.py`
Expected: 无错误

- [ ] **Step 7: Commit**

```bash
git add api/app/prompts/suggest_item.md api/app/services/item_suggester.py api/tests/test_item_suggester.py
git commit -m "feat(api): ItemSuggester 新增设定 AI 补全 service（独立 timeout+fallback）"
```

---

## Task 2: 后端端点 + schema

**Files:**
- Modify: `api/app/schemas/game.py`
- Modify: `api/app/routers/games.py`
- Test: `api/tests/test_games.py`

- [ ] **Step 1: 加 schema**

在 `api/app/schemas/game.py` 末尾追加（确认文件已 `from pydantic import BaseModel, Field`；若缺 Field 则补 import）：

```python
class SuggestItemRequest(BaseModel):
    array_key: str
    draft: dict[str, Any] = Field(default_factory=dict)


class SuggestItemResponse(BaseModel):
    fields: dict[str, Any]
```

> 若 `api/app/schemas/game.py` 顶部未导入 `Any`，补 `from typing import Any`。

- [ ] **Step 2: 写失败测试**

在 `api/tests/test_games.py` 末尾追加（沿用该文件已有的 `client` / 建游戏夹具风格；下例假设已有 `client` fixture 与建游戏 helper，如无则参照文件内现有用例的建游戏方式）：

```python
def test_suggest_item_endpoint_returns_fields(client, monkeypatch):
    # mock service，避免真实 LLM
    async def fake_suggest(self, array_key, draft, story_settings):
        return {"role": "npc", "description": "占位"}

    monkeypatch.setattr(
        "app.services.item_suggester.ItemSuggester.suggest", fake_suggest
    )
    game_id = _create_minimal_game(client)  # 见文件内已有建游戏 helper
    resp = client.post(
        f"/api/games/{game_id}/settings/suggest-item",
        json={"array_key": "core_characters", "draft": {"name": "占位角色"}},
    )
    assert resp.status_code == 200
    assert resp.json()["fields"]["role"] == "npc"
```

> **注意**：`_create_minimal_game` 用 `test_games.py` 内已有的建游戏方式（搜索文件里现成的 POST `/api/games` helper 复用，不要新造）。

- [ ] **Step 3: 重建并跑测试，确认失败**

Run:
```bash
docker compose up -d --build api && docker compose exec api pytest tests/test_games.py::test_suggest_item_endpoint_returns_fields -v
```
Expected: FAIL（404，端点不存在）

- [ ] **Step 4: 加端点**

在 `api/app/routers/games.py` 的 import 区，把 schema 导入补上 `SuggestItemRequest, SuggestItemResponse`，并加：

```python
from app.services.item_suggester import ItemSuggester
```

在文件末尾（其它 `@router` 端点旁）追加：

```python
@router.post("/{game_id}/settings/suggest-item", response_model=SuggestItemResponse)
async def suggest_settings_item(
    game_id: UUID,
    payload: SuggestItemRequest,
    db: Session = DB_DEPENDENCY,
) -> SuggestItemResponse:
    game = get_game_or_404(db, game_id)
    story_settings = game.config.story_settings if game.config else {}
    fields = await ItemSuggester().suggest(payload.array_key, payload.draft, story_settings)
    return SuggestItemResponse(fields=fields)
```

- [ ] **Step 5: 重建并跑测试，确认通过**

Run:
```bash
docker compose up -d --build api && docker compose exec api pytest tests/test_games.py::test_suggest_item_endpoint_returns_fields -v
```
Expected: PASS

- [ ] **Step 6: ruff + 回归**

Run:
```bash
docker compose exec api ruff check app/routers/games.py app/schemas/game.py && docker compose exec api pytest tests/test_games.py tests/test_item_suggester.py -q
```
Expected: ruff 干净；测试全绿

- [ ] **Step 7: Commit**

```bash
git add api/app/routers/games.py api/app/schemas/game.py api/tests/test_games.py
git commit -m "feat(api): POST /games/{id}/settings/suggest-item 端点"
```

---

## Task 3: 前端 api 客户端 + BlockDetailModal 按钮

**Files:**
- Modify: `web/lib/api.ts`
- Modify: `web/components/board/BlockDetailModal.tsx`

- [ ] **Step 1: 加 api 客户端方法**

在 `web/lib/api.ts` 加（沿用文件内现有 fetch 封装风格；下例用通用 fetch，实现时替换成文件里已有的请求 helper）：

```ts
export async function suggestItem(
  gameId: string,
  arrayKey: string,
  draft: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/games/${gameId}/settings/suggest-item`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ array_key: arrayKey, draft })
  });
  if (!res.ok) throw new Error(`suggest-item 失败: ${res.status}`);
  const data = (await res.json()) as { fields: Record<string, unknown> };
  return data.fields ?? {};
}
```

> 实现时先看 `web/lib/api.ts` 顶部是否已有统一的 `apiFetch`/`request` 封装与 base URL 处理，有则复用，保持与其它端点一致。

- [ ] **Step 2: BlockDetailModal 加 aiSuggest prop + 按钮**

在 `web/components/board/BlockDetailModal.tsx`：props 增加可选 `aiSuggest?: (draft: Record<string, BoardFieldValue>) => Promise<Record<string, unknown>>;`。

在组件内 `drafts` state 旁加：

```tsx
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);

  async function handleSuggest() {
    if (!aiSuggest) return;
    setSuggesting(true);
    setSuggestError(null);
    try {
      const fields = await aiSuggest(drafts);
      setDrafts((d) => {
        const next = { ...d };
        for (const [k, v] of Object.entries(fields)) {
          const cur = next[k];
          const empty = cur == null || cur === "" || (Array.isArray(cur) && cur.length === 0);
          if (empty) next[k] = v as BoardFieldValue; // 用户已填值优先，不覆盖
        }
        return next;
      });
      if (Object.keys(fields).length === 0) setSuggestError("AI 补全失败，请手动填写");
    } catch {
      setSuggestError("AI 补全失败，请手动填写");
    } finally {
      setSuggesting(false);
    }
  }
```

在底部按钮区（`保存` 按钮附近）加：

```tsx
          {aiSuggest ? (
            <button className="app-button" type="button" onClick={handleSuggest} disabled={suggesting}>
              {suggesting ? "AI 补全中…" : "✨ AI 补全"}
            </button>
          ) : null}
```

在标题或按钮区下方加错误提示：

```tsx
        {suggestError ? <p className="mt-2 text-sm text-[#e0533d]">{suggestError}</p> : null}
```

> `useState` 已在文件顶部 import；`BoardFieldValue` 已从 `@/lib/generatorBoard` import。

- [ ] **Step 3: 类型检查 + lint**

Run: `cd web && npx tsc --noEmit && npm run lint`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add web/lib/api.ts web/components/board/BlockDetailModal.tsx
git commit -m "feat(web): BlockDetailModal AI 补全按钮 + suggestItem 客户端"
```

---

## Task 4: 接线 —— SettingsBoard / PlotMasterDetail / 设定页

**Files:**
- Modify: `web/components/board/SettingsBoard.tsx`
- Modify: `web/components/board/PlotMasterDetail.tsx`
- Modify: `web/app/games/[id]/settings/page.tsx`

- [ ] **Step 1: SettingsBoard 透传 onSuggestItem**

`SettingsBoard` props 增加可选：

```tsx
  onSuggestItem?: (arrayKey: string, draft: Record<string, unknown>) => Promise<Record<string, unknown>>;
```

把它加入解构参数。在「新增数组项」的 `BlockDetailModal`（`addingArray` 分支）传：

```tsx
          aiSuggest={
            onSuggestItem ? (draft) => onSuggestItem(addingArray, draft) : undefined
          }
```

并把 `onSuggestItem` 透传给 plot 分支的 `PlotMasterDetail`：

```tsx
        <PlotMasterDetail
          ...
          onSuggestItem={onSuggestItem}
        />
```

- [ ] **Step 2: PlotMasterDetail 透传到新增弹窗**

`PlotMasterDetail` props 增加可选：

```tsx
  onSuggestItem?: (arrayKey: string, draft: Record<string, unknown>) => Promise<Record<string, unknown>>;
```

加入解构。在「新增幕 / 节点」的 `BlockDetailModal`（`adding && addingBlock` 分支）传：

```tsx
          aiSuggest={
            onSuggestItem
              ? (draft) => onSuggestItem(adding === "node" ? "main_quest_path" : "act_plan", draft)
              : undefined
          }
```

- [ ] **Step 3: 设定页注入 onSuggestItem**

在 `web/app/games/[id]/settings/page.tsx`：import `suggestItem`，给 `<SettingsBoard>` 传：

```tsx
        onSuggestItem={(arrayKey, draft) => suggestItem(gameId, arrayKey, draft)}
```

> `gameId` 用该页已有的游戏 id 变量（搜索文件内现成的 `params`/`id` 取法，复用，不要新造）。
> **工坊页 `web/app/workshop/page.tsx` 不传该 prop** → AI 补全按钮在工坊不显示（符合设计）。

- [ ] **Step 4: 类型检查 + lint + 构建**

Run: `cd web && npx tsc --noEmit && npm run lint && npm run build`
Expected: 全部成功

- [ ] **Step 5: 手动验证**

```bash
docker compose up -d --build web
```
打开某游戏设定页 `/games/<id>/settings`：
1. 任一分类点「＋新增」→ 弹窗里填名称/标题 → 点「✨ AI 补全」→ 其余字段被填入（保留已填值），可改后保存
2.「剧情结构」tab 新增幕/节点同样有「✨ AI 补全」
3. 工坊页 `/workshop` 新增弹窗**没有**该按钮
4. （可选）断网或清空 API Key 时点补全 → 显示「AI 补全失败，请手动填写」，不影响手动保存

- [ ] **Step 6: Commit**

```bash
git add web/components/board/SettingsBoard.tsx web/components/board/PlotMasterDetail.tsx web/app/games/[id]/settings/page.tsx
git commit -m "feat(web): 设定页新增弹窗接入 AI 补全（工坊不启用）"
```

---

## Task 5: 记录 Round + prompt

**Files:**
- Modify: `docs/OPTIMIZATION_PLAN.md`

- [ ] **Step 1: 追加 Round 条目**

在 `docs/OPTIMIZATION_PLAN.md` §1 顶部（最新 Round 之前）追加 `### Round N (2026-06-05)`，照抄现有 Round 格式，概述：
- 新增 prompt `api/app/prompts/suggest_item.md`（新增设定 AI 补全系统提示，固定文本吃前缀缓存）
- 新增 `app/services/item_suggester.py`（`ItemSuggester`，`use_flash` + `SUGGEST_ITEM_TIMEOUT_SECONDS=40s` + 失败/超时/解析/漂移→空 dict fallback；`build_outline` 精简大纲省 token）
- 新端点 `POST /api/games/{id}/settings/suggest-item`
- 前端 `BlockDetailModal` 新增态「✨ AI 补全」按钮，仅游戏设定页注入 `onSuggestItem`，工坊不启用
- 设计/计划：`docs/superpowers/specs|plans/2026-06-05-ai-suggest-item*`

（N = 当前最大 Round 号 + 1，不改历史 Round。）

- [ ] **Step 2: Commit**

```bash
git add docs/OPTIMIZATION_PLAN.md
git commit -m "docs: OPTIMIZATION_PLAN 追加 Round N（新增设定 AI 补全）"
```

---

## 验收清单（全部任务完成后）

- [ ] 容器内 `pytest tests/test_item_suggester.py tests/test_games.py` 全绿
- [ ] `docker compose exec api ruff check .` 无错误
- [ ] `web`: `npm run test` / `npm run lint` / `npm run build` 全过
- [ ] 手动验证 4 项通过（含工坊无按钮、失败兜底）
- [ ] `docs/OPTIMIZATION_PLAN.md` 已追加本轮 Round
