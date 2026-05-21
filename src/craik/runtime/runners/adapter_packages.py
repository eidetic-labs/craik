"""Runtime capture points for adapter package metadata."""

from __future__ import annotations

import json
from pathlib import Path

from craik.contracts.models import AdapterPackage
from craik.runtime.store import LocalStore


def install_adapter_package(store: LocalStore, manifest_path: Path) -> AdapterPackage:
    """Load and persist an adapter package contract from a JSON manifest."""
    package = AdapterPackage.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    store.put_adapter_package(package)
    return package
