"""Runtime critic and red-team finding helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from craik.contracts.models import RedTeamFinding, RuntimeCriticFinding
from craik.runtime.policy.redaction import redact
from craik.runtime.store import LocalStore


def record_runtime_critic_finding(
    store: LocalStore,
    *,
    task_id: str,
    finding_type: str,
    summary: str,
    rationale: str,
    project_id: str | None = None,
    run_id: str | None = None,
    handoff_id: str | None = None,
    critic_role_id: str | None = None,
    severity: str = "medium",
    affected_artifacts: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    proposed_actions: list[str] | None = None,
    now: datetime | None = None,
) -> RuntimeCriticFinding:
    """Persist a non-authoritative runtime critic finding."""
    created_at = now or datetime.now(UTC)
    finding = RuntimeCriticFinding(
        id=_finding_id("runtime_critic", task_id, summary, created_at),
        task_id=task_id,
        project_id=project_id,
        run_id=run_id,
        handoff_id=handoff_id,
        critic_role_id=critic_role_id,
        finding_type=finding_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        summary=_clean(summary),
        rationale=_clean(rationale),
        affected_artifacts=affected_artifacts or [],
        evidence_ids=evidence_ids or [],
        proposed_actions=[_clean(action) for action in proposed_actions or []],
        created_at=created_at,
    )
    store.put_runtime_critic_finding(finding)
    return finding


def record_red_team_finding(
    store: LocalStore,
    *,
    task_id: str,
    finding_type: str,
    summary: str,
    attack_path: str,
    project_id: str | None = None,
    run_id: str | None = None,
    handoff_id: str | None = None,
    red_team_role_id: str | None = None,
    severity: str = "high",
    affected_artifacts: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    proposed_actions: list[str] | None = None,
    blocking: bool = False,
    now: datetime | None = None,
) -> RedTeamFinding:
    """Persist a non-authoritative red-team finding."""
    created_at = now or datetime.now(UTC)
    finding = RedTeamFinding(
        id=_finding_id("red_team", task_id, summary, created_at),
        task_id=task_id,
        project_id=project_id,
        run_id=run_id,
        handoff_id=handoff_id,
        red_team_role_id=red_team_role_id,
        finding_type=finding_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        summary=_clean(summary),
        attack_path=_clean(attack_path),
        affected_artifacts=affected_artifacts or [],
        evidence_ids=evidence_ids or [],
        proposed_actions=[_clean(action) for action in proposed_actions or []],
        blocking=blocking,
        created_at=created_at,
    )
    store.put_red_team_finding(finding)
    return finding


def reviewable_critic_findings(
    store: LocalStore,
    *,
    task_id: str,
) -> list[RuntimeCriticFinding]:
    """Return non-authoritative critic findings that still need review."""
    return sorted(
        (
            finding
            for finding in store.list_runtime_critic_findings()
            if finding.task_id == task_id
            and finding.review_status == "reviewable"
            and not finding.authoritative
        ),
        key=lambda finding: (finding.severity, finding.id),
    )


def blocking_red_team_findings(
    store: LocalStore,
    *,
    task_id: str,
) -> list[RedTeamFinding]:
    """Return non-authoritative red-team blockers for a task."""
    return sorted(
        (
            finding
            for finding in store.list_red_team_findings()
            if finding.task_id == task_id
            and finding.blocking
            and finding.review_status == "reviewable"
            and not finding.authoritative
        ),
        key=lambda finding: (finding.severity, finding.id),
    )


def render_critic_finding_markdown(finding: RuntimeCriticFinding) -> str:
    """Render a deterministic Markdown critic finding."""
    lines = [
        f"# Runtime Critic Finding: {finding.id}",
        "",
        f"- Type: {finding.finding_type}",
        f"- Severity: {finding.severity}",
        f"- Review Status: {finding.review_status}",
        f"- Authoritative: {str(finding.authoritative).lower()}",
        "",
        "## Summary",
        "",
        finding.summary,
        "",
        "## Proposed Actions",
        "",
        *_bullets(finding.proposed_actions),
    ]
    return "\n".join(lines) + "\n"


def render_red_team_finding_markdown(finding: RedTeamFinding) -> str:
    """Render a deterministic Markdown red-team finding."""
    lines = [
        f"# Red-Team Finding: {finding.id}",
        "",
        f"- Type: {finding.finding_type}",
        f"- Severity: {finding.severity}",
        f"- Blocking: {str(finding.blocking).lower()}",
        f"- Review Status: {finding.review_status}",
        f"- Authoritative: {str(finding.authoritative).lower()}",
        "",
        "## Summary",
        "",
        finding.summary,
        "",
        "## Proposed Actions",
        "",
        *_bullets(finding.proposed_actions),
    ]
    return "\n".join(lines) + "\n"


def _bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _clean(value: str) -> str:
    redacted = redact(value).value
    return re.sub(r"\s+", " ", redacted).strip()


def _finding_id(prefix: str, task_id: str, text: str, created_at: datetime) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", _clean(text).lower()).strip("_")[:48] or "finding"
    return f"{prefix}_{task_id}_{slug}_{created_at.strftime('%Y%m%d%H%M%S%f')}"
