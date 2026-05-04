from __future__ import annotations

import mimetypes
from pathlib import Path

MAX_MEDIA_PREVIEW_BYTES = 150 * 1024 * 1024
MAX_TEXT_PREVIEW_BYTES = 2 * 1024 * 1024
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".log",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".html",
    ".xml",
    ".yaml",
    ".yml",
}


def classify_preview(path: str, kind: str, size_bytes: int, mime: str | None) -> str:
    if kind == "folder":
        return "folder"

    mime_value = mime or mimetypes.guess_type(path)[0]
    extension = Path(path).suffix.lower()

    if mime_value:
        if mime_value.startswith("image/") and size_bytes <= MAX_MEDIA_PREVIEW_BYTES:
            return "image"
        if mime_value.startswith("video/") and size_bytes <= MAX_MEDIA_PREVIEW_BYTES:
            return "video"
        if mime_value.startswith("audio/") and size_bytes <= MAX_MEDIA_PREVIEW_BYTES:
            return "audio"
        if mime_value == "application/pdf" and size_bytes <= MAX_MEDIA_PREVIEW_BYTES:
            return "pdf"
        if mime_value.startswith("text/") and size_bytes <= MAX_TEXT_PREVIEW_BYTES:
            return "text"

    if extension in TEXT_EXTENSIONS and size_bytes <= MAX_TEXT_PREVIEW_BYTES:
        return "text"

    return "metadata"


def read_text_snippet(path: str, max_chars: int = 4000) -> str:
    file_path = Path(path)
    if not file_path.exists():
        return ""
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read(max_chars)
            return content
    except OSError:
        return ""


def folder_preview_children(path: str, limit: int = 12) -> list[str]:
    folder_path = Path(path)
    if not folder_path.exists() or not folder_path.is_dir():
        return []

    names: list[str] = []
    try:
        for index, child in enumerate(sorted(folder_path.iterdir(), key=lambda p: p.name.lower())):
            if index >= limit:
                break
            names.append(child.name)
    except OSError:
        return []
    return names
