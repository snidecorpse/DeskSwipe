from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OrderMode = Literal["random", "size_desc", "newest"]
DecisionAction = Literal["keep", "delete"]


class StartSessionRequest(BaseModel):
    root_path: str | None = None
    include_hidden: bool = False
    order_mode: OrderMode = "random"


class SessionResponse(BaseModel):
    session_id: str
    root_path: str
    root_deck_id: str
    include_hidden: bool
    order_mode: OrderMode
    status: str
    score: int
    streak: int
    max_streak: int
    indexed_count: int
    root_size_bytes: int
    reclaimed_estimate_bytes: int
    created_at: str
    updated_at: str


class CardItem(BaseModel):
    id: str
    path: str
    name: str
    kind: Literal["file", "folder"]
    size_bytes: int
    percent_of_root: float
    mime: str | None
    modified_at: str | None
    created_at: str | None
    accessed_at: str | None
    deck_id: str
    parent_id: str | None
    effective_action: Literal["keep", "delete", "unresolved"]
    effective_source: Literal["user", "parent_override", "unresolved"]
    effective_from_item_id: str | None


class DeckState(BaseModel):
    deck_id: str
    parent_folder_item_id: str | None
    total_cards: int
    unresolved_count: int


class DeckResponse(BaseModel):
    session_id: str
    deck_id: str
    cursor: int
    next_cursor: int | None
    limit: int
    sort_mode: OrderMode
    items: list[CardItem]
    state: DeckState


class DecisionRequest(BaseModel):
    item_id: str
    action: DecisionAction


class EnterFolderRequest(BaseModel):
    item_id: str


class SkipFolderRequest(BaseModel):
    item_id: str


class UndoRequest(BaseModel):
    item_id: str


class ReviewItem(BaseModel):
    id: str
    name: str
    path: str
    kind: Literal["file", "folder"]
    size_bytes: int
    effective_action: Literal["keep", "delete"]
    effective_source: Literal["user", "parent_override"]
    effective_from_item_id: str


class ReviewResponse(BaseModel):
    session_id: str
    delete_count: int
    keep_count: int
    unresolved_count: int
    reclaimable_bytes: int
    delete_items: list[ReviewItem]
    keep_items: list[ReviewItem]


class PreviewResponse(BaseModel):
    item_id: str
    path: str
    kind: Literal["file", "folder"]
    preview_type: Literal["image", "video", "audio", "pdf", "text", "folder", "metadata"]
    mime: str | None
    size_bytes: int
    content_url: str | None = None
    text_snippet: str | None = None
    folder_children: list[str] = Field(default_factory=list)
    metadata_only_reason: str | None = None


class ApplyResult(BaseModel):
    session_id: str
    queued_count: int
    success_count: int
    failed_items: list[str]
    reclaimed_bytes: int


class SummaryResponse(BaseModel):
    session_id: str
    score: int
    max_streak: int
    total_indexed: int
    delete_count: int
    keep_count: int
    unresolved_count: int
    reclaimed_bytes: int
    badges: list[str]
    top_reclaimed_items: list[ReviewItem]
