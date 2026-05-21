"""Policy-aware prompt compilation for runner adapters."""

from __future__ import annotations

from dataclasses import dataclass

from craik.contracts.models import (
    CapabilityGrant,
    CaseFile,
    CompiledPrompt,
    PolicyEnvelope,
    PromptSection,
    RunnerCapabilityMatrix,
    TaskRequest,
)
from craik.runtime.policy.policy import generate_policy_envelope
from craik.runtime.runners.runners import get_runner_capability_matrix
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.case_support import governing_distillations


class PromptCompilerError(RuntimeError):
    """Base error for prompt compiler failures."""


class PromptTaskNotFoundError(PromptCompilerError):
    """Raised when a task cannot be found."""


class PromptCaseFileNotFoundError(PromptCompilerError):
    """Raised when no case file exists for a task."""


@dataclass(frozen=True)
class PromptCompiler:
    """Compile deterministic runner prompts from Craik runtime state."""

    store: LocalStore

    def compile(
        self,
        task_id: str,
        *,
        runner_id: str,
        expected_output_schemas: list[str] | None = None,
    ) -> CompiledPrompt:
        """Compile a prompt for a task and runner."""
        task = self.store.get_task(task_id)
        if task is None:
            raise PromptTaskNotFoundError(f"unknown task: {task_id}")
        case_file = CaseFileAssembler(self.store).latest_for_task(task.id)
        if case_file is None:
            raise PromptCaseFileNotFoundError(f"no case file found for task: {task_id}")

        policy = self.store.get_policy_envelope(case_file.policy_envelope_id)
        if policy is None:
            policy = generate_policy_envelope(task_id=task.id, actor=f"runner:{runner_id}")
            self.store.put_policy_envelope(policy)

        runner_matrix = get_runner_capability_matrix(runner_id)
        grants = _grants_for_task(self.store.list_capability_grants(), task.id)
        stop_conditions = _stop_conditions(self.store, case_file)
        output_schemas = expected_output_schemas or [
            "craik.runner_adapter_result",
            "craik.handoff",
        ]
        context_omissions = _context_omissions(case_file)
        distillations = governing_distillations(self.store, task.project_id or "")
        distillation_warnings = _distillation_warnings(self.store, task.project_id)
        sections = _sections(
            task=task,
            case_file=case_file,
            policy=policy,
            grants=grants,
            runner_matrix=runner_matrix,
            expected_output_schemas=output_schemas,
            context_omissions=context_omissions,
            stop_conditions=stop_conditions,
            distillations=distillations,
            distillation_warnings=distillation_warnings,
        )
        prompt_text = _render_sections(sections)

        compiled = CompiledPrompt(
            id=f"prompt_{task.id.removeprefix('task_')}_{runner_id}",
            task_id=task.id,
            case_file_id=case_file.id,
            policy_envelope_id=policy.id,
            runner_id=runner_matrix.runner.id,
            runner_mode=runner_matrix.runner.mode,
            capability_grant_ids=[grant.id for grant in grants],
            expected_output_schemas=output_schemas,
            context_omissions=context_omissions,
            stop_conditions=stop_conditions,
            distillations=distillations,
            distillation_warnings=distillation_warnings,
            sections=sections,
            prompt=prompt_text,
        )
        self.store.put_compiled_prompt(compiled)
        return compiled


def _sections(
    *,
    task: TaskRequest,
    case_file: CaseFile,
    policy: PolicyEnvelope,
    grants: list[CapabilityGrant],
    runner_matrix: RunnerCapabilityMatrix,
    expected_output_schemas: list[str],
    context_omissions: list[str],
    stop_conditions: list[str],
    distillations: list[dict[str, object]],
    distillation_warnings: list[str],
) -> list[PromptSection]:
    return [
        PromptSection(
            title="Task",
            body="\n".join(
                [
                    f"Task id: {task.id}",
                    f"Title: {task.title}",
                    f"Objective: {task.objective}",
                    f"Mode: {task.mode}",
                    f"Priority: {task.priority}",
                    _bullet_block("Constraints", task.constraints),
                    _bullet_block("Expected outputs", task.expected_outputs),
                    _bullet_block("Stop conditions", stop_conditions),
                ]
            ),
        ),
        PromptSection(
            title="Runner",
            body="\n".join(
                [
                    f"Runner id: {runner_matrix.runner.id}",
                    f"Mode: {runner_matrix.runner.mode}",
                    f"Trust level: {runner_matrix.trust.level}",
                    f"Trust boundary: {runner_matrix.trust.boundary}",
                    f"Default grant posture: {runner_matrix.trust.default_grant_posture}",
                    f"Receipts required: {runner_matrix.trust.requires_receipts}",
                    f"Redaction required: {runner_matrix.trust.requires_redaction}",
                    _capability_block(runner_matrix),
                    _bullet_block("Runner policy notes", runner_matrix.policy_notes),
                ]
            ),
        ),
        PromptSection(
            title="Policy",
            body="\n".join(
                [
                    f"Policy id: {policy.id}",
                    f"Profile: {policy.profile}",
                    f"Fail open: {policy.fail_open}",
                    _bullet_block("Allowed capabilities", policy.allowed_capabilities),
                    _bullet_block("Denied capabilities", policy.denied_capabilities),
                    _bullet_block("Approval required", policy.approval_required),
                    _bullet_block("Verification required", policy.verification_required),
                    _grants_block(grants),
                ]
            ),
        ),
        PromptSection(
            title="Active instruction constraints",
            body=_distillation_block(distillations, distillation_warnings),
        ),
        PromptSection(
            title="Context",
            body="\n".join(
                [
                    f"Case file id: {case_file.id}",
                    f"Objective: {case_file.objective}",
                    _bullet_block("Docs", case_file.docs),
                    _bullet_block("Immutable docs / ADRs", case_file.adrs),
                    _bullet_block(
                        "Assumptions",
                        [item.statement for item in case_file.assumptions],
                    ),
                    _bullet_block("Stale risks", case_file.stale_risks),
                    _bullet_block(
                        "Open contradictions",
                        [item.summary for item in case_file.contradictions],
                    ),
                    _bullet_block("Context omissions", context_omissions),
                ]
            ),
        ),
        PromptSection(
            title="Output Contract",
            body="\n".join(
                [
                    _bullet_block("Expected output schemas", expected_output_schemas),
                    "Return normalized Craik contract-shaped output.",
                    "Do not treat assumptions, stale risks, or omitted context as facts.",
                    (
                        "Create memory proposals rather than direct durable writes unless "
                        "explicitly granted."
                    ),
                ]
            ),
        ),
    ]


def _render_sections(sections: list[PromptSection]) -> str:
    return "\n\n".join(f"## {section.title}\n{section.body}" for section in sections)


def _grants_for_task(grants: list[CapabilityGrant], task_id: str) -> list[CapabilityGrant]:
    return sorted(
        [grant for grant in grants if grant.task_id == task_id],
        key=lambda grant: grant.id,
    )


def _context_omissions(case_file: CaseFile) -> list[str]:
    omitted: list[str] = []
    for path in case_file.context_budget.get("docs_omitted", []):
        omitted.append(f"Document omitted by context budget: {path}")
    for item in case_file.context_budget.get("docs_excluded", []):
        if isinstance(item, dict):
            path = item.get("path", "unknown")
            reason = item.get("reason", "excluded")
            omitted.append(f"Document excluded from discovery: {path} ({reason})")
    if case_file.github_state.get("status") != "loaded":
        omitted.append("GitHub issue and pull request state was not loaded.")
    if not case_file.facts:
        omitted.append("Memory facts were not loaded into the case file.")
    return sorted(set(omitted))


def _distillation_warnings(store: LocalStore, project_id: str | None) -> list[str]:
    if project_id is None:
        return []
    warnings = []
    for proposal in store.list_distilled_instruction_proposals():
        if (
            proposal.project_id == project_id
            and proposal.promotion_status == "deferred"
            and proposal.promoted_constraint_id is not None
        ):
            warnings.append(
                f"Stale governing distillation excluded: {proposal.id} "
                f"from {proposal.source_id}"
            )
    return sorted(set(warnings))


def _stop_conditions(store: LocalStore, case_file: CaseFile) -> list[str]:
    if case_file.intent_lock_id:
        intent_lock = store.get_intent_lock(case_file.intent_lock_id)
        if intent_lock is not None and intent_lock.stop_conditions:
            return intent_lock.stop_conditions
    return [
        "Stop if requested work exceeds the intent lock or policy envelope.",
        "Stop before writing immutable paths without explicit approval metadata.",
        "Stop before using denied capabilities.",
    ]


def _capability_block(matrix: RunnerCapabilityMatrix) -> str:
    lines = ["Capabilities:"]
    for capability in sorted(matrix.capabilities, key=lambda item: item.name):
        grant = "grant required" if capability.grant_required else "no grant required"
        suffix = f" ({capability.notes})" if capability.notes else ""
        lines.append(f"- {capability.name}: {capability.support}; {grant}{suffix}")
    return "\n".join(lines)


def _distillation_block(
    distillations: list[dict[str, object]],
    warnings: list[str],
) -> str:
    lines = ["Items:"]
    if not distillations:
        lines.append("- none")
    current_category: str | None = None
    for item in sorted(distillations, key=_distillation_sort_key):
        category = str(item.get("category", "uncategorized"))
        if category != current_category:
            lines.append(f"- {category}:")
            current_category = category
        lines.append(f"  - {_render_distillation_item(item)}")
    lines.append("Warnings:")
    lines.extend(f"- {warning}" for warning in warnings or ["none"])
    return "\n".join(lines)


def _render_distillation_item(item: dict[str, object]) -> str:
    category = str(item.get("category", "uncategorized"))
    statement = str(item.get("statement", ""))
    source_id = str(item.get("source_id", "unknown_source"))
    provenance = item.get("provenance", [])
    locations = []
    if isinstance(provenance, list):
        for raw in provenance:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path", "unknown"))
            start_line = raw.get("start_line")
            end_line = raw.get("end_line")
            if start_line is None:
                locations.append(path)
            elif end_line is None:
                locations.append(f"{path}:{start_line}-{start_line}")
            else:
                locations.append(f"{path}:{start_line}-{end_line}")
    location_text = ", ".join(locations) if locations else "unknown"
    return f"({category}) {statement} [{source_id} @ {location_text}]"


def _distillation_sort_key(item: dict[str, object]) -> tuple[int, str, str]:
    category_order = {
        "policy": 0,
        "security_rule": 1,
        "boundary": 2,
        "command": 3,
        "instruction": 4,
        "handoff_rule": 5,
        "memory_rule": 6,
        "preference": 7,
        "stale_risk": 8,
    }
    category = str(item.get("category", "uncategorized"))
    return (
        category_order.get(category, 99),
        str(item.get("source_id", "")),
        str(item.get("statement", "")),
    )


def _grants_block(grants: list[CapabilityGrant]) -> str:
    if not grants:
        return "Capability grants:\n- none"
    lines = ["Capability grants:"]
    for grant in grants:
        target_paths = ", ".join(grant.target.paths) if grant.target.paths else "all targets"
        operations = ", ".join(grant.operations) if grant.operations else "no operations"
        lines.append(f"- {grant.id}: {grant.capability}; ops={operations}; target={target_paths}")
    return "\n".join(lines)


def _bullet_block(title: str, values: list[str]) -> str:
    if not values:
        return f"{title}:\n- none"
    return "\n".join([f"{title}:", *(f"- {value}" for value in values)])
