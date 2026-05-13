from app.db.session import _connect_args_for_url


def test_psycopg_prepared_statements_are_disabled() -> None:
    assert _connect_args_for_url("postgresql+psycopg://rpg:rpg@postgres:5432/rpgforge") == {
        "prepare_threshold": None
    }


def test_non_psycopg_urls_keep_default_connect_args() -> None:
    assert _connect_args_for_url("sqlite:///tmp/rpgforge.db") == {}
