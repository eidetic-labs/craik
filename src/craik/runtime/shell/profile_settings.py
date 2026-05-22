"""User profile/persona settings for the v0.10.0 shell UX."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from craik.runtime.paths import ensure_craik_home


@dataclass(frozen=True)
class CraikUserProfile:
    """One local profile/persona boundary."""

    name: str
    description: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ProfileSettings:
    """Active profile plus known profile definitions."""

    active: str = "default"
    profiles: dict[str, CraikUserProfile] = field(
        default_factory=lambda: {"default": CraikUserProfile(name="default")}
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "active": self.active,
            "profiles": {key: value.as_dict() for key, value in self.profiles.items()},
        }


class ProfileSettingsStore:
    """File-backed user profile store."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ProfileSettingsStore:
        paths = ensure_craik_home(env)
        return cls(paths.config / "profiles.json")

    def load(self) -> ProfileSettings:
        if not self.path.exists():
            return ProfileSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        profiles: dict[str, CraikUserProfile] = {}
        raw_profiles = payload.get("profiles", {})
        if isinstance(raw_profiles, dict):
            for key, value in raw_profiles.items():
                if isinstance(value, dict):
                    profiles[str(key)] = CraikUserProfile(
                        name=str(value.get("name", key)),
                        description=str(value.get("description", "")),
                        metadata={
                            str(meta_key): str(meta_value)
                            for meta_key, meta_value in dict(value.get("metadata", {})).items()
                        },
                    )
        if "default" not in profiles:
            profiles["default"] = CraikUserProfile(name="default")
        active = payload.get("active", "default")
        return ProfileSettings(
            active=str(active) if str(active) in profiles else "default",
            profiles=profiles,
        )

    def save(self, settings: ProfileSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=".profiles.",
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
