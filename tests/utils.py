from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def workspace_temp_dir(prefix: str):
    base = Path.cwd() / ".testdata"
    base.mkdir(exist_ok=True)
    folder = base / f"{prefix}_{uuid.uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)
