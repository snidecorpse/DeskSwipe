from __future__ import annotations

from decksweep.db import read_conn
from decksweep.services.decisions import get_effective_decision
from decksweep.services.scanner import scan_session
from decksweep.services.sessions import (
    get_review_data,
    record_decision,
    undo_decision,
    create_session,
)
from tests.utils import workspace_temp_dir


def test_parent_folder_decision_overrides_child_then_undo_restores() -> None:
    with workspace_temp_dir("decisions") as temp_root:
        folder = temp_root / "folder_a"
        child_file = folder / "child.txt"
        folder.mkdir()
        child_file.write_text("hello world", encoding="utf-8")

        session_id, _ = create_session(
            root_path=str(temp_root), include_hidden=False, order_mode="random"
        )
        scan_session(session_id)

        with read_conn() as connection:
            folder_row = connection.execute(
                "SELECT id FROM items WHERE session_id = ? AND name = 'folder_a'",
                (session_id,),
            ).fetchone()
            child_row = connection.execute(
                "SELECT id FROM items WHERE session_id = ? AND name = 'child.txt'",
                (session_id,),
            ).fetchone()
            assert folder_row is not None and child_row is not None
            folder_id = str(folder_row["id"])
            child_id = str(child_row["id"])

        record_decision(session_id, child_id, "keep")
        record_decision(session_id, folder_id, "delete")

        with read_conn() as connection:
            effective_child = get_effective_decision(connection, session_id, child_id)
            assert effective_child.action == "delete"
            assert effective_child.source == "parent_override"
            assert effective_child.from_item_id == folder_id

        undo_decision(session_id, folder_id)

        with read_conn() as connection:
            effective_child = get_effective_decision(connection, session_id, child_id)
            assert effective_child.action == "keep"
            assert effective_child.source == "user"
            assert effective_child.from_item_id == child_id


def test_review_counts_keep_delete_and_unresolved() -> None:
    with workspace_temp_dir("review") as temp_root:
        (temp_root / "a.txt").write_text("a", encoding="utf-8")
        (temp_root / "b.txt").write_text("bb", encoding="utf-8")
        (temp_root / "c.txt").write_text("ccc", encoding="utf-8")

        session_id, _ = create_session(
            root_path=str(temp_root), include_hidden=False, order_mode="random"
        )
        scan_session(session_id)

        with read_conn() as connection:
            rows = connection.execute(
                "SELECT id, name FROM items WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        ids_by_name = {str(row["name"]): str(row["id"]) for row in rows}
        record_decision(session_id, ids_by_name["a.txt"], "delete")
        record_decision(session_id, ids_by_name["b.txt"], "keep")

        review = get_review_data(session_id)
        assert review["delete_count"] == 1
        assert review["keep_count"] == 1
        assert review["unresolved_count"] == 1
