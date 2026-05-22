"""Small persisted model selection settings for v0.10.0 UX."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from craik.runtime.paths import ensure_craik_home


@dataclass(frozen=True)
class ModelSettings:
    """Active model, aliases, and fallback order."""

    active_model: str | None = None
    aliases: dict[str, str] = field(default_factory=dict)
    fallbacks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "active_model": self.active_model,
            "aliases": self.aliases,
            "fallbacks": self.fallbacks,
        }


class ModelSettingsStore:
    """File-backed model settings scoped to the active Craik home."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ModelSettingsStore:
        paths = ensure_craik_home(env)
        return cls(paths.config / "model-settings.json")

    def load(self) -> ModelSettings:
        if not self.path.exists():
            return ModelSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        aliases = payload.get("aliases", {})
        fallbacks = payload.get("fallbacks", [])
        return ModelSettings(
            active_model=_string_or_none(payload.get("active_model")),
            aliases=aliases if isinstance(aliases, dict) else {},
            fallbacks=[str(item) for item in fallbacks] if isinstance(fallbacks, list) else [],
        )

    def save(self, settings: ModelSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=".model-settings.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(settings.as_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
