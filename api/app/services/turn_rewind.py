"""C6 后悔药：把游戏回退到第 N 回合（截断式撤销）。

利用既有 event-sourcing：删除 turn_number > N 的回合（StateDelta 经 FK ondelete=CASCADE 一并删除），
再 rebuild_game_state 从 initial_state 重放剩余 delta —— 状态、危机条、压力时钟、结局标记全部
确定性重算。若回退跨过了结局（completed/defeated），把 game.status 复位为 active。

每回合本就持久化 = 天然自动存档；本模块提供"撤销上一回合 / 回退到第 N 回合"的出口。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_activity import touch_game
from app.services.state_rebuilder import rebuild_game_state
from app.services.timeline import TimelineConflict, advance_timeline, lock_game_timeline

_ENDED_STATUSES = {"completed", "defeated"}


def rewind_game_to_turn(db: Session, game: Game, target_turn_number: int) -> int:
    """删除 target_turn_number 之后的回合并重建状态，返回删除的回合数。"""
    target = max(0, int(target_turn_number))
    lock_game_timeline(db, game.id)
    if db.scalars(select(TurnJob).where(
        TurnJob.game_id == game.id,
        TurnJob.timeline_generation == game.timeline_generation,
        TurnJob.status.in_(("pending", "running")),
    ).limit(1)).first() is not None:
        raise TimelineConflict("本回合任务进行中，请等待完成后再回退。")
    doomed = list(
        db.scalars(
            select(Turn).where(Turn.game_id == game.id, Turn.turn_number > target)
        ).all()
    )
    if not doomed:
        return 0

    advance_timeline(db, game)
    for turn in doomed:
        db.delete(turn)
    # A chapter/narrative/long-term summary spanning the discarded future
    # cannot be shortened by relabelling its range; drop it and bootstrap
    # later from retained turns. Unknown legacy ranges are unsafe as well.
    summaries = db.scalars(select(Summary).where(Summary.game_id == game.id)).all()
    retained_long_term = []
    for summary in summaries:
        if summary.range_end_turn is None or summary.range_end_turn > target:
            db.delete(summary)
        elif summary.type == "long_term":
            retained_long_term.append(summary)
    if game.state is not None:
        latest = max(retained_long_term, key=lambda item: item.range_end_turn or 0, default=None)
        game.state.summary = latest.content if latest else ""
        db.add(game.state)
    db.flush()

    rebuild_game_state(db, game)
    # 回退跨过结局：复位为进行中，让玩家从该回合继续。
    if game.status in _ENDED_STATUSES:
        game.status = "active"
    touch_game(db, game.id)
    db.commit()
    return len(doomed)
