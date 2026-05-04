from __future__ import annotations

from decksweep.db import read_conn
from decksweep.services.scanner import build_root_deck_id, scan_session
from decksweep.services.sessions import create_session
from tests.utils import workspace_temp_dir


def write_bytes(path, size: int) -> None:
    path.write_bytes(b"x" * size)


def test_recursive_scan_computes_folder_and_root_sizes() -> None:
    with workspace_temp_dir("scan") as temp_root:
        root_file = temp_root / "root.bin"
        folder = temp_root / "nested"
        nested_file = folder / "child.bin"
        folder.mkdir()
        write_bytes(root_file, 10)
        write_bytes(nested_file, 20)

        session_id, root_deck_id = create_session(
            root_path=str(temp_root), include_hidden=False, order_mode="random"
        )
        scan_session(session_id)

        with read_conn() as connection:
            session_row = connection.execute(
                "SELECT status, root_size_bytes FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            assert session_row is not None
            assert str(session_row["status"]) == "ready"
            assert int(session_row["root_size_bytes"]) == 30

            item_rows = connection.execute(
                """
                SELECT name, kind, size_bytes, deck_id, percent_of_root
                FROM items
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchall()
            assert len(item_rows) == 3

            by_name = {str(row["name"]): row for row in item_rows}
            assert int(by_name["child.bin"]["size_bytes"]) == 20
            assert int(by_name["root.bin"]["size_bytes"]) == 10
            assert int(by_name["nested"]["size_bytes"]) == 20
            assert str(by_name["root.bin"]["deck_id"]) == root_deck_id
            assert str(by_name["nested"]["deck_id"]) == build_root_deck_id(session_id)

            nested_deck_id = connection.execute(
                """
                SELECT id
                FROM decks
                WHERE session_id = ? AND parent_folder_item_id = (
                    SELECT id FROM items WHERE session_id = ? AND name = 'nested'
                )
                """,
                (session_id, session_id),
            ).fetchone()
            assert nested_deck_id is not None

            root_percent = float(by_name["root.bin"]["percent_of_root"])
            nested_percent = float(by_name["nested"]["percent_of_root"])
            assert 33.0 <= root_percent <= 34.0
            assert 66.0 <= nested_percent <= 67.0
