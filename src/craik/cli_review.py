"""Review finding capture CLI commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from craik.cli import review_app
from craik.cli_operator_auth import operator_identity_or_fail
from craik.runtime.reviewing.critics import record_red_team_finding, record_runtime_critic_finding
from craik.runtime.store import LocalStore


@review_app.command("critic")
def review_critic(
    task_id: Annotated[str, typer.Argument(help="Task id.")],
    finding_type: Annotated[str, typer.Option("--finding-type", help="Critic finding type.")],
    summary: Annotated[str, typer.Option("--summary", help="Finding summary.")],
    rationale: Annotated[str, typer.Option("--rationale", help="Finding rationale.")],
    severity: Annotated[str, typer.Option("--severity", help="Finding severity.")] = "medium",
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    artifact: Annotated[
        list[str] | None,
        typer.Option("--artifact", help="Affected artifact. May be repeated."),
    ] = None,
    evidence_id: Annotated[
        list[str] | None,
        typer.Option("--evidence-id", help="Evidence id. May be repeated."),
    ] = None,
    proposed_action: Annotated[
        list[str] | None,
        typer.Option("--proposed-action", help="Proposed action. May be repeated."),
    ] = None,
) -> None:
    """Persist a reviewable runtime critic finding."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        finding = record_runtime_critic_finding(
            store,
            task_id=task_id,
            project_id=project_id,
            finding_type=finding_type,
            severity=severity,
            summary=summary,
            rationale=rationale,
            affected_artifacts=artifact,
            evidence_ids=evidence_id,
            proposed_actions=proposed_action,
        )
    finally:
        store.close()
    _print(finding)


@review_app.command("red-team")
def review_red_team(
    task_id: Annotated[str, typer.Argument(help="Task id.")],
    finding_type: Annotated[str, typer.Option("--finding-type", help="Red-team finding type.")],
    summary: Annotated[str, typer.Option("--summary", help="Finding summary.")],
    attack_path: Annotated[str, typer.Option("--attack-path", help="Attack path.")],
    severity: Annotated[str, typer.Option("--severity", help="Finding severity.")] = "high",
    project_id: Annotated[str | None, typer.Option("--project", help="Project id.")] = None,
    artifact: Annotated[
        list[str] | None,
        typer.Option("--artifact", help="Affected artifact. May be repeated."),
    ] = None,
    evidence_id: Annotated[
        list[str] | None,
        typer.Option("--evidence-id", help="Evidence id. May be repeated."),
    ] = None,
    proposed_action: Annotated[
        list[str] | None,
        typer.Option("--proposed-action", help="Proposed action. May be repeated."),
    ] = None,
    blocking: Annotated[
        bool,
        typer.Option("--blocking/--non-blocking", help="Whether this is a blocking finding."),
    ] = False,
) -> None:
    """Persist a reviewable red-team finding."""
    operator_identity_or_fail()
    store = LocalStore.from_env()
    try:
        store.initialize()
        finding = record_red_team_finding(
            store,
            task_id=task_id,
            project_id=project_id,
            finding_type=finding_type,
            severity=severity,
            summary=summary,
            attack_path=attack_path,
            affected_artifacts=artifact,
            evidence_ids=evidence_id,
            proposed_actions=proposed_action,
            blocking=blocking,
        )
    finally:
        store.close()
    _print(finding)


def _print(model: object) -> None:
    payload = model.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
