"""Persistent agent launch demo workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from craik.runtime.agents import (
    agent_session_id,
    execute_agent_prompt,
    get_agent_session_status,
    start_agent_session,
)
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.providers.provider_certification import provider_certification_matrix
from craik.runtime.store import LocalStore

DEMO_OPERATOR_SUBJECT = "operator:persistent-agent-demo"
DEMO_OPERATOR_ISSUER = "craik:demo"


@dataclass(frozen=True)
class PersistentAgentLaunchDemo:
    """Run a deterministic persistent-agent launch and prompt demo."""

    store: LocalStore

    def run(
        self,
        *,
        repo_path: Path,
        project_name: str = "Persistent Agent Demo",
        provider_ids: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Launch persistent sessions, prompt them, and return linked artifacts."""
        project = ProjectRegistry(self.store).add_project(repo_path, name=project_name)
        providers = provider_ids or (
            "provider_openai",
            "provider_anthropic",
            "provider_gemini",
            "provider_local_ollama",
        )
        started_at = datetime.now(UTC).replace(microsecond=0)
        executions = [
            self._run_provider(
                project_id=project.id,
                provider_id=provider_id,
                started_at=started_at,
            )
            for provider_id in providers
        ]
        return {
            "schema": "craik.demo.persistent_agent_launch",
            "version": "0.1.0",
            "mode": "fixture",
            "project": project.model_dump(mode="json", by_alias=True),
            "provider_ids": list(providers),
            "provider_executions": executions,
            "commands": _demo_commands(project.id, providers[0]),
        }

    def _run_provider(
        self,
        *,
        project_id: str,
        provider_id: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        session_id = agent_session_id(
            project_id=project_id,
            provider_id=provider_id,
            now=started_at,
        )
        launched = start_agent_session(
            self.store,
            session_id=session_id,
            project_id=project_id,
            operator_subject=DEMO_OPERATOR_SUBJECT,
            operator_issuer=DEMO_OPERATOR_ISSUER,
            provider_id=provider_id,
            mode="interactive",
            status="running",
            now=started_at,
        )
        prompt = execute_agent_prompt(
            self.store,
            session_id=session_id,
            operator_subject=DEMO_OPERATOR_SUBJECT,
            operator_issuer=DEMO_OPERATOR_ISSUER,
            prompt="Run the persistent agent launch demo prompt.",
            now=started_at,
        )
        status = get_agent_session_status(self.store, session_id)
        run_result = prompt.run_result
        if run_result is None:
            raise RuntimeError("persistent agent demo prompt did not create a run")
        return {
            "provider_id": provider_id,
            "session_id": session_id,
            "launch_status": launched.status,
            "status_inspection": status.model_dump(mode="json", by_alias=True),
            "prompt_exit_behavior": prompt.exit_behavior,
            "task_id": prompt.task_id,
            "run_id": run_result.run.id,
            "run_status": run_result.run.status,
            "handoff_id": run_result.handoff.id,
            "handoff_status": run_result.handoff.status,
            "receipt_ids": sorted(run_result.run.receipt_ids),
            "provider_result_count": len(run_result.provider_results),
            "provider_setup": _provider_matrix_row(provider_id),
            "next_commands": [
                f"craik agent status {session_id}",
                f"craik run inspect {run_result.run.id} --include-outputs",
                f"craik handoff show {run_result.handoff.id}",
            ],
        }


def _provider_matrix_row(provider_id: str) -> dict[str, Any]:
    for row in provider_certification_matrix().rows:
        if row.provider_id == provider_id:
            return row.model_dump(mode="json", by_alias=True)
    raise ValueError(f"provider is not in the certification matrix: {provider_id}")


def _demo_commands(project_id: str, provider_id: str) -> list[str]:
    return [
        "craik auth setup --provider openai --profile demo-openai",
        "craik auth setup --provider anthropic --profile demo-anthropic",
        "craik auth setup --provider gemini --profile demo-gemini",
        "craik provider local-presets",
        (
            "craik agent launch "
            f"--project-id {project_id} "
            f"--provider-id {provider_id} "
            "--session-id agent_demo"
        ),
        'craik agent prompt agent_demo "Run the persistent agent launch demo prompt."',
        "craik agent status agent_demo",
    ]
