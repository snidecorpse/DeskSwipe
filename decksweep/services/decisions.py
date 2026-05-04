from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import sqlite3


EffectiveAction = Literal["keep", "delete", "unresolved"]
EffectiveSource = Literal["user", "parent_override", "unresolved"]


@dataclass(frozen=True)
class EffectiveDecision:
    action: EffectiveAction
    source: EffectiveSource
    from_item_id: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_parent_map(connection: sqlite3.Connection, session_id: str) -> dict[str, str | None]:
    rows = connection.execute(
        "SELECT id, parent_id FROM items WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    return {str(row["id"]): row["parent_id"] for row in rows}


def _load_explicit_map(connection: sqlite3.Connection, session_id: str) -> dict[str, str]:
    rows = connection.execute(
        "SELECT item_id, action FROM decisions WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    return {str(row["item_id"]): str(row["action"]) for row in rows}


def resolve_effective_map(
    connection: sqlite3.Connection,
    session_id: str,
    item_ids: list[str],
) -> dict[str, EffectiveDecision]:
    parent_map = _load_parent_map(connection, session_id)
    explicit_map = _load_explicit_map(connection, session_id)
    cache: dict[str, EffectiveDecision] = {}

    def resolve(item_id: str) -> EffectiveDecision:
        if item_id in cache:
            return cache[item_id]

        parent_id = parent_map.get(item_id)
        if parent_id:
            parent_decision = resolve(parent_id)
            if parent_decision.action != "unresolved":
                resolved = EffectiveDecision(
                    action=parent_decision.action,
                    source="parent_override",
                    from_item_id=parent_decision.from_item_id,
                )
                cache[item_id] = resolved
                return resolved

        own_action = explicit_map.get(item_id)
        if own_action:
            resolved = EffectiveDecision(
                action=own_action, source="user", from_item_id=item_id
            )
            cache[item_id] = resolved
            return resolved

        resolved = EffectiveDecision(
            action="unresolved", source="unresolved", from_item_id=None
        )
        cache[item_id] = resolved
        return resolved

    return {item_id: resolve(item_id) for item_id in item_ids}


def get_effective_decision(
    connection: sqlite3.Connection, session_id: str, item_id: str
) -> EffectiveDecision:
    return resolve_effective_map(connection, session_id, [item_id])[item_id]


def set_explicit_decision(
    connection: sqlite3.Connection, session_id: str, item_id: str, action: str
) -> None:
    connection.execute(
        """
        INSERT INTO decisions (session_id, item_id, action, decided_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, item_id)
        DO UPDATE SET action = excluded.action, decided_at = excluded.decided_at
        """,
        (session_id, item_id, action, utc_now_iso()),
    )


def clear_explicit_decision(connection: sqlite3.Connection, session_id: str, item_id: str) -> None:
    connection.execute(
        "DELETE FROM decisions WHERE session_id = ? AND item_id = ?",
        (session_id, item_id),
    )


def update_scoring_for_decision(
    connection: sqlite3.Connection,
    session_id: str,
    action: str,
    size_bytes: int,
) -> None:
    session_row = connection.execute(
        "SELECT score, streak, max_streak FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not session_row:
        return

    score = int(session_row["score"])
    streak = int(session_row["streak"])
    max_streak = int(session_row["max_streak"])

    if action == "delete":
        streak += 1
        size_megabytes = size_bytes / (1024 * 1024)
        points = max(10, int(size_megabytes * 5) + streak * 2)
        score += points
        max_streak = max(max_streak, streak)
    else:
        score += 1
        streak = 0

    connection.execute(
        """
        UPDATE sessions
        SET score = ?, streak = ?, max_streak = ?, updated_at = ?
        WHERE id = ?
        """,
        (score, streak, max_streak, utc_now_iso(), session_id),
    )


def get_delete_target_ids(connection: sqlite3.Connection, session_id: str) -> list[str]:
    rows = connection.execute(
        "SELECT id, parent_id FROM items WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    item_ids = [str(row["id"]) for row in rows]
    if not item_ids:
        return []

    parent_map = {str(row["id"]): row["parent_id"] for row in rows}
    effective_map = resolve_effective_map(connection, session_id, item_ids)
    deleted_ids = {
        item_id
        for item_id, effective in effective_map.items()
        if effective.action == "delete"
    }
    targets: list[str] = []
    for item_id in deleted_ids:
        parent_id = parent_map.get(item_id)
        has_deleted_ancestor = False
        while parent_id:
            if parent_id in deleted_ids:
                has_deleted_ancestor = True
                break
            parent_id = parent_map.get(parent_id)
        if not has_deleted_ancestor:
            targets.append(item_id)
    return targets


def get_session_decision_totals(
    connection: sqlite3.Connection, session_id: str
) -> dict[str, int]:
    rows = connection.execute(
        "SELECT id FROM items WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    item_ids = [str(row["id"]) for row in rows]
    if not item_ids:
        return {"keep": 0, "delete": 0, "unresolved": 0}

    effective_map = resolve_effective_map(connection, session_id, item_ids)
    counts = {"keep": 0, "delete": 0, "unresolved": 0}
    for decision in effective_map.values():
        counts[decision.action] += 1
    return counts
