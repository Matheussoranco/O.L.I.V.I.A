"""Small durable storage helpers used by the local JSON stores."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON beside ``path`` and replace it only after a complete write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def quarantine_corrupt_file(path: Path) -> Path | None:
    """Preserve an unreadable JSON file before a deliberate replacement."""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    path.rename(backup)
    return backup
