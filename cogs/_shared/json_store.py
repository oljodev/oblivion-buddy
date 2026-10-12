"""Shared JSON persistence helpers.

save_json() writes atomically: data goes to a temp file in the same folder,
is flushed to disk, and then replaces the real file in one step. A crash or
power cut mid-save leaves either the old or the new file — never half a file.

load_json() never silently throws data away: if a file exists but can't be
parsed, it is renamed to "<name>.corrupt-<timestamp>" (so it can be recovered
by hand) and an error is logged before the default is returned. Without this,
the next save would overwrite the broken-but-recoverable file with the default.
"""

import copy
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("JSONStore")


def load_json(path, default):
    """Load JSON from `path`, or return a copy of `default` if missing/corrupt."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        backup = path.with_name(
            f"{path.name}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        try:
            path.replace(backup)
            logger.error(
                f"Corrupt JSON in {path} ({e}). Moved it to {backup.name} and "
                "started from defaults — restore it by hand if needed."
            )
        except OSError as move_err:
            logger.error(f"Corrupt JSON in {path} ({e}); could not back it up: {move_err}")
        return copy.deepcopy(default)


def save_json(path, data, indent: int = 2):
    """Atomically write `data` as JSON to `path`. Raises on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
