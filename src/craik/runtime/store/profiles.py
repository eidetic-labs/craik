"""Gateway, project, run-output, worker, review, and adjudication store methods."""

# ruff: noqa: F403,F405,I001

from __future__ import annotations

from craik.runtime.store.integrity import contract_hmac, hmac_key_for_store
from craik.runtime.store.receipt_integrity import (
    AgentSessionEventReadResult,
    AgentSessionStateReadResult,
    contract_receipt_hmac_status,
)

from .base import *


class ProfileStoreMixin(LocalStoreCore):
    def put_gateway_config(self, config: GatewayConfig) -> None:
        """Persist a gateway configuration record."""
        self.put_contract(config)

    def get_gateway_config(self, config_id: str) -> GatewayConfig | None:
        """Load a gateway configuration by id."""
        contract = self.get_contract("craik.gateway_config", config_id)
        return _cast_optional(GatewayConfig, contract)

    def list_gateway_configs(self) -> list[GatewayConfig]:
        """List gateway configurations."""
        return _cast_list(GatewayConfig, self.list_contracts("craik.gateway_config"))

    def put_gateway_runtime_state(self, state: GatewayRuntimeState) -> None:
        """Persist gateway runtime state."""
        self.put_contract(state)

    def get_gateway_runtime_state(self, state_id: str) -> GatewayRuntimeState | None:
        """Load gateway runtime state by id."""
        contract = self.get_contract("craik.gateway_runtime_state", state_id)
        return _cast_optional(GatewayRuntimeState, contract)

    def list_gateway_runtime_states(self) -> list[GatewayRuntimeState]:
        """List gateway runtime states."""
        return _cast_list(
            GatewayRuntimeState,
            self.list_contracts("craik.gateway_runtime_state"),
        )

    def put_agent_session_state(self, state: AgentSessionState) -> None:
        """Persist persistent agent session state."""
        state = _signed_agent_session_state(self, state)
        self.put_contract(state)

    def get_agent_session_state(self, state_id: str) -> AgentSessionState | None:
        """Load persistent agent session state by id."""
        contract = self.get_contract("craik.agent_session_state", state_id)
        state = _cast_optional(AgentSessionState, contract)
        _verify_agent_session_state_hmac(self, state)
        return state

    def get_agent_session_state_with_verification(
        self,
        state_id: str,
    ) -> AgentSessionStateReadResult | None:
        """Load persistent agent session state with explicit HMAC status."""
        contract = self.get_contract("craik.agent_session_state", state_id)
        state = _cast_optional(AgentSessionState, contract)
        if state is None:
            return None
        return AgentSessionStateReadResult(
            state=state,
            hmac_status=contract_receipt_hmac_status(self, state),
        )

    def list_agent_session_states(self) -> list[AgentSessionState]:
        """List persistent agent session states."""
        states = _cast_list(
            AgentSessionState,
            self.list_contracts("craik.agent_session_state"),
        )
        for state in states:
            _verify_agent_session_state_hmac(self, state)
        return states

    def put_agent_session_event(self, event: AgentSessionEvent) -> None:
        """Persist a persistent agent session event."""
        event = _signed_agent_session_event(self, event)
        self.put_contract(event)

    def get_agent_session_event(self, event_id: str) -> AgentSessionEvent | None:
        """Load a persistent agent session event by id."""
        contract = self.get_contract("craik.agent_session_event", event_id)
        event = _cast_optional(AgentSessionEvent, contract)
        _verify_agent_session_event_hmac(self, event)
        return event

    def get_agent_session_event_with_verification(
        self,
        event_id: str,
    ) -> AgentSessionEventReadResult | None:
        """Load persistent agent session event with explicit HMAC status."""
        contract = self.get_contract("craik.agent_session_event", event_id)
        event = _cast_optional(AgentSessionEvent, contract)
        if event is None:
            return None
        return AgentSessionEventReadResult(
            event=event,
            hmac_status=contract_receipt_hmac_status(self, event),
        )

    def list_agent_session_events(self) -> list[AgentSessionEvent]:
        """List persistent agent session events."""
        events = _cast_list(
            AgentSessionEvent,
            self.list_contracts("craik.agent_session_event"),
        )
        for event in events:
            _verify_agent_session_event_hmac(self, event)
        return events

    def put_project(self, project: ProjectProfile) -> None:
        self.put_contract(project)

    def get_project(self, project_id: str) -> ProjectProfile | None:
        contract = self.get_contract("craik.project_profile", project_id)
        return _cast_optional(ProjectProfile, contract)

    def list_projects(self) -> list[ProjectProfile]:
        return _cast_list(ProjectProfile, self.list_contracts("craik.project_profile"))

    def put_run_output(self, output: RunOutput) -> None:
        self.put_contract(output)

    def get_run_output(self, output_id: str) -> RunOutput | None:
        contract = self.get_contract("craik.run_output", output_id)
        return _cast_optional(RunOutput, contract)

    def list_run_outputs(self) -> list[RunOutput]:
        return _cast_list(RunOutput, self.list_contracts("craik.run_output"))

    def put_worker_result(self, result: WorkerResult) -> None:
        self.put_contract(result)

    def get_worker_result(self, result_id: str) -> WorkerResult | None:
        contract = self.get_contract("craik.worker_result", result_id)
        return _cast_optional(WorkerResult, contract)

    def list_worker_results(self) -> list[WorkerResult]:
        return _cast_list(WorkerResult, self.list_contracts("craik.worker_result"))

    def put_debate_turn(self, turn: DebateTurn) -> None:
        self.put_contract(turn)

    def get_debate_turn(self, turn_id: str) -> DebateTurn | None:
        contract = self.get_contract("craik.debate_turn", turn_id)
        return _cast_optional(DebateTurn, contract)

    def list_debate_turns(self) -> list[DebateTurn]:
        return _cast_list(DebateTurn, self.list_contracts("craik.debate_turn"))

    def put_debate_summary(self, summary: DebateSummary) -> None:
        self.put_contract(summary)

    def get_debate_summary(self, summary_id: str) -> DebateSummary | None:
        contract = self.get_contract("craik.debate_summary", summary_id)
        return _cast_optional(DebateSummary, contract)

    def list_debate_summaries(self) -> list[DebateSummary]:
        return _cast_list(DebateSummary, self.list_contracts("craik.debate_summary"))

    def put_review_request(self, request: ReviewRequest) -> None:
        self.put_contract(request)

    def get_review_request(self, request_id: str) -> ReviewRequest | None:
        contract = self.get_contract("craik.review_request", request_id)
        return _cast_optional(ReviewRequest, contract)

    def list_review_requests(self) -> list[ReviewRequest]:
        return _cast_list(ReviewRequest, self.list_contracts("craik.review_request"))

    def put_review_result(self, result: ReviewResult) -> None:
        self.put_contract(result)

    def get_review_result(self, result_id: str) -> ReviewResult | None:
        contract = self.get_contract("craik.review_result", result_id)
        return _cast_optional(ReviewResult, contract)

    def list_review_results(self) -> list[ReviewResult]:
        return _cast_list(ReviewResult, self.list_contracts("craik.review_result"))

    def put_adjudication_outcome(self, outcome: AdjudicationOutcome) -> None:
        self.put_contract(outcome)

    def get_adjudication_outcome(self, outcome_id: str) -> AdjudicationOutcome | None:
        contract = self.get_contract("craik.adjudication_outcome", outcome_id)
        return _cast_optional(AdjudicationOutcome, contract)

    def list_adjudication_outcomes(self) -> list[AdjudicationOutcome]:
        return _cast_list(
            AdjudicationOutcome,
            self.list_contracts("craik.adjudication_outcome"),
        )


def _signed_agent_session_state(
    store: LocalStoreCore,
    state: AgentSessionState,
) -> AgentSessionState:
    payload = state.model_dump(mode="json", by_alias=True)
    receipt_hmac = contract_hmac(payload, hmac_key_for_store(store))
    return state.model_copy(update={"receipt_hmac": receipt_hmac})


def _signed_agent_session_event(
    store: LocalStoreCore,
    event: AgentSessionEvent,
) -> AgentSessionEvent:
    payload = event.model_dump(mode="json", by_alias=True)
    receipt_hmac = contract_hmac(payload, hmac_key_for_store(store))
    return event.model_copy(update={"receipt_hmac": receipt_hmac})


def _verify_agent_session_state_hmac(
    store: LocalStoreCore,
    state: AgentSessionState | None,
) -> None:
    if state is None:
        return
    if contract_receipt_hmac_status(store, state) == "tampered":
        raise LocalStoreCorruptError(f"stored agent session state has invalid HMAC: {state.id}")


def _verify_agent_session_event_hmac(
    store: LocalStoreCore,
    event: AgentSessionEvent | None,
) -> None:
    if event is None:
        return
    if contract_receipt_hmac_status(store, event) == "tampered":
        raise LocalStoreCorruptError(f"stored agent session event has invalid HMAC: {event.id}")
