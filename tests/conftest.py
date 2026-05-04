from __future__ import annotations

import pytest

from decksweep.db import init_db, write_conn


@pytest.fixture(autouse=True)
def reset_database() -> None:
    init_db()
    with write_conn() as connection:
        connection.execute("DELETE FROM skipped_folders")
        connection.execute("DELETE FROM decisions")
        connection.execute("DELETE FROM items")
        connection.execute("DELETE FROM decks")
        connection.execute("DELETE FROM sessions")
