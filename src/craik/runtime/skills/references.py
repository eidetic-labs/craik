"""Runtime capture points for v0.6 reference integration contracts."""

from __future__ import annotations

import json
from pathlib import Path

from craik.contracts.models import ReferenceIntegration
from craik.runtime.store import LocalStore


def install_reference_integration(store: LocalStore, manifest_path: Path) -> ReferenceIntegration:
    """Load and persist a reference integration contract from a JSON manifest."""
    integration = ReferenceIntegration.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    store.put_reference_integration(integration)
    return integration


def verify_reference_integration(
    store: LocalStore,
    integration_id: str,
) -> ReferenceIntegration:
    """Reload a reference integration and rely on model validation for safety gates."""
    integration = store.get_reference_integration(integration_id)
    if integration is None:
        raise ValueError(f"unknown reference integration: {integration_id}")
    return integration
