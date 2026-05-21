"""Case file assembly from local project and task state."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from craik.contracts.models import (
    CaseFile,
    EvidenceReference,
    FactValue,
    ProjectProfile,
    TaskRequest,
)
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.github import GitHubReadAdapter
from craik.runtime.policy.intent_locks import IntentLockManager
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.policy.redaction import redact
from craik.runtime.projects.git_commands import run_git
from craik.runtime.projects.instruction_sources import (
    active_instruction_context,
    instruction_stale_risk_warnings,
)
from craik.runtime.store import LocalStore
from craik.runtime.work.case_support import (
    case_assumptions,
    context_budget,
    credential_context,
    governing_distillations,
    open_contradictions,
    verification_plan,
)
from craik.runtime.work.case_support import (
    stale_risks as case_stale_risks,
)
from craik.runtime.work.case_support.receipts import case_file_denial_receipt
from craik.runtime.work.known_traps import known_trap_summaries
from craik.runtime.work.scratchpad import unknown_summaries


class CaseFileError(RuntimeError):
    """Base error for case file assembly failures."""


class TaskNotFoundError(CaseFileError):
    """Raised when a task cannot be found."""


class ProjectNotFoundError(CaseFileError):
    """Raised when a task references an unknown project."""


class CaseFilePathTraversalError(CaseFileError):
    """Raised when configured discovery paths escape the repository root."""


DEFAULT_DISCOVERY_EXCLUDE = (
    ".git/**",
    ".hg/**",
    ".svn/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".tox/**",
    ".venv/**",
    "__pycache__/**",
    "build/**",
    "coverage/**",
    "dist/**",
    "generated/**",
    "archive/**",
    "docs/archive/**",
    "docs/build/**",
    "node_modules/**",
    "site/**",
    "vendor/**",
    "**/.git/**",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/__pycache__/**",
    "**/build/**",
    "**/coverage/**",
    "**/dist/**",
    "**/generated/**",
    "**/archive/**",
    "**/node_modules/**",
    "**/vendor/**",
)


class MemorySearch(Protocol):
    """Memory surface needed for case-file context loading."""

    def search(self, query: str) -> list[FactValue]:
        """Return facts relevant to a query."""


@dataclass(frozen=True)
class DiscoveryOverrides:
    """One-off user overrides for repository context discovery."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveredDocs:
    """Documentation discovered for a case file."""

    docs: list[str]
    adrs: list[str]
    omitted: list[str]
    excluded: list[dict[str, str]]
    rules: dict[str, list[str]]


@dataclass(frozen=True)
class CaseFileAssembler:
    """Build deterministic case files from local project and task contracts."""

    store: LocalStore
    github_adapter: GitHubReadAdapter | None = None
    memory: MemorySearch | None = None

    def build(
        self,
        task_id: str,
        *,
        max_tokens: int = 24000,
        discovery_overrides: DiscoveryOverrides | None = None,
    ) -> CaseFile:
        """Build and persist a case file for a task."""
        task = self.store.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(f"unknown task: {task_id}")
        project = self.store.get_project(task.project_id)
        if project is None:
            raise ProjectNotFoundError(f"unknown project for task {task_id}: {task.project_id}")

        repo_root = Path(project.repo.local_path)
        policy = generate_policy_envelope(task_id=task.id, actor="agent:case-file")
        try:
            discovered = _discover_docs(
                project,
                repo_root,
                max_tokens=max_tokens,
                overrides=discovery_overrides or DiscoveryOverrides(),
            )
        except CaseFilePathTraversalError as exc:
            self.store.put_receipt(
                case_file_denial_receipt(task=task, policy_id=policy.id, reason=str(exc))
            )
            raise
        repo_state = _repo_state(project, repo_root)
        github_state = _github_state(self.github_adapter, project, repo_state)
        evidence = _evidence(task, project, discovered.docs, discovered.adrs, repo_state)
        facts = _memory_facts(self.memory, task)
        recent_handoffs = _recent_handoffs(self.store, task.id)
        contradictions = open_contradictions(self.store, task.id, project.id)
        assumptions = case_assumptions(
            task,
            project,
            discovered.docs,
            discovered.omitted,
            github_state,
            facts,
        )
        credential_evidence, credential_risks = credential_context(
            AuthProfileStore(self.store.database_path.parent.parent),
            task,
        )
        evidence.extend(credential_evidence)
        stale_risks = [
            *case_stale_risks(repo_state, discovered.docs, assumptions),
            *instruction_stale_risk_warnings(self.store, project.id),
            *known_trap_summaries(self.store, project.id),
            *unknown_summaries(self.store, task.id),
            *credential_risks,
        ]
        active_instructions = active_instruction_context(self.store, project.id)
        distillations = governing_distillations(self.store, project.id)
        intent_lock = IntentLockManager(self.store).ensure_for_task(task)
        case_file = CaseFile(
            id=f"case_{task.id.removeprefix('task_')}",
            task_id=task.id,
            objective=task.objective,
            policy_envelope_id=policy.id,
            intent_lock_id=intent_lock.id,
            facts=facts,
            evidence=evidence,
            assumptions=assumptions,
            docs=discovered.docs,
            adrs=discovered.adrs,
            repo_state=repo_state,
            github_state=github_state,
            recent_handoffs=recent_handoffs,
            stale_risks=stale_risks,
            contradictions=contradictions,
            distillations=distillations,
            verification_plan=verification_plan(task),
            context_budget=context_budget(
                max_tokens=max_tokens,
                docs=discovered.docs,
                adrs=discovered.adrs,
                omitted_docs=discovered.omitted,
                excluded_docs=discovered.excluded,
                discovery_rules=discovered.rules,
                evidence=evidence,
                assumptions=assumptions,
                active_instruction_constraints=active_instructions,
                distillations=distillations,
                memory_fact_count=len(facts),
                recent_handoffs=recent_handoffs,
                contradiction_ids=[item.id for item in contradictions],
            ),
        )
        self.store.put_case_file(case_file)
        return case_file

    def get(self, case_file_id: str) -> CaseFile | None:
        """Load one persisted case file."""
        return self.store.get_case_file(case_file_id)

    def latest_for_task(self, task_id: str) -> CaseFile | None:
        """Return the stable case file for a task when present."""
        return self.store.get_case_file(f"case_{task_id.removeprefix('task_')}")


def _discover_docs(
    project: ProjectProfile,
    repo_root: Path,
    *,
    max_tokens: int,
    overrides: DiscoveryOverrides,
) -> DiscoveredDocs:
    docs: list[str] = []
    adrs: list[str] = []
    omitted: list[str] = []
    excluded: dict[str, str] = {}
    budget_chars = max_tokens * 4
    used_chars = 0
    immutable_prefixes = tuple(_normalize_path(path) for path in project.docs.immutable_paths)
    rules = _discovery_rules(project, overrides)

    for configured in sorted(project.docs.paths):
        path = repo_root / configured
        candidates = _doc_candidates(repo_root, path, rules=rules, excluded=excluded)
        for candidate in candidates:
            relative = _relative(repo_root, candidate)
            reason = _exclusion_reason(relative, rules)
            if reason is not None:
                excluded.setdefault(relative, reason)
                continue
            size = candidate.stat().st_size
            if used_chars + size > budget_chars:
                omitted.append(relative)
                continue
            used_chars += size
            if _is_immutable(relative, immutable_prefixes):
                adrs.append(relative)
            else:
                docs.append(relative)

    return DiscoveredDocs(
        docs=sorted(set(docs)),
        adrs=sorted(set(adrs)),
        omitted=sorted(set(omitted)),
        excluded=[
            {"path": path, "reason": reason}
            for path, reason in sorted(excluded.items(), key=lambda item: item[0])
        ],
        rules={
            "default_exclude": list(DEFAULT_DISCOVERY_EXCLUDE),
            "project_include": list(project.docs.discovery_include),
            "project_exclude": list(project.docs.discovery_exclude),
            "user_include": list(overrides.include),
            "user_exclude": list(overrides.exclude),
        },
    )


def _discovery_rules(
    project: ProjectProfile,
    overrides: DiscoveryOverrides,
) -> dict[str, tuple[str, ...]]:
    return {
        "include": tuple(
            _normalize_path(pattern)
            for pattern in (*project.docs.discovery_include, *overrides.include)
        ),
        "exclude": tuple(
            _normalize_path(pattern)
            for pattern in (
                *DEFAULT_DISCOVERY_EXCLUDE,
                *project.docs.discovery_exclude,
                *overrides.exclude,
            )
        ),
    }


def _doc_candidates(
    repo_root: Path,
    path: Path,
    *,
    rules: dict[str, tuple[str, ...]],
    excluded: dict[str, str],
) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    candidates: list[Path] = []
    include_rules = rules["include"]
    for root, dirs, files in os.walk(path):
        current = Path(root)
        if not include_rules:
            kept_dirs: list[str] = []
            for dirname in dirs:
                directory = current / dirname
                relative = _relative(repo_root, directory)
                reason = _exclusion_reason(f"{relative}/", rules)
                if reason is None:
                    kept_dirs.append(dirname)
                else:
                    excluded.setdefault(relative, reason)
            dirs[:] = kept_dirs
        for filename in files:
            candidate = current / filename
            if candidate.suffix.lower() in {".md", ".mdx", ".txt"}:
                candidates.append(candidate)
    return sorted(candidates)


def _exclusion_reason(path: str, rules: dict[str, tuple[str, ...]]) -> str | None:
    normalized = _normalize_path(path)
    if _matches_any(normalized, rules["include"]):
        return None
    for pattern in rules["exclude"]:
        if _path_matches(pattern, normalized):
            return f"excluded by discovery rule: {pattern}"
    return None


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(_path_matches(pattern, path) for pattern in patterns)


def _path_matches(pattern: str, path: str) -> bool:
    normalized_pattern = _normalize_path(pattern)
    normalized_path = _normalize_path(path)
    if fnmatch.fnmatchcase(normalized_path, normalized_pattern):
        return True
    if normalized_pattern.startswith("**/") and normalized_pattern.endswith("/**"):
        directory = normalized_pattern.removeprefix("**/").removesuffix("/**")
        return (
            normalized_path == directory
            or normalized_path.endswith(f"/{directory}")
            or f"/{directory}/" in normalized_path
        )
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern.removesuffix("/**")
        return normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
    return False


def _repo_state(project: ProjectProfile, repo_root: Path) -> dict[str, Any]:
    status = _git(repo_root, "status", "--short")
    branch = _git(repo_root, "branch", "--show-current")
    rev = _git(repo_root, "rev-parse", "--short", "HEAD")
    return {
        "branch": redact(branch.stdout.strip() or "detached").value,
        "default_branch": project.repo.default_branch,
        "dirty": bool(status.stdout.strip()),
        "head": redact(rev.stdout.strip() or "unknown").value,
        "immutable_paths": list(project.docs.immutable_paths),
        "repo": redact(project.repo.remote or project.repo.local_path).value,
        "status": "clean" if not status.stdout.strip() else "dirty",
    }


def _github_state(
    adapter: GitHubReadAdapter | None,
    project: ProjectProfile,
    repo_state: dict[str, Any],
) -> dict[str, Any]:
    if adapter is None:
        return {"status": "not_loaded"}
    return adapter.case_file_state(
        remote=project.repo.remote,
        ref=str(repo_state["head"]),
    )


def _evidence(
    task: TaskRequest,
    project: ProjectProfile,
    docs: list[str],
    adrs: list[str],
    repo_state: dict[str, Any],
) -> list[EvidenceReference]:
    evidence = [
        EvidenceReference(
            id=f"evidence_{task.id}_task",
            source="local_store",
            kind="other",
            locator=task.id,
            summary="Task request loaded from local store.",
        ),
        EvidenceReference(
            id=f"evidence_{task.id}_project",
            source="local_store",
            kind="other",
            locator=project.id,
            summary="Project profile loaded from local store.",
        ),
        EvidenceReference(
            id=f"evidence_{task.id}_repo_status",
            source="git",
            kind="command",
            locator="git status --short",
            summary=f"Repository status is {repo_state['status']}.",
            metadata={"branch": repo_state["branch"], "dirty": repo_state["dirty"]},
        ),
    ]
    for path in docs:
        evidence.append(_file_evidence(task.id, path, immutable=False))
    for path in adrs:
        evidence.append(_file_evidence(task.id, path, immutable=True))
    return evidence


def _file_evidence(task_id: str, path: str, *, immutable: bool) -> EvidenceReference:
    return EvidenceReference(
        id=f"evidence_{task_id}_{_slug(path)}",
        source=path,
        kind="file",
        locator=path,
        summary="Immutable documentation source." if immutable else "Documentation source.",
        metadata={"immutable": immutable},
    )


def _memory_facts(memory: MemorySearch | None, task: TaskRequest) -> list[FactValue]:
    if memory is None:
        return []
    query = " ".join([task.title, task.objective, *task.constraints, *task.expected_outputs])
    return sorted(memory.search(query), key=lambda fact: (fact.entity, fact.relation, fact.source))


def _recent_handoffs(store: LocalStore, task_id: str, limit: int = 5) -> list[str]:
    handoffs = [
        handoff
        for handoff in store.list_handoffs()
        if handoff.task_id == task_id or handoff.status in {"completed", "incomplete"}
    ]
    return [
        f"{handoff.id}: {handoff.status}: {handoff.summary}"
        for handoff in sorted(handoffs, key=lambda item: item.created_at, reverse=True)[:limit]
    ]


def _is_immutable(path: str, immutable_prefixes: tuple[str, ...]) -> bool:
    normalized = _normalize_path(path)
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(f"{prefix.rstrip('/')}/")
        for prefix in immutable_prefixes
    )


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise CaseFilePathTraversalError(
            "case-file discovery path escapes repository root"
        ) from exc


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_git(cwd, *args)
