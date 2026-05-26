"""Instruction distillation lifecycle CLI commands."""

from __future__ import annotations

from typing import Annotated, Any, NoReturn, get_args

import typer

from craik.cli import instructions_app
from craik.cli_output import emit_command_result
from craik.contracts.models import DistilledInstructionCategory, InstructionSourceKind
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.contract import CommandResult, PayloadShape, craik_command
from craik.runtime.instruction_approval import (
    InstructionApprovalError,
    approve_instruction,
    reject_instruction,
)
from craik.runtime.instruction_distillation import (
    InstructionDistillationError,
    ingest_project_instructions,
)
from craik.runtime.instructions import (
    InstructionRegistrationError,
    list_sources,
    register_source,
)
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore


@instructions_app.command("register")
@craik_command(payload_shape="card")
def instructions_register(
    kind: Annotated[str, typer.Argument(help="Instruction source kind.")],
    path: Annotated[str, typer.Argument(help="Path inside the project repository.")],
    project: Annotated[
        str | None,
        typer.Option("--project", help="Project id or name. Defaults when one project exists."),
    ] = None,
    owner: Annotated[
        str | None,
        typer.Option("--owner", help="Owning team or operator. Defaults to active operator."),
    ] = None,
) -> CommandResult:
    """Register an instruction source idempotently and print its receipt."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        project_id = _project_id(store, project)
        operator = _operator_identity()
        parsed_kind = _instruction_source_kind(kind)
        existing = _existing_source(store, project_id=project_id, kind=parsed_kind, path=path)
        if existing is not None:
            receipt = store.get_instruction_registry_receipt(
                f"instruction_registry_receipt_{existing.id}"
            )
            payload = {
                "registered": False,
                "source_id": existing.id,
                "receipt_id": receipt.id if receipt is not None else None,
            }
        else:
            try:
                result = register_source(
                    store,
                    project_id=project_id,
                    kind=parsed_kind,
                    path=path,
                    owner=owner or operator,
                    registered_by=operator,
                )
            except InstructionRegistrationError as error:
                _fail(str(error))
            payload = {
                "registered": True,
                "source_id": result.source.id,
                "receipt_id": result.receipt.id,
            }
    finally:
        store.close()
    return _emit_payload(payload, shape="card")


@instructions_app.command("ingest")
@craik_command(payload_shape="kv")
def instructions_ingest(
    project: Annotated[
        str | None,
        typer.Option("--project", help="Project id or name. Defaults when one project exists."),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json/--table", help="Print JSON instead of a table."),
    ] = False,
) -> CommandResult:
    """Ingest registered instruction sources into reviewable proposals."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        project_id = _project_id(store, project)
        _operator_identity()
        try:
            summary = ingest_project_instructions(store, project_id)
        except InstructionDistillationError as error:
            _fail(str(error))
        payload = {
            "project_id": summary.project_id,
            "source_count": summary.source_count,
            "snapshot_count": summary.snapshot_count,
            "provenance_count": summary.provenance_count,
            "proposal_count": summary.proposal_count,
            "invalidated_count": summary.invalidated_count,
            "contradiction_count": summary.contradiction_count,
            "skipped_existing_count": summary.skipped_existing_count,
            "unclassified_count": summary.unclassified_count,
            "warnings": summary.warnings,
        }
    finally:
        store.close()
    return _emit_payload(
        payload,
        shape="kv",
        text=None if as_json else _render_ingest_summary(payload),
    )


@instructions_app.command("list")
@craik_command(payload_shape="table")
def instructions_list(
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by proposed, governing, rejected, superseded, or stale.",
        ),
    ] = None,
    source_id: Annotated[
        str | None,
        typer.Option("--source", help="Filter by instruction source id."),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option("--category", help="Filter by distillation category."),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json/--table", help="Print JSON instead of a table."),
    ] = False,
) -> CommandResult:
    """List distilled instruction proposals."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        items = [_proposal_payload(store, proposal) for proposal in _filtered_proposals(
            store,
            status=status,
            source_id=source_id,
            category=category,
        )]
    finally:
        store.close()
    return _emit_payload(
        items,
        shape="table",
        text=None if as_json else _render_table(items),
    )


@instructions_app.command("approve")
@craik_command(payload_shape="card")
def instructions_approve(
    item_id: Annotated[str, typer.Argument(help="Distilled instruction proposal id.")],
    rationale: Annotated[
        str,
        typer.Option("--rationale", help="Approval rationale."),
    ] = "",
    override: Annotated[
        bool,
        typer.Option("--override", help="Approve a stale or contradicted item intentionally."),
    ] = False,
    override_rationale: Annotated[
        str | None,
        typer.Option("--override-rationale", help="Required rationale for override approval."),
    ] = None,
) -> CommandResult:
    """Approve a distilled instruction and make it governing."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        try:
            result = approve_instruction(
                store,
                proposal_id=item_id,
                operator_identity=_operator_identity(),
                rationale=rationale or "Approved from CLI.",
                override=override,
                override_rationale=override_rationale or rationale or None,
            )
        except InstructionApprovalError as error:
            _fail(str(error))
        payload = {
            "proposal_id": result.proposal.id,
            "status": result.proposal.promotion_status,
            "constraint_id": result.constraint.id if result.constraint is not None else None,
            "receipt_id": result.review.id,
            "override_stale": result.review.override_stale,
            "override_contradiction": result.review.override_contradiction,
        }
    finally:
        store.close()
    return _emit_payload(payload, shape="card")


@instructions_app.command("reject")
@craik_command(payload_shape="card")
def instructions_reject(
    item_id: Annotated[str, typer.Argument(help="Distilled instruction proposal id.")],
    rationale: Annotated[
        str,
        typer.Option("--rationale", help="Rejection rationale."),
    ] = "",
) -> CommandResult:
    """Reject a distilled instruction with an auditable receipt."""
    store = LocalStore.from_env()
    try:
        store.initialize()
        try:
            result = reject_instruction(
                store,
                proposal_id=item_id,
                operator_identity=_operator_identity(),
                rationale=rationale or "Rejected from CLI.",
            )
        except InstructionApprovalError as error:
            _fail(str(error))
        payload = {
            "proposal_id": result.proposal.id,
            "status": result.proposal.promotion_status,
            "receipt_id": result.review.id,
        }
    finally:
        store.close()
    return _emit_payload(payload, shape="card")


@instructions_app.command("show")
@craik_command(payload_shape="card")
def instructions_show(
    item_id: Annotated[str, typer.Argument(help="Distilled instruction proposal id.")],
) -> CommandResult:
    """Show one distilled instruction with provenance and freshness."""
    _operator_identity()
    store = LocalStore.from_env()
    try:
        store.initialize()
        proposal = store.get_distilled_instruction_proposal(item_id)
        if proposal is None:
            raise typer.BadParameter(f"unknown distilled instruction proposal: {item_id}")
        payload = _proposal_payload(store, proposal)
        payload["provenance"] = [
            _provenance_payload(store, provenance_id)
            for provenance_id in proposal.provenance_ids
        ]
        payload["contradictions"] = [
            report.model_dump(mode="json", by_alias=True)
            for report in store.list_contradictions()
            if item_id in report.affected_artifacts
            or any(
                provenance_id in report.evidence_ids
                for provenance_id in proposal.provenance_ids
            )
        ]
    finally:
        store.close()
    return _emit_payload(payload, shape="card")


def _operator_identity() -> str:
    try:
        session = OperatorSessionStore.from_env().get()
    except OperatorSessionNotFoundError:
        _fail("operator identity required; run craik login")
    return session.subject


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(2)


def _project_id(store: LocalStore, project: str | None) -> str:
    projects = store.list_projects()
    if project:
        resolved = ProjectRegistry(store).get_project(project)
        if resolved is None:
            raise typer.BadParameter(f"unknown project: {project}") from None
        return resolved.id
    if len(projects) == 1:
        return projects[0].id
    raise typer.BadParameter("--project is required when zero or multiple projects are registered")


def _existing_source(
    store: LocalStore,
    *,
    project_id: str,
    kind: InstructionSourceKind,
    path: str,
) -> Any | None:
    for source in list_sources(store, project_id=project_id):
        if source.kind == kind and source.path == path:
            return source
    return None


def _filtered_proposals(
    store: LocalStore,
    *,
    status: str | None,
    source_id: str | None,
    category: str | None,
) -> list[Any]:
    parsed_status = _promotion_status(status) if status else None
    parsed_category = _category(category) if category else None
    proposals = []
    for proposal in store.list_distilled_instruction_proposals():
        if parsed_status and proposal.promotion_status != parsed_status:
            continue
        if source_id and proposal.source_id != source_id:
            continue
        if parsed_category and proposal.category != parsed_category:
            continue
        proposals.append(proposal)
    return sorted(proposals, key=lambda item: (item.category, item.source_id, item.id))


def _proposal_payload(store: LocalStore, proposal: Any) -> dict[str, Any]:
    review = store.get_instruction_promotion_review(f"promotion_review_{proposal.id}")
    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "source_id": proposal.source_id,
        "snapshot_id": proposal.snapshot_id,
        "category": proposal.category,
        "status": "stale" if proposal.promotion_status == "deferred" else proposal.promotion_status,
        "freshness": "stale" if proposal.promotion_status == "deferred" else "fresh",
        "statement": proposal.statement,
        "provenance_ids": list(proposal.provenance_ids),
        "contradiction_ids": list(proposal.contradiction_ids),
        "constraint_id": proposal.promoted_constraint_id,
        "review": review.model_dump(mode="json", by_alias=True) if review is not None else None,
    }


def _provenance_payload(store: LocalStore, provenance_id: str) -> dict[str, Any]:
    provenance = store.get_instruction_provenance(provenance_id)
    if provenance is None:
        return {"id": provenance_id, "missing": True}
    return {
        "id": provenance.id,
        "source_id": provenance.source_id,
        "snapshot_id": provenance.snapshot_id,
        "path": provenance.path,
        "start_line": provenance.start_line,
        "end_line": provenance.end_line,
        "quote": provenance.summary,
        "excerpt_hash": provenance.excerpt_hash,
    }


def _render_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "ID  STATUS  CATEGORY  SOURCE  STATEMENT"
    lines = ["ID\tSTATUS\tCATEGORY\tSOURCE\tSTATEMENT"]
    for item in items:
        lines.append(
            "\t".join(
                (
                    str(item["id"]),
                    str(item["status"]),
                    str(item["category"]),
                    str(item["source_id"]),
                    str(item["statement"]),
                )
            )
        )
    return "\n".join(lines)


def _render_ingest_summary(payload: dict[str, Any]) -> str:
    lines = ["FIELD\tVALUE"]
    for key in (
        "project_id",
        "source_count",
        "snapshot_count",
        "provenance_count",
        "proposal_count",
        "invalidated_count",
        "contradiction_count",
        "skipped_existing_count",
        "unclassified_count",
    ):
        lines.append(f"{key}\t{payload[key]}")
    for warning in payload["warnings"]:
        lines.append(f"warning\t{warning}")
    return "\n".join(lines)


def _emit_payload(
    payload: object,
    *,
    shape: PayloadShape,
    text: str | None = None,
) -> CommandResult:
    result = CommandResult(payload=payload, shape=shape, text=text)
    emit_command_result(result)
    return result


def _instruction_source_kind(value: str) -> InstructionSourceKind:
    allowed = set(get_args(InstructionSourceKind))
    if value not in allowed:
        raise typer.BadParameter(f"unsupported instruction source kind: {value}")
    return value  # type: ignore[return-value]


def _category(value: str) -> DistilledInstructionCategory:
    allowed = {
        "instruction",
        "policy",
        "preference",
        "command",
        "boundary",
        "handoff_rule",
        "memory_rule",
        "security_rule",
        "stale_risk",
    }
    if value not in allowed:
        raise typer.BadParameter(f"unsupported instruction category: {value}")
    return value  # type: ignore[return-value]


def _promotion_status(value: str) -> str:
    aliases = {"stale": "deferred"}
    normalized = aliases.get(value, value)
    allowed = {"proposed", "governing", "rejected", "superseded", "deferred"}
    if normalized not in allowed:
        raise typer.BadParameter(f"unsupported instruction status: {value}")
    return normalized
