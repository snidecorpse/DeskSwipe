from __future__ import annotations

import ctypes
import os
from pathlib import Path

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def get_file_attributes(path: str | Path) -> int | None:
    if os.name != "nt":
        return None

    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1:
        return None
    return int(attrs)


def is_reparse_point(attrs: int | None) -> bool:
    if attrs is None:
        return False
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def is_hidden(path: str | Path, attrs: int | None = None) -> bool:
    path_obj = Path(path)
    if os.name != "nt":
        return path_obj.name.startswith(".")
    return bool(attrs and (attrs & FILE_ATTRIBUTE_HIDDEN))


def is_system(attrs: int | None) -> bool:
    if attrs is None:
        return False
    return bool(attrs & FILE_ATTRIBUTE_SYSTEM)
