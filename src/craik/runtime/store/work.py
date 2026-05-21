"""Task, receipt, policy, case, prompt, and handoff store methods."""

# ruff: noqa: F403,F405,I001

from __future__ import annotations

from craik.runtime.store.integrity import contract_hmac, hmac_key_for_store, verify_contract_hmac

from .base import *


class WorkStoreMixin(LocalStoreCore):
    def put_task(self, task: TaskRequest) -> None:
        self.put_contract(task)

    def get_task(self, task_id: str) -> TaskRequest | None:
        return _cast_optional(TaskRequest, self.get_contract("craik.task_request", task_id))

    def list_tasks(self) -> list[TaskRequest]:
        return _cast_list(TaskRequest, self.list_contracts("craik.task_request"))

    def put_task_run(self, run: TaskRun) -> None:
        self.put_contract(run)

    def get_task_run(self, run_id: str) -> TaskRun | None:
        contract = self.get_contract("craik.task_run", run_id)
        return _cast_optional(TaskRun, contract)

    def list_task_runs(self) -> list[TaskRun]:
        return _cast_list(TaskRun, self.list_contracts("craik.task_run"))

    def put_agent_message(self, message: AgentMessage) -> None:
        self.put_contract(message)

    def get_agent_message(self, message_id: str) -> AgentMessage | None:
        contract = self.get_contract("craik.agent_message", message_id)
        return _cast_optional(AgentMessage, contract)

    def list_agent_messages(self) -> list[AgentMessage]:
        return _cast_list(AgentMessage, self.list_contracts("craik.agent_message"))

    def put_receipt(self, receipt: CapabilityReceipt) -> CapabilityReceipt:
        existing = self.get_receipt(receipt.id)
        replaced_hashes = _receipt_hash_history(existing)
        if existing is not None:
            replaced_hashes.append(existing.self_hash)
        previous_hash = (
            receipt.previous_receipt_hash
            if receipt.previous_receipt_hash is not None
            else existing.previous_receipt_hash
            if existing is not None
            else self._latest_receipt_hash(exclude_id=receipt.id)
        )
        if receipt.previous_receipt_hash is None or replaced_hashes:
            receipt = _receipt_with_integrity_metadata(
                receipt,
                previous_hash=previous_hash,
                replaced_hashes=replaced_hashes,
            )
        self.put_contract(receipt)
        stored = self.get_receipt(receipt.id)
        if stored is None:
            raise LocalStoreCorruptError("stored capability receipt could not be reloaded")
        return stored

    def get_receipt(self, receipt_id: str) -> CapabilityReceipt | None:
        contract = self.get_contract("craik.capability_receipt", receipt_id)
        return _cast_optional(CapabilityReceipt, contract)

    def list_receipts(self) -> list[CapabilityReceipt]:
        receipts = _cast_list(CapabilityReceipt, self.list_contracts("craik.capability_receipt"))
        _verify_receipt_chain(receipts)
        return receipts

    def _latest_receipt_hash(self, *, exclude_id: str) -> str | None:
        receipts = [
            receipt for receipt in self.list_receipts() if receipt.id != exclude_id
        ]
        if not receipts:
            return None
        return sorted(receipts, key=lambda receipt: (receipt.created_at, receipt.id))[-1].self_hash

    def put_policy_envelope(self, policy: PolicyEnvelope) -> None:
        self.put_contract(policy)

    def get_policy_envelope(self, policy_id: str) -> PolicyEnvelope | None:
        contract = self.get_contract("craik.policy_envelope", policy_id)
        return _cast_optional(PolicyEnvelope, contract)

    def list_policy_envelopes(self) -> list[PolicyEnvelope]:
        return _cast_list(PolicyEnvelope, self.list_contracts("craik.policy_envelope"))

    def put_capability_grant(self, grant: CapabilityGrant) -> None:
        self.put_contract(grant)

    def get_capability_grant(self, grant_id: str) -> CapabilityGrant | None:
        contract = self.get_contract("craik.capability_grant", grant_id)
        return _cast_optional(CapabilityGrant, contract)

    def list_capability_grants(self) -> list[CapabilityGrant]:
        return _cast_list(CapabilityGrant, self.list_contracts("craik.capability_grant"))

    def put_case_file(self, case_file: CaseFile) -> None:
        self.put_contract(case_file)

    def get_case_file(self, case_file_id: str) -> CaseFile | None:
        contract = self.get_contract("craik.case_file", case_file_id)
        return _cast_optional(CaseFile, contract)

    def list_case_files(self) -> list[CaseFile]:
        return _cast_list(CaseFile, self.list_contracts("craik.case_file"))

    def put_compiled_prompt(self, prompt: CompiledPrompt) -> None:
        self.put_contract(prompt)

    def get_compiled_prompt(self, prompt_id: str) -> CompiledPrompt | None:
        contract = self.get_contract("craik.compiled_prompt", prompt_id)
        return _cast_optional(CompiledPrompt, contract)

    def list_compiled_prompts(self) -> list[CompiledPrompt]:
        return _cast_list(CompiledPrompt, self.list_contracts("craik.compiled_prompt"))

    def put_intent_lock(self, intent_lock: IntentLock) -> None:
        self.put_contract(intent_lock)

    def get_intent_lock(self, intent_lock_id: str) -> IntentLock | None:
        contract = self.get_contract("craik.intent_lock", intent_lock_id)
        return _cast_optional(IntentLock, contract)

    def list_intent_locks(self) -> list[IntentLock]:
        return _cast_list(IntentLock, self.list_contracts("craik.intent_lock"))

    def put_tool_result_attestation(self, attestation: ToolResultAttestation) -> None:
        attestation = _signed_tool_result_attestation(self, attestation)
        self.put_contract(attestation)

    def get_tool_result_attestation(
        self,
        attestation_id: str,
    ) -> ToolResultAttestation | None:
        contract = self.get_contract("craik.tool_result_attestation", attestation_id)
        attestation = _cast_optional(ToolResultAttestation, contract)
        _verify_tool_result_attestation_hmac(self, attestation)
        return attestation

    def list_tool_result_attestations(self) -> list[ToolResultAttestation]:
        attestations = _cast_list(
            ToolResultAttestation,
            self.list_contracts("craik.tool_result_attestation"),
        )
        for attestation in attestations:
            _verify_tool_result_attestation_hmac(self, attestation)
        return attestations

    def put_knowledge_freshness_probe(self, probe: KnowledgeFreshnessProbe) -> None:
        self.put_contract(probe)

    def get_knowledge_freshness_probe(
        self,
        probe_id: str,
    ) -> KnowledgeFreshnessProbe | None:
        contract = self.get_contract("craik.knowledge_freshness_probe", probe_id)
        return _cast_optional(KnowledgeFreshnessProbe, contract)

    def list_knowledge_freshness_probes(self) -> list[KnowledgeFreshnessProbe]:
        return _cast_list(
            KnowledgeFreshnessProbe,
            self.list_contracts("craik.knowledge_freshness_probe"),
        )

    def put_known_trap(self, trap: KnownTrap) -> None:
        self.put_contract(trap)

    def get_known_trap(self, trap_id: str) -> KnownTrap | None:
        contract = self.get_contract("craik.known_trap", trap_id)
        return _cast_optional(KnownTrap, contract)

    def list_known_traps(self) -> list[KnownTrap]:
        return _cast_list(KnownTrap, self.list_contracts("craik.known_trap"))

    def put_negative_knowledge(self, knowledge: NegativeKnowledge) -> None:
        self.put_contract(knowledge)

    def get_negative_knowledge(self, knowledge_id: str) -> NegativeKnowledge | None:
        contract = self.get_contract("craik.negative_knowledge", knowledge_id)
        return _cast_optional(NegativeKnowledge, contract)

    def list_negative_knowledge(self) -> list[NegativeKnowledge]:
        return _cast_list(NegativeKnowledge, self.list_contracts("craik.negative_knowledge"))

    def put_scratchpad_record(self, record: ScratchpadRecord) -> None:
        self.put_contract(record)

    def get_scratchpad_record(self, record_id: str) -> ScratchpadRecord | None:
        contract = self.get_contract("craik.scratchpad_record", record_id)
        return _cast_optional(ScratchpadRecord, contract)

    def list_scratchpad_records(self) -> list[ScratchpadRecord]:
        return _cast_list(ScratchpadRecord, self.list_contracts("craik.scratchpad_record"))

    def put_unknown_record(self, record: UnknownRecord) -> None:
        self.put_contract(record)

    def get_unknown_record(self, record_id: str) -> UnknownRecord | None:
        contract = self.get_contract("craik.unknown_record", record_id)
        return _cast_optional(UnknownRecord, contract)

    def list_unknown_records(self) -> list[UnknownRecord]:
        return _cast_list(UnknownRecord, self.list_contracts("craik.unknown_record"))

    def put_handoff(self, handoff: Handoff) -> None:
        self.put_contract(handoff)

    def get_handoff(self, handoff_id: str) -> Handoff | None:
        contract = self.get_contract("craik.handoff", handoff_id)
        return _cast_optional(Handoff, contract)

    def list_handoffs(self) -> list[Handoff]:
        return _cast_list(Handoff, self.list_contracts("craik.handoff"))

    def put_handoff_quality_score(self, score: HandoffQualityScore) -> None:
        self.put_contract(score)

    def get_handoff_quality_score(self, score_id: str) -> HandoffQualityScore | None:
        contract = self.get_contract("craik.handoff_quality_score", score_id)
        return _cast_optional(HandoffQualityScore, contract)

    def list_handoff_quality_scores(self) -> list[HandoffQualityScore]:
        return _cast_list(
            HandoffQualityScore,
            self.list_contracts("craik.handoff_quality_score"),
        )


def _verify_receipt_chain(receipts: list[CapabilityReceipt]) -> None:
    receipt_hashes = {
        known_hash
        for receipt in receipts
        for known_hash in [receipt.self_hash, *_receipt_hash_history(receipt)]
    }
    for receipt in receipts:
        if (
            receipt.previous_receipt_hash is not None
            and receipt.previous_receipt_hash not in receipt_hashes
        ):
            raise LocalStoreCorruptError("stored capability receipt chain is broken")


def _receipt_with_integrity_metadata(
    receipt: CapabilityReceipt,
    *,
    previous_hash: str | None,
    replaced_hashes: list[str],
) -> CapabilityReceipt:
    payload = receipt.model_dump(mode="json", by_alias=True)
    metadata = dict(payload["result"].get("metadata", {}))
    if replaced_hashes:
        metadata["receipt_hash_history"] = sorted(set(replaced_hashes))
    payload["result"]["metadata"] = metadata
    payload["previous_receipt_hash"] = previous_hash
    payload["self_hash"] = ""
    return CapabilityReceipt.model_validate(payload)


def _receipt_hash_history(receipt: CapabilityReceipt | None) -> list[str]:
    if receipt is None:
        return []
    value = receipt.result.metadata.get("receipt_hash_history")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _signed_tool_result_attestation(
    store: LocalStoreCore,
    attestation: ToolResultAttestation,
) -> ToolResultAttestation:
    key = hmac_key_for_store(store)
    payload = attestation.model_dump(mode="json", by_alias=True)
    return attestation.model_copy(update={"receipt_hmac": contract_hmac(payload, key)})


def _verify_tool_result_attestation_hmac(
    store: LocalStoreCore,
    attestation: ToolResultAttestation | None,
) -> None:
    if attestation is None:
        return
    payload = attestation.model_dump(mode="json", by_alias=True)
    if not verify_contract_hmac(payload, hmac_key_for_store(store)):
        raise LocalStoreCorruptError(
            f"stored tool result attestation has invalid HMAC: {attestation.id}"
        )
