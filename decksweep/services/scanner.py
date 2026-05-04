from __future__ import annotations

import mimetypes
import os
import random
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from decksweep.db import read_conn, write_conn
from decksweep.services.windows_fs import (
    get_file_attributes,
    is_hidden,
    is_reparse_point,
    is_system,
)

BATCH_SIZE = 250
SCAN_THREADS: dict[str, threading.Thread] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_root_deck_id(session_id: str) -> str:
    return f"deck-root-{session_id}"


def build_deck_id(item_id: str) -> str:
    return f"deck-{item_id}"


def default_downloads_path() -> str:
    downloads = Path.home() / "Downloads"
    return str(downloads)


def start_scan_thread(session_id: str) -> None:
    thread = threading.Thread(target=scan_session, args=(session_id,), daemon=True)
    SCAN_THREADS[session_id] = thread
    thread.start()


def scan_session(session_id: str) -> None:
    try:
        with read_conn() as connection:
            session_row = connection.execute(
                """
                SELECT root_path, include_hidden
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        if not session_row:
            return

        root_path = str(session_row["root_path"])
        include_hidden = bool(session_row["include_hidden"])
        root_deck_id = build_root_deck_id(session_id)

        with write_conn() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO decks (id, session_id, parent_folder_item_id, name)
                VALUES (?, ?, NULL, ?)
                """,
                (root_deck_id, session_id, Path(root_path).name or root_path),
            )
            connection.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
                ("scanning", utc_now_iso(), session_id),
            )

        stack: list[tuple[str, str | None, str, int]] = [
            (root_path, None, root_deck_id, 0)
        ]
        item_batch: list[tuple] = []
        deck_batch: list[tuple] = []
        indexed_count = 0

        while stack:
            current_path, parent_item_id, deck_id, depth = stack.pop()
            try:
                with os.scandir(current_path) as iterator:
                    entries = list(iterator)
            except (PermissionError, FileNotFoundError, NotADirectoryError):
                continue

            entries.sort(key=lambda entry: entry.name.lower())

            for entry in entries:
                attrs = get_file_attributes(entry.path)
                if entry.is_symlink() or is_reparse_point(attrs):
                    continue

                hidden = is_hidden(entry.path, attrs)
                system = is_system(attrs)
                if not include_hidden and (hidden or system):
                    continue

                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                    stat_result = entry.stat(follow_symlinks=False)
                except (PermissionError, FileNotFoundError, OSError):
                    continue

                item_id = uuid.uuid4().hex
                mime, _ = mimetypes.guess_type(entry.path)
                item_kind = "folder" if is_directory else "file"
                item_size = 0 if is_directory else int(stat_result.st_size)
                modified_at = datetime.fromtimestamp(
                    stat_result.st_mtime, tz=timezone.utc
                ).isoformat()
                created_at = datetime.fromtimestamp(
                    stat_result.st_ctime, tz=timezone.utc
                ).isoformat()
                accessed_at = datetime.fromtimestamp(
                    stat_result.st_atime, tz=timezone.utc
                ).isoformat()

                item_batch.append(
                    (
                        item_id,
                        session_id,
                        entry.path,
                        entry.name,
                        item_kind,
                        deck_id,
                        parent_item_id,
                        depth,
                        item_size,
                        mime,
                        modified_at,
                        created_at,
                        accessed_at,
                        int(hidden),
                        int(system),
                        random.random(),
                    )
                )

                indexed_count += 1

                if is_directory:
                    child_deck_id = build_deck_id(item_id)
                    deck_batch.append(
                        (
                            child_deck_id,
                            session_id,
                            item_id,
                            entry.name,
                        )
                    )
                    stack.append((entry.path, item_id, child_deck_id, depth + 1))

                if len(item_batch) >= BATCH_SIZE:
                    _flush_batches(
                        session_id=session_id,
                        indexed_count=indexed_count,
                        item_batch=item_batch,
                        deck_batch=deck_batch,
                    )
                    item_batch = []
                    deck_batch = []

        if item_batch or deck_batch:
            _flush_batches(
                session_id=session_id,
                indexed_count=indexed_count,
                item_batch=item_batch,
                deck_batch=deck_batch,
            )

        _finalize_scan(session_id=session_id, root_deck_id=root_deck_id)
    except Exception:
        with write_conn() as connection:
            connection.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
                ("failed", utc_now_iso(), session_id),
            )


def _flush_batches(
    session_id: str,
    indexed_count: int,
    item_batch: list[tuple],
    deck_batch: list[tuple],
) -> None:
    with write_conn() as connection:
        if deck_batch:
            connection.executemany(
                """
                INSERT OR IGNORE INTO decks (id, session_id, parent_folder_item_id, name)
                VALUES (?, ?, ?, ?)
                """,
                deck_batch,
            )
        if item_batch:
            connection.executemany(
                """
                INSERT OR IGNORE INTO items (
                    id, session_id, path, name, kind, deck_id, parent_id, depth,
                    size_bytes, mime, modified_at, created_at, accessed_at,
                    is_hidden, is_system, random_rank
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item_batch,
            )
        connection.execute(
            "UPDATE sessions SET indexed_count = ?, updated_at = ? WHERE id = ?",
            (indexed_count, utc_now_iso(), session_id),
        )


def _finalize_scan(session_id: str, root_deck_id: str) -> None:
    with write_conn() as connection:
        rows = connection.execute(
            """
            SELECT id, parent_id, kind, size_bytes, deck_id, depth
            FROM items
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchall()

        children_by_parent: dict[str | None, list[str]] = defaultdict(list)
        size_by_item: dict[str, int] = {}
        depth_by_item: dict[str, int] = {}
        folder_ids: list[str] = []
        root_children: list[str] = []

        for row in rows:
            item_id = str(row["id"])
            parent_id = row["parent_id"]
            children_by_parent[parent_id].append(item_id)
            depth_by_item[item_id] = int(row["depth"])
            if str(row["kind"]) == "folder":
                size_by_item[item_id] = 0
                folder_ids.append(item_id)
            else:
                size_by_item[item_id] = int(row["size_bytes"])
            if str(row["deck_id"]) == root_deck_id:
                root_children.append(item_id)

        folder_ids.sort(key=lambda item_id: depth_by_item[item_id], reverse=True)
        for folder_id in folder_ids:
            child_ids = children_by_parent.get(folder_id, [])
            size_by_item[folder_id] = sum(size_by_item.get(child_id, 0) for child_id in child_ids)

        root_size = sum(size_by_item.get(item_id, 0) for item_id in root_children)

        if size_by_item:
            connection.executemany(
                "UPDATE items SET size_bytes = ? WHERE session_id = ? AND id = ?",
                [
                    (size_by_item[item_id], session_id, item_id)
                    for item_id in size_by_item
                ],
            )

            if root_size > 0:
                connection.executemany(
                    "UPDATE items SET percent_of_root = ? WHERE session_id = ? AND id = ?",
                    [
                        ((size_by_item[item_id] / root_size) * 100.0, session_id, item_id)
                        for item_id in size_by_item
                    ],
                )
            else:
                connection.execute(
                    "UPDATE items SET percent_of_root = 0 WHERE session_id = ?",
                    (session_id,),
                )

        connection.execute(
            "UPDATE decks SET total_cards = 0 WHERE session_id = ?",
            (session_id,),
        )
        deck_rows = connection.execute(
            """
            SELECT deck_id, COUNT(*) AS card_count
            FROM items
            WHERE session_id = ?
            GROUP BY deck_id
            """,
            (session_id,),
        ).fetchall()
        connection.executemany(
            """
            UPDATE decks
            SET total_cards = ?
            WHERE id = ? AND session_id = ?
            """,
            [(int(row["card_count"]), str(row["deck_id"]), session_id) for row in deck_rows],
        )

        connection.execute(
            """
            UPDATE sessions
            SET root_size_bytes = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (root_size, "ready", utc_now_iso(), session_id),
        )
