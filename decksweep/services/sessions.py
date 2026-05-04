from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlite3
from send2trash import send2trash

from decksweep.db import read_conn, write_conn
from decksweep.services.decisions import (
    clear_explicit_decision,
    get_delete_target_ids,
    get_effective_decision,
    resolve_effective_map,
    set_explicit_decision,
    update_scoring_for_decision,
)
from decksweep.services.scanner import build_root_deck_id

VALID_ORDER_MODES = {"random", "size_desc", "newest"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_root_path() -> str:
    return str(Path.home() / "Downloads")


def create_session(
    root_path: str | None, include_hidden: bool, order_mode: str
) -> tuple[str, str]:
    resolved_root = Path(root_path or default_root_path()).expanduser().resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        raise ValueError("Root path must be an existing folder.")

    if order_mode not in VALID_ORDER_MODES:
        raise ValueError("Unsupported order mode.")

    session_id = uuid.uuid4().hex
    root_deck_id = build_root_deck_id(session_id)
    created_at = utc_now_iso()

    with write_conn() as connection:
        connection.execute(
            """
            INSERT INTO sessions (
                id, root_path, include_hidden, order_mode, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                str(resolved_root),
                int(include_hidden),
                order_mode,
                "scanning",
                created_at,
                created_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO decks (id, session_id, parent_folder_item_id, name, total_cards)
            VALUES (?, ?, NULL, ?, 0)
            """,
            (root_deck_id, session_id, resolved_root.name or str(resolved_root)),
        )
    return session_id, root_deck_id


def get_latest_session() -> dict[str, Any] | None:
    with read_conn() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM sessions
            WHERE status IN ('scanning', 'ready')
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        return get_session_payload(str(row["id"]), connection=connection)


def get_session_payload(
    session_id: str, connection: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    owns_connection = connection is None
    if owns_connection:
        context = read_conn()
        connection = context.__enter__()
    try:
        session_row = connection.execute(
            """
            SELECT id, root_path, include_hidden, order_mode, status,
                   score, streak, max_streak, indexed_count, root_size_bytes,
                   created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if not session_row:
            return None

        root_deck_id = build_root_deck_id(session_id)
        reclaimed_estimate = get_reclaimable_bytes(connection, session_id)
        return {
            "session_id": str(session_row["id"]),
            "root_path": str(session_row["root_path"]),
            "root_deck_id": root_deck_id,
            "include_hidden": bool(session_row["include_hidden"]),
            "order_mode": str(session_row["order_mode"]),
            "status": str(session_row["status"]),
            "score": int(session_row["score"]),
            "streak": int(session_row["streak"]),
            "max_streak": int(session_row["max_streak"]),
            "indexed_count": int(session_row["indexed_count"]),
            "root_size_bytes": int(session_row["root_size_bytes"]),
            "reclaimed_estimate_bytes": reclaimed_estimate,
            "created_at": str(session_row["created_at"]),
            "updated_at": str(session_row["updated_at"]),
        }
    finally:
        if owns_connection:
            context.__exit__(None, None, None)


def _sort_clause(sort_mode: str) -> str:
    if sort_mode == "size_desc":
        return "size_bytes DESC, name COLLATE NOCASE ASC"
    if sort_mode == "newest":
        return "modified_at DESC, name COLLATE NOCASE ASC"
    return "random_rank ASC, name COLLATE NOCASE ASC"


def _item_rows_for_deck(
    connection: sqlite3.Connection, session_id: str, deck_id: str, sort_mode: str
) -> list[sqlite3.Row]:
    query = f"""
        SELECT id, path, name, kind, size_bytes, percent_of_root, mime,
               modified_at, created_at, accessed_at, deck_id, parent_id
        FROM items
        WHERE session_id = ? AND deck_id = ?
        ORDER BY {_sort_clause(sort_mode)}
    """
    return connection.execute(query, (session_id, deck_id)).fetchall()


def get_deck_page(
    session_id: str,
    deck_id: str,
    cursor: int,
    limit: int,
    sort_mode: str,
    unresolved_only: bool,
) -> dict[str, Any]:
    if sort_mode not in VALID_ORDER_MODES:
        sort_mode = "random"

    with read_conn() as connection:
        rows = _item_rows_for_deck(connection, session_id, deck_id, sort_mode)
        item_ids = [str(row["id"]) for row in rows]
        effective_map = resolve_effective_map(connection, session_id, item_ids) if item_ids else {}

        filtered_rows: list[sqlite3.Row] = []
        unresolved_count = 0
        for row in rows:
            item_id = str(row["id"])
            effective = effective_map[item_id]
            if effective.action == "unresolved":
                unresolved_count += 1
            if unresolved_only and effective.action != "unresolved":
                continue
            filtered_rows.append(row)

        total_filtered = len(filtered_rows)
        safe_cursor = max(0, min(cursor, total_filtered))
        page_rows = filtered_rows[safe_cursor : safe_cursor + limit]
        next_cursor = safe_cursor + limit if (safe_cursor + limit) < total_filtered else None

        cards: list[dict[str, Any]] = []
        for row in page_rows:
            item_id = str(row["id"])
            effective = effective_map[item_id]
            cards.append(
                {
                    "id": item_id,
                    "path": str(row["path"]),
                    "name": str(row["name"]),
                    "kind": str(row["kind"]),
                    "size_bytes": int(row["size_bytes"]),
                    "percent_of_root": float(row["percent_of_root"]),
                    "mime": row["mime"],
                    "modified_at": row["modified_at"],
                    "created_at": row["created_at"],
                    "accessed_at": row["accessed_at"],
                    "deck_id": str(row["deck_id"]),
                    "parent_id": row["parent_id"],
                    "effective_action": effective.action,
                    "effective_source": effective.source,
                    "effective_from_item_id": effective.from_item_id,
                }
            )

        deck_row = connection.execute(
            """
            SELECT parent_folder_item_id, total_cards
            FROM decks
            WHERE id = ? AND session_id = ?
            """,
            (deck_id, session_id),
        ).fetchone()
        if not deck_row:
            raise ValueError("Deck not found.")

        return {
            "session_id": session_id,
            "deck_id": deck_id,
            "cursor": safe_cursor,
            "next_cursor": next_cursor,
            "limit": limit,
            "sort_mode": sort_mode,
            "items": cards,
            "state": {
                "deck_id": deck_id,
                "parent_folder_item_id": deck_row["parent_folder_item_id"],
                "total_cards": int(deck_row["total_cards"]),
                "unresolved_count": unresolved_count,
            },
        }


def record_decision(session_id: str, item_id: str, action: str) -> dict[str, Any]:
    with write_conn() as connection:
        item_row = connection.execute(
            """
            SELECT id, kind, size_bytes
            FROM items
            WHERE session_id = ? AND id = ?
            """,
            (session_id, item_id),
        ).fetchone()
        if not item_row:
            raise ValueError("Item not found.")

        effective = get_effective_decision(connection, session_id, item_id)
        if effective.source == "parent_override":
            raise PermissionError("Item is locked by a parent folder decision.")

        set_explicit_decision(connection, session_id, item_id, action)
        update_scoring_for_decision(
            connection,
            session_id,
            action,
            int(item_row["size_bytes"]),
        )

    with read_conn() as connection:
        updated = get_effective_decision(connection, session_id, item_id)
        return {
            "item_id": item_id,
            "action": updated.action,
            "source": updated.source,
            "from_item_id": updated.from_item_id,
        }


def undo_decision(session_id: str, item_id: str) -> None:
    with write_conn() as connection:
        clear_explicit_decision(connection, session_id, item_id)
        connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (utc_now_iso(), session_id),
        )


def mark_folder_skipped(session_id: str, item_id: str) -> None:
    with write_conn() as connection:
        item_row = connection.execute(
            "SELECT kind FROM items WHERE session_id = ? AND id = ?",
            (session_id, item_id),
        ).fetchone()
        if not item_row:
            raise ValueError("Folder not found.")
        if str(item_row["kind"]) != "folder":
            raise ValueError("Only folders can be skipped.")

        connection.execute(
            """
            INSERT INTO skipped_folders (session_id, item_id, skipped_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id, item_id)
            DO UPDATE SET skipped_at = excluded.skipped_at
            """,
            (session_id, item_id, utc_now_iso()),
        )
        connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (utc_now_iso(), session_id),
        )


def get_reclaimable_bytes(connection: sqlite3.Connection, session_id: str) -> int:
    target_ids = get_delete_target_ids(connection, session_id)
    if not target_ids:
        return 0

    placeholders = ",".join("?" for _ in target_ids)
    params = [session_id, *target_ids]
    row = connection.execute(
        f"""
        SELECT COALESCE(SUM(size_bytes), 0) AS reclaimable
        FROM items
        WHERE session_id = ? AND id IN ({placeholders})
        """,
        params,
    ).fetchone()
    return int(row["reclaimable"]) if row else 0


def get_review_data(session_id: str) -> dict[str, Any]:
    with read_conn() as connection:
        rows = connection.execute(
            """
            SELECT id, name, path, kind, size_bytes
            FROM items
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchall()

        item_ids = [str(row["id"]) for row in rows]
        effective_map = resolve_effective_map(connection, session_id, item_ids) if item_ids else {}

        keep_items: list[dict[str, Any]] = []
        delete_items: list[dict[str, Any]] = []
        unresolved_count = 0

        for row in rows:
            item_id = str(row["id"])
            effective = effective_map[item_id]
            if effective.action == "unresolved":
                unresolved_count += 1
                continue

            review_item = {
                "id": item_id,
                "name": str(row["name"]),
                "path": str(row["path"]),
                "kind": str(row["kind"]),
                "size_bytes": int(row["size_bytes"]),
                "effective_action": effective.action,
                "effective_source": effective.source,
                "effective_from_item_id": effective.from_item_id,
            }
            if effective.action == "delete":
                delete_items.append(review_item)
            else:
                keep_items.append(review_item)

        reclaimable = get_reclaimable_bytes(connection, session_id)

        return {
            "session_id": session_id,
            "delete_count": len(delete_items),
            "keep_count": len(keep_items),
            "unresolved_count": unresolved_count,
            "reclaimable_bytes": reclaimable,
            "delete_items": sorted(delete_items, key=lambda item: item["size_bytes"], reverse=True),
            "keep_items": sorted(keep_items, key=lambda item: item["size_bytes"], reverse=True),
        }


def apply_delete_queue(session_id: str) -> dict[str, Any]:
    with write_conn() as connection:
        session_row = connection.execute(
            "SELECT status FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not session_row:
            raise ValueError("Session not found.")
        if str(session_row["status"]) == "applied":
            raise ValueError("Delete queue already applied.")

        target_ids = get_delete_target_ids(connection, session_id)
        if not target_ids:
            connection.execute(
                """
                UPDATE sessions
                SET status = ?, applied_at = ?, updated_at = ?
                WHERE id = ?
                """,
                ("applied", utc_now_iso(), utc_now_iso(), session_id),
            )
            return {
                "session_id": session_id,
                "queued_count": 0,
                "success_count": 0,
                "failed_items": [],
                "reclaimed_bytes": 0,
            }

        placeholders = ",".join("?" for _ in target_ids)
        target_rows = connection.execute(
            f"""
            SELECT id, path, size_bytes
            FROM items
            WHERE session_id = ? AND id IN ({placeholders})
            """,
            (session_id, *target_ids),
        ).fetchall()

        root_row = connection.execute(
            "SELECT root_path FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        root_path = Path(str(root_row["root_path"])).resolve()

        failed_items: list[str] = []
        success_count = 0
        reclaimed_bytes = 0

        for row in target_rows:
            target_path = Path(str(row["path"]))
            try:
                resolved_target = target_path.resolve()
                resolved_target.relative_to(root_path)
            except Exception:
                failed_items.append(str(target_path))
                continue

            if not target_path.exists():
                failed_items.append(str(target_path))
                continue

            try:
                send2trash(str(target_path))
                success_count += 1
                reclaimed_bytes += int(row["size_bytes"])
            except OSError:
                failed_items.append(str(target_path))

        connection.execute(
            """
            UPDATE sessions
            SET status = ?, applied_at = ?, updated_at = ?, streak = 0
            WHERE id = ?
            """,
            ("applied", utc_now_iso(), utc_now_iso(), session_id),
        )

        return {
            "session_id": session_id,
            "queued_count": len(target_rows),
            "success_count": success_count,
            "failed_items": failed_items,
            "reclaimed_bytes": reclaimed_bytes,
        }


def get_summary(session_id: str) -> dict[str, Any]:
    with read_conn() as connection:
        session_row = connection.execute(
            """
            SELECT score, max_streak, indexed_count
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if not session_row:
            raise ValueError("Session not found.")

        review = get_review_data(session_id)
        reclaimed_bytes = review["reclaimable_bytes"]
        target_ids = get_delete_target_ids(connection, session_id)
        top_reclaimed_items: list[dict[str, Any]] = []
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            target_rows = connection.execute(
                f"""
                SELECT id, name, path, kind, size_bytes
                FROM items
                WHERE session_id = ? AND id IN ({placeholders})
                ORDER BY size_bytes DESC
                LIMIT 5
                """,
                (session_id, *target_ids),
            ).fetchall()
            effective_map = resolve_effective_map(
                connection, session_id, [str(row["id"]) for row in target_rows]
            )
            for row in target_rows:
                item_id = str(row["id"])
                effective = effective_map[item_id]
                top_reclaimed_items.append(
                    {
                        "id": item_id,
                        "name": str(row["name"]),
                        "path": str(row["path"]),
                        "kind": str(row["kind"]),
                        "size_bytes": int(row["size_bytes"]),
                        "effective_action": effective.action,
                        "effective_source": effective.source,
                        "effective_from_item_id": effective.from_item_id,
                    }
                )

        badges: list[str] = []
        if reclaimed_bytes >= 1024 * 1024 * 1024:
            badges.append("Space Saver")
        if int(session_row["max_streak"]) >= 10:
            badges.append("Swipe Streaker")
        if review["delete_count"] >= 100:
            badges.append("Cleanup Crusher")
        if not badges:
            badges.append("Deck Rookie")

        return {
            "session_id": session_id,
            "score": int(session_row["score"]),
            "max_streak": int(session_row["max_streak"]),
            "total_indexed": int(session_row["indexed_count"]),
            "delete_count": review["delete_count"],
            "keep_count": review["keep_count"],
            "unresolved_count": review["unresolved_count"],
            "reclaimed_bytes": reclaimed_bytes,
            "badges": badges,
            "top_reclaimed_items": top_reclaimed_items,
        }


def get_file_web_data(session_id: str, limit: int = 72) -> dict[str, Any]:
    with read_conn() as connection:
        session_row = connection.execute(
            """
            SELECT status, indexed_count, root_size_bytes, root_path
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if not session_row:
            raise ValueError("Session not found.")

        root_path = Path(str(session_row["root_path"]))

        rows = connection.execute(
            """
            SELECT id, name, kind, size_bytes, parent_id, path
            FROM items
            WHERE session_id = ?
            ORDER BY size_bytes DESC, name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

        item_ids = [str(row["id"]) for row in rows]
        effective_map = resolve_effective_map(connection, session_id, item_ids) if item_ids else {}

        nodes: list[dict[str, Any]] = []
        counts = {"unresolved": 0, "keep": 0, "delete": 0}
        for row in rows:
            item_id = str(row["id"])
            effective = effective_map[item_id]
            counts[effective.action] += 1
            item_path = Path(str(row["path"]))
            try:
                relative_path = str(item_path.relative_to(root_path))
            except ValueError:
                relative_path = item_path.name
            depth = max(0, len(Path(relative_path).parts) - 1)
            nodes.append(
                {
                    "id": item_id,
                    "name": str(row["name"]),
                    "kind": str(row["kind"]),
                    "size_bytes": int(row["size_bytes"]),
                    "parent_id": row["parent_id"],
                    "effective_action": effective.action,
                    "relative_path": relative_path.replace("/", "\\"),
                    "depth": depth,
                }
            )

        return {
            "session_id": session_id,
            "status": str(session_row["status"]),
            "indexed_count": int(session_row["indexed_count"]),
            "root_size_bytes": int(session_row["root_size_bytes"]),
            "root_name": root_path.name or str(root_path),
            "root_path": str(root_path),
            "counts": counts,
            "nodes": nodes,
        }


def get_item_for_session(session_id: str, item_id: str) -> sqlite3.Row | None:
    with read_conn() as connection:
        return connection.execute(
            """
            SELECT id, session_id, path, name, kind, size_bytes, mime, deck_id, parent_id
            FROM items
            WHERE session_id = ? AND id = ?
            """,
            (session_id, item_id),
        ).fetchone()


def get_session_root(session_id: str) -> str | None:
    with read_conn() as connection:
        row = connection.execute(
            "SELECT root_path FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return str(row["root_path"]) if row else None
