"""Runtime services for Craik."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
from types import ModuleType

_LEGACY_MODULE_TARGETS = {
    "craik.runtime.accessibility": "craik.runtime.companions.accessibility",
    "craik.runtime.adjacent_runtime_bridge": "craik.runtime.bridges.adjacent_runtime_bridge",
    "craik.runtime.browser_tool_boundary": "craik.runtime.sandbox.browser_tool_boundary",
    "craik.runtime.case_files": "craik.runtime.work.case_files",
    "craik.runtime.channel_allowlist": "craik.runtime.channels.allowlist",
    "craik.runtime.channel_identity": "craik.runtime.channels.identity",
    "craik.runtime.channel_policy": "craik.runtime.channels.policy",
    "craik.runtime.claude_adapter": "craik.runtime.runners.claude_adapter",
    "craik.runtime.codex_adapter": "craik.runtime.runners.codex_adapter",
    "craik.runtime.context_debt": "craik.runtime.work.context_debt",
    "craik.runtime.contradictions": "craik.runtime.memory.contradictions",
    "craik.runtime.critics": "craik.runtime.reviewing.critics",
    "craik.runtime.debates": "craik.runtime.reviewing.debates",
    "craik.runtime.delegations": "craik.runtime.reviewing.delegations",
    "craik.runtime.demos": "craik.runtime.projects.demos",
    "craik.runtime.demos_provider": "craik.runtime.projects.demos_provider",
    "craik.runtime.desktop_companion": "craik.runtime.companions.desktop_companion",
    "craik.runtime.docker_sandbox_backend": "craik.runtime.sandbox.docker_sandbox_backend",
    "craik.runtime.exit_discipline": "craik.runtime.work.exit_discipline",
    "craik.runtime.freshness": "craik.runtime.memory.freshness",
    "craik.runtime.gemini_adapter": "craik.runtime.runners.google_adapter",
    "craik.runtime.graph": "craik.runtime.work.graph",
    "craik.runtime.handoffs": "craik.runtime.work.handoffs",
    "craik.runtime.http_transport": "craik.runtime.providers.http_transport",
    "craik.runtime.import_dry_run": "craik.runtime.projects.import_dry_run",
    "craik.runtime.instruction_sources": "craik.runtime.projects.instruction_sources",
    "craik.runtime.intent_locks": "craik.runtime.policy.intent_locks",
    "craik.runtime.investigations": "craik.runtime.reviewing.investigations",
    "craik.runtime.known_traps": "craik.runtime.work.known_traps",
    "craik.runtime.learning_receipts": "craik.runtime.skills.learning_receipts",
    "craik.runtime.local_process_backend": "craik.runtime.sandbox.local_process_backend",
    "craik.runtime.locale_i18n": "craik.runtime.companions.locale_i18n",
    "craik.runtime.loop": "craik.runtime.work.loop",
    "craik.runtime.mcp_client": "craik.runtime.sandbox.mcp_client",
    "craik.runtime.mcp_export": "craik.runtime.sandbox.mcp_export",
    "craik.runtime.memory_errors": "craik.runtime.memory.memory_errors",
    "craik.runtime.memory_hygiene": "craik.runtime.memory.memory_hygiene",
    "craik.runtime.memory_proposals": "craik.runtime.memory.memory_proposals",
    "craik.runtime.memory_review": "craik.runtime.memory.memory_review",
    "craik.runtime.messaging_channel": "craik.runtime.channels.messaging",
    "craik.runtime.migration_assessment": "craik.runtime.projects.migration_assessment",
    "craik.runtime.migration_maps": "craik.runtime.projects.migration_maps",
    "craik.runtime.mobile_companion": "craik.runtime.companions.mobile_companion",
    "craik.runtime.model_providers": "craik.runtime.providers.model_providers",
    "craik.runtime.multi_agent_workflow_bridge": (
        "craik.runtime.bridges.multi_agent_workflow_bridge"
    ),
    "craik.runtime.multimodal_artifacts": "craik.runtime.voice.multimodal_artifacts",
    "craik.runtime.onboarding": "craik.runtime.projects.onboarding",
    "craik.runtime.operator_memory_views": "craik.runtime.memory.operator_memory_views",
    "craik.runtime.operator_views": "craik.runtime.companions.operator_views",
    "craik.runtime.policy_tests": "craik.runtime.policy.policy_tests",
    "craik.runtime.preference_facts": "craik.runtime.memory.preference_facts",
    "craik.runtime.preview_adapter": "craik.runtime.runners.preview_adapter",
    "craik.runtime.project_registry": "craik.runtime.projects.project_registry",
    "craik.runtime.prompts": "craik.runtime.projects.prompts",
    "craik.runtime.provider_budgets": "craik.runtime.providers.provider_budgets",
    "craik.runtime.provider_certification": "craik.runtime.providers.provider_certification",
    "craik.runtime.provider_failover": "craik.runtime.providers.provider_failover",
    "craik.runtime.provider_runner": "craik.runtime.providers.provider_runner",
    "craik.runtime.provider_runtime": "craik.runtime.providers.provider_runtime",
    # Deprecated import path; resolves to provider_runtime_google (gemini→google rename).
    "craik.runtime.providers.provider_runtime_gemini": (
        "craik.runtime.providers.provider_runtime_google"
    ),
    "craik.runtime.provider_runtime_support": "craik.runtime.providers.provider_runtime_support",
    "craik.runtime.provider_transport": "craik.runtime.providers.provider_transport",
    "craik.runtime.public_docs": "craik.runtime.projects.public_docs",
    "craik.runtime.quality_scores": "craik.runtime.work.quality_scores",
    "craik.runtime.receipts": "craik.runtime.work.receipts",
    "craik.runtime.recovery": "craik.runtime.work.recovery",
    "craik.runtime.redaction": "craik.runtime.policy.redaction",
    "craik.runtime.remote_shell_backend": "craik.runtime.sandbox.remote_shell_backend",
    "craik.runtime.reviews": "craik.runtime.reviewing.reviews",
    "craik.runtime.run_outputs": "craik.runtime.work.run_outputs",
    "craik.runtime.runner_metadata": "craik.runtime.runners.runner_metadata",
    "craik.runtime.runs": "craik.runtime.work.runs",
    "craik.runtime.scheduled_automations": "craik.runtime.channels.scheduled_automations",
    "craik.runtime.schedules": "craik.runtime.channels.schedules",
    "craik.runtime.scratchpad": "craik.runtime.work.scratchpad",
    "craik.runtime.secret_migration": "craik.runtime.projects.secret_migration",
    "craik.runtime.skill_promotions": "craik.runtime.skills.skill_promotions",
    "craik.runtime.skill_proposals": "craik.runtime.skills.skill_proposals",
    "craik.runtime.skill_replay": "craik.runtime.skills.skill_replay",
    "craik.runtime.skill_rollbacks": "craik.runtime.skills.skill_rollbacks",
    "craik.runtime.skill_telemetry": "craik.runtime.skills.skill_telemetry",
    "craik.runtime.speech_to_text": "craik.runtime.voice.speech_to_text",
    "craik.runtime.tasks": "craik.runtime.work.tasks",
    "craik.runtime.text_to_speech": "craik.runtime.voice.text_to_speech",
    "craik.runtime.trajectory_exports": "craik.runtime.skills.trajectory_exports",
    "craik.runtime.update_guidance": "craik.runtime.projects.update_guidance",
    "craik.runtime.visual_workspace": "craik.runtime.companions.visual_workspace",
    "craik.runtime.voice_posture": "craik.runtime.voice.voice_posture",
    "craik.runtime.webhook_ingress": "craik.runtime.channels.webhook_ingress",
    "craik.runtime.work_graph_visual": "craik.runtime.companions.work_graph_visual",
}


class _RuntimeAliasLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, target: str) -> None:
        self.fullname = fullname
        self.target = target

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        module = importlib.import_module(self.target)
        sys.modules[self.fullname] = module
        return module

    def exec_module(self, module: ModuleType) -> None:
        return None


class _RuntimeAliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        alias_target = _LEGACY_MODULE_TARGETS.get(fullname)
        if alias_target is None:
            return None
        return importlib.machinery.ModuleSpec(
            fullname,
            _RuntimeAliasLoader(fullname, alias_target),
        )


if not any(isinstance(finder, _RuntimeAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _RuntimeAliasFinder())
