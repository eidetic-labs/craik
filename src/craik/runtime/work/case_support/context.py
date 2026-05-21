"""Context helpers for case-file assembly."""

from __future__ import annotations

from typing import Any

from craik.contracts.models import (
    Assumption,
    ContradictionReport,
    EvidenceReference,
    FactValue,
    ProjectProfile,
    TaskRequest,
)
from craik.runtime.store import LocalStore


def open_contradictions(
    store: LocalStore,
    task_id: str,
    project_id: str,
) -> list[ContradictionReport]:
    """Return open contradictions relevant to a task or project."""
    return sorted(
        [
            report
            for report in store.list_contradictions()
            if report.status == "open"
            and (report.task_id == task_id or getattr(report, "project_id", None) == project_id)
        ],
        key=lambda report: report.id,
    )


def case_assumptions(
    task: TaskRequest,
    project: ProjectProfile,
    docs: list[str],
    omitted_docs: list[str],
    github_state: dict[str, Any],
    facts: list[FactValue],
) -> list[Assumption]:
    """Build assumptions for missing memory, GitHub, docs, or context."""
    assumptions = []
    if not facts:
        assumptions.append(
            Assumption(
                id=f"assumption_{task.id}_memory_not_loaded",
                task_id=task.id,
                statement="No memory facts were loaded into this case file.",
                rationale=(
                    f"The configured memory backend is {project.memory.backend}, but no "
                    "queryable facts were available for this task."
                ),
                confidence=1.0,
                status="open",
            )
        )
    if github_state.get("status") != "loaded":
        assumptions.append(
            Assumption(
                id=f"assumption_{task.id}_github_not_loaded",
                task_id=task.id,
                statement="No GitHub issue or pull request state was loaded into this case file.",
                rationale=github_assumption_rationale(github_state),
                confidence=1.0,
                status="open",
            )
        )
    if not docs:
        assumptions.append(
            Assumption(
                id=f"assumption_{task.id}_docs_missing",
                task_id=task.id,
                statement="No mutable documentation files were discovered for this project.",
                rationale=(
                    "Configured documentation paths were missing or only contained immutable docs."
                ),
                confidence=0.9,
                status="open",
            )
        )
    if omitted_docs:
        assumptions.append(
            Assumption(
                id=f"assumption_{task.id}_context_omitted",
                task_id=task.id,
                statement="Some documentation was omitted from the case file context budget.",
                rationale="Configured docs exceeded the requested context budget.",
                confidence=1.0,
                status="open",
            )
        )
    return assumptions


def github_assumption_rationale(github_state: dict[str, Any]) -> str:
    """Explain why GitHub state is absent from a case file."""
    status = github_state.get("status")
    if status == "not_configured":
        return "Project remote is not configured as a GitHub repository."
    if status == "error":
        warnings = github_state.get("warnings")
        if isinstance(warnings, list) and warnings:
            return f"GitHub read adapter could not load state: {warnings[0]}"
        return "GitHub read adapter could not load state."
    return "GitHub read adapter was not configured for this case file build."


def stale_risks(
    repo_state: dict[str, Any],
    docs: list[str],
    assumptions: list[Assumption],
) -> list[str]:
    """Return generic stale-risk warnings for a case file."""
    risks: list[str] = []
    if docs:
        risks.append("Documentation may be stale relative to implementation and memory state.")
    if repo_state["dirty"]:
        risks.append("Repository has uncommitted changes that may affect case file accuracy.")
    if assumptions:
        risks.append("Case file contains open assumptions that require downstream review.")
    return risks


def verification_plan(task: TaskRequest) -> list[str]:
    """Return the default verification plan for a case file."""
    plan = ["Review case file assumptions before acting.", "Run repository-appropriate tests."]
    if task.mode in {"review", "verify"}:
        plan.insert(0, "Compare findings against cited evidence.")
    return plan


def context_budget(
    *,
    max_tokens: int,
    docs: list[str],
    adrs: list[str],
    omitted_docs: list[str],
    excluded_docs: list[dict[str, str]],
    discovery_rules: dict[str, list[str]],
    evidence: list[EvidenceReference],
    assumptions: list[Assumption],
    active_instruction_constraints: list[dict[str, object]],
    distillations: list[dict[str, Any]],
    memory_fact_count: int,
    recent_handoffs: list[str],
    contradiction_ids: list[str],
) -> dict[str, Any]:
    """Return context-budget metadata for a case file."""
    return {
        "max_tokens": max_tokens,
        "estimated_tokens": _estimate_tokens(docs + adrs),
        "docs_included": len(docs),
        "adrs_included": len(adrs),
        "docs_omitted": omitted_docs,
        "docs_excluded": excluded_docs,
        "discovery_rules": discovery_rules,
        "evidence_count": len(evidence),
        "assumption_count": len(assumptions),
        "active_instruction_constraints": active_instruction_constraints,
        "distillations": distillations or [],
        "memory_fact_count": memory_fact_count,
        "recent_handoffs": recent_handoffs,
        "contradiction_ids": contradiction_ids,
    }


def _estimate_tokens(paths: list[str]) -> int:
    return sum(max(1, len(path) // 4) for path in paths)
