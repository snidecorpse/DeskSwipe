from __future__ import annotations

import base64
import mimetypes
import subprocess
from pathlib import Path

ICON_CACHE: dict[str, tuple[bytes, str]] = {}


def _svg_icon(label: str, bg: str, fg: str = "#102a43") -> bytes:
    safe_label = "".join(ch for ch in label.upper() if ch.isalnum())[:4] or "FILE"
    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect x="4" y="4" width="56" height="56" rx="14" fill="{bg}" stroke="#b8c7d6" stroke-width="2"/>
  <text x="32" y="38" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="700" fill="{fg}">{safe_label}</text>
</svg>
"""
    return svg.strip().encode("utf-8")


def _fallback_svg(name: str, kind: str, mime: str | None) -> bytes:
    if kind == "folder":
        return _svg_icon("DIR", "#fbe9d5", "#8a4b0e")

    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix:
        if suffix in {"png", "jpg", "jpeg", "gif", "bmp", "webp"}:
            return _svg_icon("IMG", "#d7f2ec", "#0f766e")
        if suffix in {"mp4", "mov", "mkv", "avi", "webm"}:
            return _svg_icon("VID", "#d9e9fb", "#12457b")
        if suffix in {"mp3", "wav", "aac", "flac"}:
            return _svg_icon("AUD", "#efe4fb", "#53389e")
        if suffix in {"pdf"}:
            return _svg_icon("PDF", "#ffd6d6", "#8a1a1a")
        if suffix in {"zip", "rar", "7z"}:
            return _svg_icon("ZIP", "#f5e8d8", "#6b4a1f")
        return _svg_icon(suffix[:3], "#eaf1fa")

    if mime:
        if mime.startswith("image/"):
            return _svg_icon("IMG", "#d7f2ec", "#0f766e")
        if mime.startswith("video/"):
            return _svg_icon("VID", "#d9e9fb", "#12457b")
        if mime.startswith("audio/"):
            return _svg_icon("AUD", "#efe4fb", "#53389e")
        if mime == "application/pdf":
            return _svg_icon("PDF", "#ffd6d6", "#8a1a1a")
    return _svg_icon("FILE", "#eaf1fa")


def _extract_system_icon_png(path: str) -> bytes | None:
    candidate = Path(path)
    if not candidate.exists():
        return None
    if candidate.is_dir():
        return None

    encoded = base64.b64encode(path.encode("utf-8")).decode("ascii")
    script = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName System.Drawing;"
        f"$p=[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{encoded}'));"
        "$i=[System.Drawing.Icon]::ExtractAssociatedIcon($p);"
        "if($null -eq $i){exit 3};"
        "$b=$i.ToBitmap();"
        "$m=New-Object System.IO.MemoryStream;"
        "$b.Save($m,[System.Drawing.Imaging.ImageFormat]::Png);"
        "[System.Convert]::ToBase64String($m.ToArray())"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    payload = result.stdout.strip()
    if not payload:
        return None
    try:
        return base64.b64decode(payload)
    except (ValueError, base64.binascii.Error):
        return None


def icon_bytes_for_item(path: str, name: str, kind: str, mime: str | None) -> tuple[bytes, str]:
    guessed_mime = mime or mimetypes.guess_type(path)[0]
    suffix = Path(name).suffix.lower()
    cache_key = f"{kind}:{suffix}:{guessed_mime or ''}"
    if cache_key in ICON_CACHE:
        return ICON_CACHE[cache_key]

    icon_png = _extract_system_icon_png(path)
    if icon_png:
        ICON_CACHE[cache_key] = (icon_png, "image/png")
        return ICON_CACHE[cache_key]

    fallback = _fallback_svg(name=name, kind=kind, mime=guessed_mime)
    ICON_CACHE[cache_key] = (fallback, "image/svg+xml")
    return ICON_CACHE[cache_key]
