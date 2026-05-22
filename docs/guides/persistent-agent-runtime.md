# Persistent agent runtime

<p className="craik-meta"><span>5 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Launch and manage the v0.9.0 persistent agent runtime. This guide
covers the lifecycle CLI, the operator-session requirement, the
provider-backed prompt loop, and the records Craik leaves behind.

</div>

<div className="craik-keypoint">

**One-shot runs and persistent agents are separate surfaces.**

Use `craik run execute` for bounded one-shot task runs. Use
`craik agent launch` plus `craik agent prompt` when you want a
longer-lived session that keeps provider, model, project, operator,
policy, receipt, handoff, and recovery links together.

</div>

## Before you launch

Persistent agent lifecycle commands require an active operator session.
The CLI checks the same session store used by the operator surface:

```sh
craik auth login
craik whoami
```

If no session is available, lifecycle commands fail before reading or
writing agent state.

## Launch a session

```sh
craik agent launch \
  --session-id agent_docs \
  --project-id project_docs \
  --provider-id provider_openai \
  --model-id gpt-5.2 \
  --auth-profile-id openai:work
```

The command persists a `craik.agent_session_state` record and returns
JSON. The session is bound to the active operator subject and issuer,
the project id, provider id, optional model id, optional auth profile,
and optional policy envelope.

## Send a prompt

```sh
craik agent prompt agent_docs "Implement the next bounded provider task."
```

`prompt` creates a task under the session project, executes it through
the session provider, and returns the same run, provider receipt,
handoff, and output shape used by provider-backed one-shot runs. The
session moves back to `idle` when the run finishes and stores the active
task id, run id, receipt ids, handoff ids, and recovery metadata.

Use `/exit`, `exit`, `/quit`, or `quit` as the prompt text to stop the
session without starting a provider run:

```sh
craik agent prompt agent_docs /exit
```

For deterministic fixture-backed validation, the command grants the
fixture action by default. Use `--no-allow-fixture-action` to exercise
the blocked approval path, `--max-iterations` to test interruption, and
`--provider-token-budget` to test token-budget interruption.

## Inspect and list sessions

```sh
craik agent status agent_docs
craik agent list
```

`status` returns one persisted session. When a future background launch
stores a pid, status checks whether that pid still exists. Missing
processes are marked `failed` with an operator-visible supervision
note, which gives recovery code a precise state to act on.

## Stop and restart

```sh
craik agent stop agent_docs --reason "operator stop"
craik agent restart agent_docs --reason "operator restart"
```

Stop is only valid for active sessions. Restart is only valid for
stopped or failed sessions. Invalid transitions fail with a CLI input
error and do not mutate stored state.

## What is persisted

Agent sessions store identifiers and references, not credential
material:

<div className="craik-grid">

<div><h4>Operator</h4><p>Subject and issuer from the active session.</p></div>
<div><h4>Provider</h4><p>Provider id, model id, and optional auth profile id.</p></div>
<div><h4>Lifecycle</h4><p>Mode, status, timestamps, pid, endpoint URL, and supervision notes.</p></div>
<div><h4>Links</h4><p>Project, task, run, policy envelope, receipt, handoff, and recovery ids.</p></div>
<div><h4>Events</h4><p>Prompt, run completion, interruption, and exit events.</p></div>

</div>

Each prompt also persists redacted `craik.agent_session_event` records.
Events carry stable ids for the session, task, run, handoff, receipts,
provider, model, policy envelope, and recovery metadata. The raw prompt
is not stored in the event; Craik stores a short prompt hash for
correlation without adding operator text to logs.

## Validation

```sh
uv run --extra dev pytest tests/test_cli_agents.py tests/test_agent_sessions.py
```

Expected output: launch, prompt, status, stop, restart,
operator-session gates, invalid transitions, prompt events, receipt and
handoff links, interruption recovery metadata, explicit exit behavior,
and stale-pid recovery tests pass.

## What's next

<div className="craik-next">

<a href="../../reference/agent-lifecycle/">
<strong>Reference</strong>
<span>Agent lifecycle</span>
<small>Status values, commands, and transition rules.</small>
</a>

<a href="../../guides/provider-routing/">
<strong>Guide</strong>
<span>Provider routing</span>
<small>Provider and sandbox decisions used by later persistent sessions.</small>
</a>

<a href="../../reference/run-state/">
<strong>Reference</strong>
<span>Run state</span>
<small>The one-shot task-run lifecycle.</small>
</a>

</div>
