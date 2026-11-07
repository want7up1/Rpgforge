"""Deterministic CPU benchmark; no database, model calls, or project data writes.

Run this file with PYTHONPATH pointing at api/ from the revision under test.
The fake repository counts service reads/flushes, not PostgreSQL statements.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from statistics import median
from time import perf_counter
from uuid import uuid4

from app.models.game import Game, GameConfig
from app.models.state import GameState
from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services.state_rebuilder import rebuild_game_state


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class MemoryRepository:
    def __init__(self, history):
        self.history = history
        self.reads = 0
        self.flushes = 0

    def scalars(self, _statement):
        self.reads += 1
        return Rows([delta for _turn, delta in self.history])

    def execute(self, _statement):
        self.reads += 1
        return Rows(self.history)

    def add(self, _value):
        pass

    def flush(self):
        self.flushes += 1


def fixture(size: int, acts: int, anchors: int):
    game_id = uuid4()
    game = Game(id=game_id, title="Benchmark", description="", status="active")
    game.config = GameConfig(story_settings={
        "game_profile": {"title": "Benchmark"},
        "story_core": {"current_act": "act_1"},
        "act_plan": [
            {"id": f"act_{act}", "title": f"Act {act}", "completion_anchors": [
                {"id": f"required_{act}_{anchor}", "title": "Finish",
                 "completion_signal": "Finish"}
                for anchor in range(anchors)
            ]}
            for act in range(1, acts + 1)
        ],
    })
    seed = {"current_turn": 0, "story_progress": {"current_act": "act_1"}}
    game.state = GameState(
        current_turn=0, state_json=deepcopy(seed), initial_state_json=seed,
    )
    now = datetime.now(UTC)
    history = []
    for number in range(1, size + 1):
        turn = Turn(
            id=uuid4(), game_id=game_id, turn_number=number,
            player_input="Look around", gm_output="The scene continues.",
            visible_summary="A new fact.",
        )
        delta = StateDelta(
            id=uuid4(), game_id=game_id, turn_id=turn.id, turn=turn,
            status="approved", created_at=now,
            delta_json={"new_known_facts": [f"Fact {number}"]},
        )
        history.append((turn, delta))
    return game, MemoryRepository(history)


def run(size: int, repeats: int, acts: int, anchors: int) -> dict:
    times = []
    for _ in range(repeats):
        game, repository = fixture(size, acts, anchors)
        started = perf_counter()
        rebuild_game_state(repository, game)
        times.append(perf_counter() - started)
    game, repository = fixture(size, acts, anchors)
    profiler = cProfile.Profile()
    profiler.enable()
    rebuild_game_state(repository, game)
    profiler.disable()
    names = {"normalize_story_settings", "apply_state_delta", "rebuild_game_state"}
    calls = {
        entry.code.co_name: entry.callcount for entry in profiler.getstats()
        if not isinstance(entry.code, str) and entry.code.co_name in names
    }
    return {
        "turns": size, "story_acts": acts, "anchors_per_act": anchors,
        "median_ms": round(median(times) * 1000, 3),
        "calls": calls, "repository_reads": repository.reads,
        "flushes": repository.flushes,
        "facts": len(game.state.state_json.get("known_facts", [])),
        # v2 is a derived UI/GM projection which may gain fields independently.
        "canonical_digest": hashlib.sha256(json.dumps(
            {key: value for key, value in game.state.state_json.items() if key != "v2"},
            ensure_ascii=False, sort_keys=True,
        ).encode()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="10,100,500")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--acts", type=int, default=1)
    parser.add_argument("--anchors", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps([
        run(int(size), args.repeats, args.acts, args.anchors) for size in args.sizes.split(",")
    ], indent=2))
