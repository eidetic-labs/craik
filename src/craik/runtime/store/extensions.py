"""Adapter, skill, plugin, instruction, and critic store methods."""

# ruff: noqa: F403,F405,I001

from __future__ import annotations

from craik.runtime.store.integrity import contract_hmac, hmac_key_for_store, verify_contract_hmac

from .base import *


class ExtensionStoreMixin(LocalStoreCore):
    def put_adapter_package(self, package: AdapterPackage) -> None:
        self.put_contract(package)

    def get_adapter_package(self, package_id: str) -> AdapterPackage | None:
        contract = self.get_contract("craik.adapter_package", package_id)
        return _cast_optional(AdapterPackage, contract)

    def list_adapter_packages(self) -> list[AdapterPackage]:
        return _cast_list(AdapterPackage, self.list_contracts("craik.adapter_package"))

    def put_human_delegation(self, delegation: HumanDelegationPoint) -> None:
        self.put_contract(delegation)

    def get_human_delegation(self, delegation_id: str) -> HumanDelegationPoint | None:
        contract = self.get_contract("craik.human_delegation_point", delegation_id)
        return _cast_optional(HumanDelegationPoint, contract)

    def list_human_delegations(self) -> list[HumanDelegationPoint]:
        return _cast_list(
            HumanDelegationPoint,
            self.list_contracts("craik.human_delegation_point"),
        )

    def put_scope_change_request(self, request: ScopeChangeRequest) -> None:
        self.put_contract(request)

    def get_scope_change_request(self, request_id: str) -> ScopeChangeRequest | None:
        contract = self.get_contract("craik.scope_change_request", request_id)
        return _cast_optional(ScopeChangeRequest, contract)

    def list_scope_change_requests(self) -> list[ScopeChangeRequest]:
        return _cast_list(
            ScopeChangeRequest,
            self.list_contracts("craik.scope_change_request"),
        )

    def put_scope_change_result(self, result: ScopeChangeResult) -> None:
        self.put_contract(result)

    def get_scope_change_result(self, result_id: str) -> ScopeChangeResult | None:
        contract = self.get_contract("craik.scope_change_result", result_id)
        return _cast_optional(ScopeChangeResult, contract)

    def list_scope_change_results(self) -> list[ScopeChangeResult]:
        return _cast_list(
            ScopeChangeResult,
            self.list_contracts("craik.scope_change_result"),
        )

    def put_skill_package(self, package: SkillPackage) -> None:
        self.put_contract(package)

    def get_skill_package(self, package_id: str) -> SkillPackage | None:
        contract = self.get_contract("craik.skill_package", package_id)
        return _cast_optional(SkillPackage, contract)

    def list_skill_packages(self) -> list[SkillPackage]:
        return _cast_list(SkillPackage, self.list_contracts("craik.skill_package"))

    def put_skill_registry(self, registry: SkillRegistry) -> None:
        self.put_contract(registry)

    def get_skill_registry(self, registry_id: str) -> SkillRegistry | None:
        contract = self.get_contract("craik.skill_registry", registry_id)
        return _cast_optional(SkillRegistry, contract)

    def list_skill_registries(self) -> list[SkillRegistry]:
        return _cast_list(SkillRegistry, self.list_contracts("craik.skill_registry"))

    def put_skill_invocation_context(self, context: SkillInvocationContext) -> None:
        self.put_contract(context)

    def get_skill_invocation_context(
        self,
        context_id: str,
    ) -> SkillInvocationContext | None:
        contract = self.get_contract("craik.skill_invocation_context", context_id)
        return _cast_optional(SkillInvocationContext, contract)

    def list_skill_invocation_contexts(self) -> list[SkillInvocationContext]:
        return _cast_list(
            SkillInvocationContext,
            self.list_contracts("craik.skill_invocation_context"),
        )

    def put_plugin_capability_grant(self, grant: PluginCapabilityGrant) -> None:
        self.put_contract(grant)

    def get_plugin_capability_grant(
        self,
        grant_id: str,
    ) -> PluginCapabilityGrant | None:
        contract = self.get_contract("craik.plugin_capability_grant", grant_id)
        return _cast_optional(PluginCapabilityGrant, contract)

    def list_plugin_capability_grants(self) -> list[PluginCapabilityGrant]:
        return _cast_list(
            PluginCapabilityGrant,
            self.list_contracts("craik.plugin_capability_grant"),
        )

    def put_plugin_descriptor(self, descriptor: PluginDescriptor) -> None:
        self.put_contract(descriptor)

    def get_plugin_descriptor(self, descriptor_id: str) -> PluginDescriptor | None:
        contract = self.get_contract("craik.plugin_descriptor", descriptor_id)
        return _cast_optional(PluginDescriptor, contract)

    def list_plugin_descriptors(self) -> list[PluginDescriptor]:
        return _cast_list(
            PluginDescriptor,
            self.list_contracts("craik.plugin_descriptor"),
        )

    def put_plugin_probation(self, probation: PluginProbation) -> None:
        probation = _signed_plugin_probation(self, probation)
        self.put_contract(probation)

    def get_plugin_probation(self, probation_id: str) -> PluginProbation | None:
        contract = self.get_contract("craik.plugin_probation", probation_id)
        probation = _cast_optional(PluginProbation, contract)
        _verify_plugin_probation_hmac(self, probation)
        return probation

    def list_plugin_probations(self) -> list[PluginProbation]:
        probations = _cast_list(PluginProbation, self.list_contracts("craik.plugin_probation"))
        for probation in probations:
            _verify_plugin_probation_hmac(self, probation)
        return probations

    def put_plugin_receipt(self, receipt: PluginReceipt) -> None:
        receipt = _signed_plugin_receipt(self, receipt)
        self.put_contract(receipt)

    def get_plugin_receipt(self, receipt_id: str) -> PluginReceipt | None:
        contract = self.get_contract("craik.plugin_receipt", receipt_id)
        receipt = _cast_optional(PluginReceipt, contract)
        _verify_plugin_receipt_hmac(self, receipt)
        return receipt

    def list_plugin_receipts(self) -> list[PluginReceipt]:
        receipts = _cast_list(PluginReceipt, self.list_contracts("craik.plugin_receipt"))
        for receipt in receipts:
            _verify_plugin_receipt_hmac(self, receipt)
        return receipts

    def put_instruction_source(self, source: InstructionSource) -> None:
        self.put_contract(source)
        _upsert_instruction_source_row(self, source)

    def get_instruction_source(self, source_id: str) -> InstructionSource | None:
        contract = self.get_contract("craik.instruction_source", source_id)
        return _cast_optional(InstructionSource, contract)

    def list_instruction_sources(self) -> list[InstructionSource]:
        return _cast_list(
            InstructionSource,
            self.list_contracts("craik.instruction_source"),
        )

    def put_instruction_source_registration(
        self,
        registration: InstructionSourceRegistration,
    ) -> None:
        self.put_contract(registration)

    def get_instruction_source_registration(
        self,
        registration_id: str,
    ) -> InstructionSourceRegistration | None:
        contract = self.get_contract("craik.instruction_source_registration", registration_id)
        return _cast_optional(InstructionSourceRegistration, contract)

    def list_instruction_source_registrations(
        self,
    ) -> list[InstructionSourceRegistration]:
        return _cast_list(
            InstructionSourceRegistration,
            self.list_contracts("craik.instruction_source_registration"),
        )

    def put_instruction_registry_receipt(
        self,
        receipt: InstructionRegistryReceipt,
    ) -> None:
        self.put_contract(receipt)

    def get_instruction_registry_receipt(
        self,
        receipt_id: str,
    ) -> InstructionRegistryReceipt | None:
        contract = self.get_contract("craik.instruction_registry_receipt", receipt_id)
        return _cast_optional(InstructionRegistryReceipt, contract)

    def list_instruction_registry_receipts(self) -> list[InstructionRegistryReceipt]:
        return _cast_list(
            InstructionRegistryReceipt,
            self.list_contracts("craik.instruction_registry_receipt"),
        )

    def put_instruction_source_registry(self, registry: InstructionSourceRegistry) -> None:
        self.put_contract(registry)

    def get_instruction_source_registry(
        self,
        registry_id: str,
    ) -> InstructionSourceRegistry | None:
        contract = self.get_contract("craik.instruction_source_registry", registry_id)
        return _cast_optional(InstructionSourceRegistry, contract)

    def list_instruction_source_registries(self) -> list[InstructionSourceRegistry]:
        return _cast_list(
            InstructionSourceRegistry,
            self.list_contracts("craik.instruction_source_registry"),
        )

    def put_instruction_source_snapshot(self, snapshot: InstructionSourceSnapshot) -> None:
        self.put_contract(snapshot)

    def get_instruction_source_snapshot(
        self,
        snapshot_id: str,
    ) -> InstructionSourceSnapshot | None:
        contract = self.get_contract("craik.instruction_source_snapshot", snapshot_id)
        return _cast_optional(InstructionSourceSnapshot, contract)

    def list_instruction_source_snapshots(self) -> list[InstructionSourceSnapshot]:
        return _cast_list(
            InstructionSourceSnapshot,
            self.list_contracts("craik.instruction_source_snapshot"),
        )

    def put_instruction_provenance(self, provenance: InstructionProvenance) -> None:
        self.put_contract(provenance)

    def get_instruction_provenance(self, provenance_id: str) -> InstructionProvenance | None:
        contract = self.get_contract("craik.instruction_provenance", provenance_id)
        return _cast_optional(InstructionProvenance, contract)

    def list_instruction_provenance(self) -> list[InstructionProvenance]:
        return _cast_list(
            InstructionProvenance,
            self.list_contracts("craik.instruction_provenance"),
        )

    def put_distilled_instruction_proposal(
        self,
        proposal: DistilledInstructionProposal,
    ) -> None:
        self.put_contract(proposal)

    def get_distilled_instruction_proposal(
        self,
        proposal_id: str,
    ) -> DistilledInstructionProposal | None:
        contract = self.get_contract("craik.distilled_instruction_proposal", proposal_id)
        return _cast_optional(DistilledInstructionProposal, contract)

    def list_distilled_instruction_proposals(self) -> list[DistilledInstructionProposal]:
        return _cast_list(
            DistilledInstructionProposal,
            self.list_contracts("craik.distilled_instruction_proposal"),
        )

    def put_instruction_promotion_review(self, review: InstructionPromotionReview) -> None:
        self.put_contract(review)

    def get_instruction_promotion_review(
        self,
        review_id: str,
    ) -> InstructionPromotionReview | None:
        contract = self.get_contract("craik.instruction_promotion_review", review_id)
        return _cast_optional(InstructionPromotionReview, contract)

    def list_instruction_promotion_reviews(self) -> list[InstructionPromotionReview]:
        return _cast_list(
            InstructionPromotionReview,
            self.list_contracts("craik.instruction_promotion_review"),
        )

    def put_promoted_instruction_constraint(
        self,
        constraint: PromotedInstructionConstraint,
    ) -> None:
        self.put_contract(constraint)

    def get_promoted_instruction_constraint(
        self,
        constraint_id: str,
    ) -> PromotedInstructionConstraint | None:
        contract = self.get_contract("craik.promoted_instruction_constraint", constraint_id)
        return _cast_optional(PromotedInstructionConstraint, contract)

    def list_promoted_instruction_constraints(self) -> list[PromotedInstructionConstraint]:
        return _cast_list(
            PromotedInstructionConstraint,
            self.list_contracts("craik.promoted_instruction_constraint"),
        )

    def put_reference_integration(self, integration: ReferenceIntegration) -> None:
        self.put_contract(integration)

    def get_reference_integration(
        self,
        integration_id: str,
    ) -> ReferenceIntegration | None:
        contract = self.get_contract("craik.reference_integration", integration_id)
        return _cast_optional(ReferenceIntegration, contract)

    def list_reference_integrations(self) -> list[ReferenceIntegration]:
        return _cast_list(
            ReferenceIntegration,
            self.list_contracts("craik.reference_integration"),
        )

    def put_run_delta(self, delta: RunDelta) -> None:
        self.put_contract(delta)

    def get_run_delta(self, delta_id: str) -> RunDelta | None:
        contract = self.get_contract("craik.run_delta", delta_id)
        return _cast_optional(RunDelta, contract)

    def list_run_deltas(self) -> list[RunDelta]:
        return _cast_list(RunDelta, self.list_contracts("craik.run_delta"))

    def put_recovery_session(self, session: RecoverySession) -> None:
        session = _signed_recovery_session(self, session)
        self.put_contract(session)

    def get_recovery_session(self, session_id: str) -> RecoverySession | None:
        contract = self.get_contract("craik.recovery_session", session_id)
        session = _cast_optional(RecoverySession, contract)
        _verify_recovery_session_hmac(self, session)
        return session

    def list_recovery_sessions(self) -> list[RecoverySession]:
        sessions = _cast_list(RecoverySession, self.list_contracts("craik.recovery_session"))
        for session in sessions:
            _verify_recovery_session_hmac(self, session)
        return sessions

    def put_runtime_critic_finding(self, finding: RuntimeCriticFinding) -> None:
        self.put_contract(finding)

    def get_runtime_critic_finding(
        self,
        finding_id: str,
    ) -> RuntimeCriticFinding | None:
        contract = self.get_contract("craik.runtime_critic_finding", finding_id)
        return _cast_optional(RuntimeCriticFinding, contract)

    def list_runtime_critic_findings(self) -> list[RuntimeCriticFinding]:
        return _cast_list(
            RuntimeCriticFinding,
            self.list_contracts("craik.runtime_critic_finding"),
        )

    def put_red_team_finding(self, finding: RedTeamFinding) -> None:
        self.put_contract(finding)

    def get_red_team_finding(self, finding_id: str) -> RedTeamFinding | None:
        contract = self.get_contract("craik.red_team_finding", finding_id)
        return _cast_optional(RedTeamFinding, contract)

    def list_red_team_findings(self) -> list[RedTeamFinding]:
        return _cast_list(RedTeamFinding, self.list_contracts("craik.red_team_finding"))


def _signed_recovery_session(
    store: LocalStoreCore,
    session: RecoverySession,
) -> RecoverySession:
    payload = session.model_dump(mode="json", by_alias=True)
    receipt_hmac = contract_hmac(payload, hmac_key_for_store(store))
    return session.model_copy(update={"receipt_hmac": receipt_hmac})


def _signed_plugin_probation(
    store: LocalStoreCore,
    probation: PluginProbation,
) -> PluginProbation:
    payload = probation.model_dump(mode="json", by_alias=True)
    receipt_hmac = contract_hmac(payload, hmac_key_for_store(store))
    return probation.model_copy(update={"receipt_hmac": receipt_hmac})


def _verify_plugin_probation_hmac(
    store: LocalStoreCore,
    probation: PluginProbation | None,
) -> None:
    if probation is None or probation.receipt_hmac is None:
        return
    payload = probation.model_dump(mode="json", by_alias=True)
    if not verify_contract_hmac(payload, hmac_key_for_store(store)):
        raise LocalStoreCorruptError(f"stored plugin probation has invalid HMAC: {probation.id}")


def _signed_plugin_receipt(
    store: LocalStoreCore,
    receipt: PluginReceipt,
) -> PluginReceipt:
    payload = receipt.model_dump(mode="json", by_alias=True)
    receipt_hmac = contract_hmac(payload, hmac_key_for_store(store))
    return receipt.model_copy(update={"receipt_hmac": receipt_hmac})


def _verify_plugin_receipt_hmac(
    store: LocalStoreCore,
    receipt: PluginReceipt | None,
) -> None:
    if receipt is None or receipt.receipt_hmac is None:
        return
    payload = receipt.model_dump(mode="json", by_alias=True)
    if not verify_contract_hmac(payload, hmac_key_for_store(store)):
        raise LocalStoreCorruptError(f"stored plugin receipt has invalid HMAC: {receipt.id}")


def _verify_recovery_session_hmac(
    store: LocalStoreCore,
    session: RecoverySession | None,
) -> None:
    if session is None:
        return
    payload = session.model_dump(mode="json", by_alias=True)
    if not verify_contract_hmac(payload, hmac_key_for_store(store)):
        raise LocalStoreCorruptError(f"stored recovery session has invalid HMAC: {session.id}")


def _upsert_instruction_source_row(store: LocalStoreCore, source: InstructionSource) -> None:
    payload = source.model_dump(mode="json", by_alias=True)
    now = datetime.now(UTC).isoformat()
    registered_by = source.registered_by or source.declared_by
    registered_at = (source.registered_at or source.created_at).isoformat()
    try:
        with store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO instruction_sources (
                  id, project_id, kind, path, owner, trust_boundary, active,
                  registered_by, registered_at, content_hash, payload_json,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  project_id = excluded.project_id,
                  kind = excluded.kind,
                  path = excluded.path,
                  owner = excluded.owner,
                  trust_boundary = excluded.trust_boundary,
                  active = excluded.active,
                  registered_by = excluded.registered_by,
                  registered_at = excluded.registered_at,
                  content_hash = excluded.content_hash,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                (
                    source.id,
                    source.project_id,
                    source.kind,
                    source.path,
                    source.owner,
                    source.trust_boundary,
                    1 if source.active else 0,
                    registered_by,
                    registered_at,
                    source.content_hash,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    now,
                    now,
                ),
            )
    except sqlite3.DatabaseError as error:
        raise LocalStoreCorruptError(
            f"cannot mirror instruction source registration: {error}"
        ) from error
