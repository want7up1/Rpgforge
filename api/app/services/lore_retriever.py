from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.lore import LoreEntry
from app.models.mode import Mode
from app.models.turn import Turn
from app.services.story_blueprint import story_blueprint_search_fragments
from app.services.text_vectorizer import cosine_similarity, extract_terms, text_to_vector

MAX_CONTENT_TERM_SCORE = 3.0
MIN_KEYWORD_SCORE = 2.0
MIN_VECTOR_SCORE_WITHOUT_KEYWORD = 0.5
MIN_KEYWORD_SCORE_FOR_VECTOR = 0.8
STATE_LIST_LIMIT = 8
RECENT_GM_SNIPPET_LIMIT = 240

GENERIC_TERMS = {
    "gm",
    "一个",
    "一种",
    "一些",
    "作为",
    "以及",
    "可以",
    "需要",
    "正在",
    "继续",
    "开始",
    "进入",
    "发现",
    "任务",
    "线索",
    "主线",
    "剧情",
    "状态",
    "地点",
    "人物",
    "角色",
    "能力",
    "风险",
    "方向",
    "时候",
    "周围",
    "附近",
    "内部",
    "外部",
    "已经",
    "仍然",
    "没有",
    "必须",
    "保持",
    "目标",
    "系统",
    "当前",
    "回合",
    "行动",
    "选择",
    "玩家",
    "可见",
    "隐藏",
    "信息",
    "情况",
    "位置",
    "区域",
    "应该",
    "不要",
    "重要",
}

ACTIVE_NPC_MARKERS = (
    "在场",
    "同行",
    "同伴",
    "队伍",
    "跟随",
    "陪同",
    "身边",
    "交谈",
    "对峙",
    "战斗",
    "受伤",
    "昏迷",
    "保护",
    "等待",
)


@dataclass(frozen=True)
class LoreRetrievalResult:
    entry: LoreEntry
    score: float
    keyword_score: float
    vector_score: float
    matched_terms: list[str]


class LoreRetriever:
    def retrieve(
        self,
        *,
        db: Session,
        game: Game,
        player_input: str,
        selected_mode: Mode | None,
        recent_turns: list[Turn],
        limit: int = 8,
    ) -> list[LoreRetrievalResult]:
        query_text = self._build_query_text(game, player_input, selected_mode, recent_turns)
        query_terms = set(self._meaningful_terms(query_text))
        anchor_terms = set(self._state_anchor_terms(game.state.state_json if game.state else {}))
        query_text_lower = query_text.lower()
        query_vector = text_to_vector(query_text)
        entries = [
            entry
            for entry in game.lore_entries
            if not entry.always_on and getattr(entry, "is_active", True)
        ]

        active_entries = [entry for entry in game.lore_entries if getattr(entry, "is_active", True)]
        self.ensure_lore_embeddings(db, active_entries)
        vector_scores = self._pgvector_scores(db, game.id, query_vector, limit=max(limit * 4, 12))

        results: list[LoreRetrievalResult] = []
        for entry in entries:
            keyword_score, matched_terms = self._keyword_score(
                entry,
                query_terms,
                query_text_lower,
                anchor_terms,
            )
            vector_score = vector_scores.get(entry.id)
            if vector_score is None:
                vector_score = max(0.0, cosine_similarity(query_vector, entry.embedding))
            score = keyword_score + vector_score * 2.0 + self._priority_bonus(entry)

            has_keyword_signal = keyword_score >= MIN_KEYWORD_SCORE
            has_vector_signal = (
                vector_score >= MIN_VECTOR_SCORE_WITHOUT_KEYWORD
                and keyword_score >= MIN_KEYWORD_SCORE_FOR_VECTOR
            )
            if has_keyword_signal or has_vector_signal:
                results.append(
                    LoreRetrievalResult(
                        entry=entry,
                        score=round(score, 4),
                        keyword_score=round(keyword_score, 4),
                        vector_score=round(vector_score, 4),
                        matched_terms=matched_terms[:12],
                    )
                )

        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def ensure_lore_embeddings(self, db: Session, entries: list[LoreEntry]) -> None:
        changed = False
        for entry in entries:
            if entry.embedding is not None:
                continue
            vector = text_to_vector(self._entry_search_text(entry))
            if vector is None:
                continue
            entry.embedding = vector
            db.add(entry)
            changed = True
        if changed:
            db.flush()

    def rebuild_lore_embeddings(self, db: Session, entries: list[LoreEntry]) -> int:
        updated = 0
        for entry in entries:
            vector = text_to_vector(self._entry_search_text(entry))
            if vector is None:
                continue
            entry.embedding = vector
            db.add(entry)
            updated += 1
        if updated:
            db.commit()
        return updated

    def _pgvector_scores(
        self,
        db: Session,
        game_id: UUID,
        query_vector: list[float] | None,
        *,
        limit: int,
    ) -> dict[UUID, float]:
        if query_vector is None:
            return {}

        distance = LoreEntry.embedding.cosine_distance(query_vector)
        rows = db.execute(
            select(LoreEntry.id, distance.label("distance"))
            .where(
                LoreEntry.game_id == game_id,
                LoreEntry.embedding.is_not(None),
                LoreEntry.always_on.is_(False),
                LoreEntry.is_active.is_(True),
            )
            .order_by(distance.asc())
            .limit(limit)
        ).all()
        scores: dict[UUID, float] = {}
        for row in rows:
            if row.distance is None:
                continue
            scores[row.id] = max(0.0, 1.0 - float(row.distance))
        return scores

    def _build_query_text(
        self,
        game: Game,
        player_input: str,
        selected_mode: Mode | None,
        recent_turns: list[Turn],
    ) -> str:
        parts = [player_input, game.title, game.genre or "", game.description or ""]
        if selected_mode is not None:
            parts.extend([selected_mode.name, selected_mode.injection, *selected_mode.triggers])
        if game.state is not None:
            parts.extend(self._state_query_fragments(game.state.state_json))
        parts.extend(story_blueprint_search_fragments(game.config))
        for turn in recent_turns[-3:]:
            parts.extend(
                [
                    turn.player_input,
                    turn.visible_summary or "",
                    turn.gm_output[:RECENT_GM_SNIPPET_LIMIT],
                ]
            )
        return "\n".join(part for part in parts if part)

    def _keyword_score(
        self,
        entry: LoreEntry,
        query_terms: set[str],
        query_text_lower: str,
        anchor_terms: set[str],
    ) -> tuple[float, list[str]]:
        if not query_terms and not anchor_terms:
            return 0.0, []

        keywords = {term.lower() for term in entry.keywords if term}
        triggers = {term.lower() for term in entry.trigger_words if term}
        title_lower = entry.title.lower()
        title_terms = set(self._meaningful_terms(entry.title))
        content_terms = set(self._meaningful_terms(self._entry_search_text(entry)))

        score = 0.0
        matched: set[str] = set()

        for term in triggers:
            if self._term_hits(term, query_text_lower, query_terms):
                score += 4.0
                matched.add(term)

        for term in keywords:
            if self._term_hits(term, query_text_lower, query_terms):
                score += 3.0
                matched.add(term)

        if title_lower and title_lower in query_text_lower:
            score += 4.0
            matched.add(title_lower)
        for term in query_terms & title_terms:
            score += 2.0
            matched.add(term)

        for term in anchor_terms:
            if (
                term
                and (
                    term == title_lower
                    or term in title_terms
                    or term in keywords
                    or term in triggers
                )
            ):
                score += 5.0
                matched.add(term)

        content_matches = sorted(
            term
            for term in (query_terms & content_terms) - matched
            if self._is_content_match_term(term)
        )
        if content_matches:
            score += min(MAX_CONTENT_TERM_SCORE, len(content_matches) * 0.45)
            matched.update(content_matches[:8])

        return score, sorted(matched)

    @staticmethod
    def _entry_search_text(entry: LoreEntry) -> str:
        return "\n".join(
            part
            for part in [
                entry.title,
                entry.type or "",
                " ".join(entry.keywords),
                " ".join(entry.trigger_words),
                entry.public_info or "",
                entry.gm_secret or "",
                entry.content,
                entry.usage_note or "",
            ]
            if part
        )

    @staticmethod
    def _priority_bonus(entry: LoreEntry) -> float:
        return {
            "critical": 1.2,
            "high": 0.8,
            "medium": 0.4,
            "low": 0.1,
        }.get(entry.priority or "medium", 0.4)

    def _state_query_fragments(self, state: Any) -> list[str]:
        if not isinstance(state, dict):
            return []

        fragments: list[str] = []
        current_location = self._location_name(state.get("location"))
        if current_location:
            fragments.append(current_location)

        location = state.get("location")
        if isinstance(location, dict):
            fragments.extend(self._string_values(location, ("pressure", "threat", "current")))

        protagonist = state.get("protagonist")
        if isinstance(protagonist, dict):
            fragments.extend(
                self._string_values(
                    protagonist,
                    ("name", "identity", "status", "body", "mind"),
                )
            )

        fragments.extend(self._active_quest_fragments(state.get("quests")))
        fragments.extend(self._active_npc_fragments(state.get("npcs"), current_location))
        fragments.extend(self._recent_string_fragments(state.get("known_facts")))
        fragments.extend(self._recent_string_fragments(state.get("open_threads")))
        return fragments

    def _state_anchor_terms(self, state: Any) -> list[str]:
        if not isinstance(state, dict):
            return []

        fragments = self._state_query_fragments(state)

        terms: list[str] = []
        for fragment in fragments:
            terms.extend(self._meaningful_terms(fragment))
        return sorted(set(terms))

    def _active_quest_fragments(self, quests: Any) -> list[str]:
        if not isinstance(quests, list):
            return []

        fragments: list[str] = []
        for quest in quests[:STATE_LIST_LIMIT]:
            if not isinstance(quest, dict):
                continue
            status = str(quest.get("status") or quest.get("state") or "")
            if any(marker in status for marker in ("完成", "失败", "关闭", "解决")):
                continue
            fragments.extend(
                self._string_values(
                    quest,
                    ("name", "title", "status", "objective", "current", "description"),
                )
            )
        return fragments

    def _active_npc_fragments(self, npcs: Any, current_location: str | None) -> list[str]:
        if not isinstance(npcs, list):
            return []

        fragments: list[str] = []
        for npc in npcs[:STATE_LIST_LIMIT]:
            if not isinstance(npc, dict):
                continue
            if self._npc_is_active(npc, current_location):
                fragments.extend(
                    self._string_values(
                        npc,
                        ("name", "identity", "status", "location", "relationship", "attitude"),
                    )
                )
        return fragments

    def _npc_is_active(self, npc: dict[str, Any], current_location: str | None) -> bool:
        if npc.get("active") is True or npc.get("present") is True:
            return True

        location = str(npc.get("location") or npc.get("current_location") or "")
        status = str(npc.get("status") or npc.get("state") or "")
        relation = str(npc.get("relationship") or npc.get("attitude") or "")
        haystack = f"{location}\n{status}\n{relation}"
        if current_location and current_location in haystack:
            return True
        return any(marker in haystack for marker in ACTIVE_NPC_MARKERS)

    @staticmethod
    def _location_name(location: Any) -> str | None:
        if isinstance(location, dict):
            value = location.get("current") or location.get("name")
            return str(value) if value else None
        if isinstance(location, str):
            return location
        return None

    @staticmethod
    def _string_values(source: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
        values: list[str] = []
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value if str(item or "").strip())
        return values

    @staticmethod
    def _recent_string_fragments(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        fragments = []
        for item in value[-STATE_LIST_LIMIT:]:
            if isinstance(item, str) and item.strip():
                fragments.append(item)
            elif isinstance(item, dict):
                fragments.extend(str(part) for part in item.values() if isinstance(part, str))
        return fragments

    def _meaningful_terms(self, text: str) -> list[str]:
        terms = []
        for term in extract_terms(text):
            if self._is_generic_term(term):
                continue
            terms.append(term.lower())
        return terms

    @staticmethod
    def _term_hits(term: str, query_text_lower: str, query_terms: set[str]) -> bool:
        if not term:
            return False
        return term in query_terms or term in query_text_lower

    @staticmethod
    def _is_generic_term(term: str) -> bool:
        term = term.strip().lower()
        if not term:
            return True
        if term in GENERIC_TERMS:
            return True
        if LoreRetriever._is_cjk_text(term):
            for generic in GENERIC_TERMS:
                if LoreRetriever._is_cjk_text(generic) and len(generic) >= 2 and generic in term:
                    return True
        if term.isdigit() and len(term) < 3:
            return True
        return False

    @staticmethod
    def _is_content_match_term(term: str) -> bool:
        if LoreRetriever._is_cjk_text(term):
            return len(term) >= 4
        return len(term) >= 4

    @staticmethod
    def _is_cjk_text(value: str) -> bool:
        return bool(value) and all("\u3400" <= char <= "\u9fff" for char in value)
