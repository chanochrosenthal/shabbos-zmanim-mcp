"""Per-profile preferences that persist across sessions (a small JSON file).

A voice assistant user says "I live in Lakewood, we light 18 minutes before
sunset" once; every later question without a city uses it. In a multi-user
deployment the profile key would be the authenticated user's subject (for
Alexa+, the account-linked user id); locally it defaults to "default".
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any


class PrefStore:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path or os.environ.get("ZMANIM_MCP_STATE", Path.cwd() / "state" / "profiles.json"))
        self._lock = threading.Lock()

    @staticmethod
    def key(profile: str | None) -> str:
        p = (profile or "default").strip().lower()
        return re.sub(r"[^a-z0-9_.@-]", "_", p)[:64] or "default"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get(self, profile: str | None) -> dict[str, Any]:
        with self._lock:
            return dict(self._load().get(self.key(profile), {}))

    def update(self, profile: str | None, **values: Any) -> dict[str, Any]:
        with self._lock:
            data = self._load()
            cur = data.get(self.key(profile), {})
            for k, v in values.items():
                if v is not None:
                    cur[k] = v
            data[self.key(profile)] = cur
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
            return dict(cur)

    def delete(self, profile: str | None) -> bool:
        """Remove a profile's saved preferences. Returns True if something was deleted, False if the
        profile was not saved (a no-op; the file is left untouched)."""
        with self._lock:
            data = self._load()
            k = self.key(profile)
            if k not in data:
                return False
            del data[k]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
            return True
