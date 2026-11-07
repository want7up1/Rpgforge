"""Small, isolated PostgreSQL/runtime benchmark for two separate source revisions.

Run this script in independent processes with PYTHONPATH set to the API root
under test. It reuses benchmark_state_rebuild.fixture, whose app imports then
resolve to that revision. Only the two named disposable databases are accepted.
All measurements exclude fixture/schema creation and one warm-up. No HTTP/model
request is permitted. SQL counts are SQLAlchemy cursor executions, not row counts.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import math
import os
import platform
import sys
import tracemalloc
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import httpx
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import selectinload, sessionmaker

ALLOWED_DATABASES = {"rpgforge_perf_before_test", "rpgforge_perf_after_test"}
TEST_SOCKET = "/private/tmp/rpgforge-refactor-pg"
HARD_MARKERS = ("基准硬约束：角色只知道亲眼见到的线索", "基准禁止：不得提前揭露终局答案")


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def source_digest(api_root) -> str:
    root = Path(api_root) / "app"
    return digest(
        {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*.py"))
        }
    )


def canonical(state):
    return {key: value for key, value in state.items() if key != "v2"}


def block_http(*_args, **_kwargs):
    raise AssertionError("HTTP/model calls are forbidden in this benchmark")


class NoModelExtractor:
    calls = 0

    async def extract(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Already-settled fixtures must not invoke a model")


def runtime(api_root):
    from benchmark_state_rebuild import fixture

    import app.models  # noqa: F401
    from app.db.session import Base
    from app.models.game import Game
    from app.models.progress_save import GameProgressSave
    from app.models.turn import Turn
    from app.services.gameplay import gameplay_game_query
    from app.services.progress_saves import create_progress_save, load_progress_save
    from app.services.prompt_builder import PromptBuilder
    from app.services.state_rebuilder import rebuild_game_state
    from app.services.state_settlement import StateSettlementService

    actual_root = Path(app.models.__file__).resolve().parents[2]
    if actual_root != Path(api_root).resolve():
        raise RuntimeError(f"Mixed source roots: loaded {actual_root}, expected {api_root}")
    return SimpleNamespace(
        Base=Base,
        Game=Game,
        GameProgressSave=GameProgressSave,
        Turn=Turn,
        gameplay_game_query=gameplay_game_query,
        create_progress_save=create_progress_save,
        load_progress_save=load_progress_save,
        PromptBuilder=PromptBuilder,
        rebuild_game_state=rebuild_game_state,
        StateSettlementService=StateSettlementService,
        fixture=fixture,
    )


def prepare_database(url, rt):
    if url.database not in ALLOWED_DATABASES or url.query.get("host") != TEST_SOCKET:
        raise ValueError("Only the explicitly named disposable databases/socket are allowed")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": url.database}
        )
        if not exists:
            # The identifier is from the exact allow-list above, not arbitrary input.
            connection.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
    admin.dispose()
    engine = create_engine(url, connect_args={"prepare_threshold": None})
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    rt.Base.metadata.drop_all(engine)
    rt.Base.metadata.create_all(engine)
    return engine


def make_fixture(rt, size):
    game, repository = rt.fixture(size, 1, 1)
    game.id = uuid5(NAMESPACE_URL, f"rpgforge-runtime-benchmark-game-{size}")
    game.config.story_settings["hard_rules"] = {
        "must_follow": [HARD_MARKERS[0]],
        "must_not": [HARD_MARKERS[1]],
    }
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for turn, delta in repository.history:
        number = turn.turn_number
        turn.id = uuid5(NAMESPACE_URL, f"rpgforge-runtime-benchmark-turn-{size}-{number}")
        turn.game_id = delta.game_id = game.id
        delta.turn_id = turn.id
        delta.id = uuid5(NAMESPACE_URL, f"rpgforge-runtime-benchmark-delta-{size}-{number}")
        turn.created_at = delta.created_at = delta.updated_at = now
        repetitions = 500 if number > size - 6 else 80
        turn.gm_output = (
            f"第{number}回开头。"
            + "雨声落在仓库门口，你检查已经封存的证据。" * repetitions
            + f"最后动作：把钥匙交给守门人。END_OF_TURN_{number:04d}"
        )
        turn.state_delta_json = deepcopy(delta.delta_json)
        turn.action_options_json = []
        delta.attempt_count = 0
    return game, repository


def measure(engine, operation):
    counts = Counter()

    def on_statement(_connection, _cursor, statement, _parameters, _context, _many):
        counts[statement.lstrip().split(None, 1)[0].upper()] += 1

    event.listen(engine, "before_cursor_execute", on_statement)
    started = perf_counter()
    try:
        result = operation()
    finally:
        elapsed = (perf_counter() - started) * 1000
        event.remove(engine, "before_cursor_execute", on_statement)
    return {"ms": elapsed, "sql": sum(counts.values()), "statements": dict(counts)}, result


def summarize(samples):
    return {
        "median_ms": round(median(item["ms"] for item in samples), 3),
        "median_sql": median(item["sql"] for item in samples),
        "samples": [{**item, "ms": round(item["ms"], 3)} for item in samples],
    }


def game_query(rt, game_id):
    return (
        select(rt.Game)
        .options(
            selectinload(rt.Game.config),
            selectinload(rt.Game.state),
            selectinload(rt.Game.summaries),
            selectinload(rt.Game.characters),
        )
        .where(rt.Game.id == game_id)
    )


def snapshot_metrics(saved):
    fields = (
        "state_json",
        "turns_json",
        "summaries_json",
        "state_deltas_json",
        "initial_state_json",
    )
    snapshots = {name: getattr(saved, name) for name in fields if hasattr(saved, name)}
    # Compare gameplay data; IDs/timestamps/derived v2 and newly added receipts
    # are metadata and are reported separately rather than silently conflated.
    turn_keys = (
        "turn_number",
        "player_input",
        "gm_output",
        "visible_summary",
        "hidden_summary",
        "state_delta_json",
        "action_options_json",
        "model_used",
    )
    delta_keys = ("turn_id", "status", "delta_json", "error_message", "attempt_count")
    common = {
        "state": canonical(saved.state_json),
        "current_turn": saved.state_current_turn,
        "summary": saved.state_summary,
        "turns": [{key: row.get(key) for key in turn_keys} for row in saved.turns_json],
        "deltas": sorted(
            [
                {key: row.get(key, 0 if key == "attempt_count" else None) for key in delta_keys}
                for row in saved.state_deltas_json
            ],
            key=lambda item: item["turn_id"],
        ),
    }
    return {
        "snapshot_json_bytes": len(encoded(snapshots)),
        "json_fields_bytes": {name: len(encoded(value)) for name, value in snapshots.items()},
        "canonical_payload_digest": digest(common),
        "snapshot_version": getattr(saved, "snapshot_version", 1),
        "added_metadata": [
            name
            for name in ("initial_state_json", "game_status", "config_hash")
            if hasattr(saved, name)
        ],
        "turns_with_receipt": sum(bool(row.get("settlement_receipt")) for row in saved.turns_json),
    }


def memory_rebuild(rt, size, repeats):
    samples, outputs = [], []
    for _ in range(repeats):
        game, repository = make_fixture(rt, size)
        gc.collect()
        tracemalloc.start()
        started = perf_counter()
        rt.rebuild_game_state(repository, game)
        elapsed = (perf_counter() - started) * 1000
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        outputs.append(digest(canonical(game.state.state_json)))
        samples.append({"ms": round(elapsed, 3), "peak_bytes": peak})
    return {
        "median_peak_bytes": median(item["peak_bytes"] for item in samples),
        "median_ms_with_tracing": round(median(item["ms"] for item in samples), 3),
        "samples": samples,
        "canonical_digest": outputs[-1],
        "stable_digest": len(set(outputs)) == 1,
        "scope": "rebuild only; fixture allocated before tracing; in-memory repository",
    }


def context_metrics(rt, session_factory, game_id):
    with session_factory() as db:
        game = db.scalars(rt.gameplay_game_query(game_id)).first()
        turns = list(
            reversed(
                db.scalars(
                    select(rt.Turn)
                    .where(rt.Turn.game_id == game_id)
                    .order_by(rt.Turn.turn_number.desc())
                    .limit(6)
                ).all()
            )
        )
        messages = rt.PromptBuilder().build_runtime_messages(
            game=game,
            player_input="我检查仓库门口。",
            selected_action_style=None,
            recent_turns=turns,
            summaries={},
            related_materials=[],
        )
        chars = sum(len(item["content"]) for item in messages)
        content_bytes = sum(len(item["content"].encode()) for item in messages)
        payload = json.loads(messages[-1]["content"])
        full_turns = [item for item in payload["recent_turns"] if "gm_output" in item]
        return {
            "messages_content_chars": chars,
            "messages_content_utf8_bytes": content_bytes,
            "serialized_messages_utf8_bytes": len(encoded(messages)),
            "rough_tokens_chars_div_2": math.ceil(chars / 2),
            "recent_prose_chars": sum(
                len(item.get("gm_output", item.get("gm_output_excerpt", "")))
                for item in payload["recent_turns"]
            ),
            "tails_retained_in_full_turns": [
                f"END_OF_TURN_{item['turn_number']:04d}" in item["gm_output"] for item in full_turns
            ],
            "hard_constraints_in_system": [
                marker in messages[0]["content"] for marker in HARD_MARKERS
            ],
        }


def run_case(rt, engine, size, repeats):
    rt.Base.metadata.drop_all(engine)
    rt.Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    game, repository = make_fixture(rt, size)
    with sessions() as db:
        db.add(game)
        for turn, delta in repository.history:
            db.add_all([turn, delta])
        db.commit()
        rt.rebuild_game_state(db, game)
        db.commit()
        expected = digest(canonical(game.state.state_json))
    game_id = game.id
    extractor = NoModelExtractor()

    def settled():
        with sessions() as db:
            current = db.scalars(rt.gameplay_game_query(game_id)).first()
            changed = asyncio.run(
                rt.StateSettlementService(extractor=extractor).ensure_settled(db, current)
            )
            db.commit() if changed else db.rollback()
            return changed

    def save():
        with sessions() as db:
            current = db.scalars(game_query(rt, game_id)).first()
            saved = rt.create_progress_save(db, current, name="Runtime benchmark")
            db.commit()
            return saved

    settled()  # Warm Python/driver/schema paths; keep measured calls steady-state.
    settled_samples = [measure(engine, settled) for _ in range(repeats)]
    save()  # Warm save path; never include setup in the timing.
    saved_samples = [measure(engine, save) for _ in range(repeats)]
    saved = saved_samples[-1][1]
    save_id, snapshot = saved.id, snapshot_metrics(saved)

    def load():
        with sessions() as db:
            current = db.scalars(game_query(rt, game_id)).first()
            saved = db.get(rt.GameProgressSave, save_id)
            rt.load_progress_save(db, current, saved)
            db.commit()
            return current.state.state_json

    load()
    load_samples = [measure(engine, load) for _ in range(repeats)]
    loaded_digests = [digest(canonical(item[1])) for item in load_samples]
    result = {
        "turns": size,
        "settled_prepare": {
            **summarize([item[0] for item in settled_samples]),
            "changed_returns": [item[1] for item in settled_samples],
            "model_calls": extractor.calls,
        },
        "save": {**summarize([item[0] for item in saved_samples]), **snapshot},
        "load": {
            **summarize([item[0] for item in load_samples]),
            "canonical_digest": loaded_digests[-1],
            "restored_canonical_matches": all(value == expected for value in loaded_digests),
        },
        "canonical_state_digest": expected,
        "rebuild_tracemalloc": memory_rebuild(rt, size, repeats),
        "context": context_metrics(rt, sessions, game_id),
    }
    if extractor.calls or not result["load"]["restored_canonical_matches"]:
        raise AssertionError("Fixture unexpectedly required inference or changed on restore")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-root", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--sizes", default="10,100,500")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(args.database_url)
    if url.database not in ALLOWED_DATABASES or url.query.get("host") != TEST_SOCKET:
        parser.error("database/socket is outside the disposable benchmark allow-list")
    sizes = [int(value) for value in args.sizes.split(",")]
    if any(size < 6 or size > 500 for size in sizes) or not 1 <= args.repeats <= 5:
        parser.error("only small fixtures (6..500 turns, 1..5 repeats) are allowed")
    os.environ["DATABASE_URL"] = args.database_url
    os.environ["DEEPSEEK_API_KEY"] = os.environ["MIMO_API_KEY"] = ""
    httpx.Client.send = block_http
    httpx.AsyncClient.send = block_http
    started_at = datetime.now(UTC).isoformat()
    source_before = source_digest(args.api_root)
    rt = runtime(args.api_root)
    engine = prepare_database(url, rt)
    try:
        cases = []
        for size in sizes:
            print(f"{args.label}: {size} turns", file=sys.stderr, flush=True)
            cases.append(run_case(rt, engine, size, args.repeats))
        if source_digest(args.api_root) != source_before:
            raise RuntimeError("API source changed while benchmarking; rerun the affected revision")
        output = {
            "label": args.label,
            "api_root": str(Path(args.api_root).resolve()),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database": url.database,
            "repeats": args.repeats,
            "source_digest": source_before,
            "started_at_utc": started_at,
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "method": {
                "sql": (
                    "cursor executions including game relationships + operation + commit; "
                    "fixture/schema/warm-up excluded"
                ),
                "clock": "perf_counter; warm process and local PostgreSQL; no HTTP or LLM",
                "tokens": (
                    "ceil(sum(message content characters)/2); rough estimate, not tokenizer usage"
                ),
                "snapshot_bytes": (
                    "compact UTF-8 JSON of JSONB snapshot fields; "
                    "not PostgreSQL compressed storage size"
                ),
                "input": (
                    "shared fixture, one act/one anchor; 6 long recent narratives, "
                    "identical deterministic IDs/facts/prose"
                ),
            },
            "cases": cases,
        }
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(str(args.output), flush=True)
    finally:
        rt.Base.metadata.drop_all(engine)
        engine.dispose()


if __name__ == "__main__":
    main()
