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
from app.models.turn import Turn
from app.services.game_activity import touch_game
from app.services.state_rebuilder import rebuild_game_state

_ENDED_STATUSES = {"completed", "defeated"}


def rewind_game_to_turn(db: Session, game: Game, target_turn_number: int) -> int:
    """删除 target_turn_number 之后的回合并重建状态，返回删除的回合数。"""
    target = max(0, int(target_turn_number))
    doomed = list(
        db.scalars(
            select(Turn).where(Turn.game_id == game.id, Turn.turn_number > target)
        ).all()
    )
    if not doomed:
        return 0

    for turn in doomed:
        db.delete(turn)
    db.flush()

    rebuild_game_state(db, game)
    # 回退跨过结局：复位为进行中，让玩家从该回合继续。
    if game.status in _ENDED_STATUSES:
        game.status = "active"
    touch_game(db, game.id)
    db.commit()
    return len(doomed)
