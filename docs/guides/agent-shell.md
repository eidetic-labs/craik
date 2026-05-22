# Agent shell

<p className="craik-meta"><span>8 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Launch Craik before setup is complete, use the in-runtime command surface,
and understand how one-shot prompts behave when the runtime is not yet
fully configured.

</div>

## Launch

Run `craik` with no subcommand to enter the agent shell entrypoint:

```sh
craik
```

On first launch, Craik does not require operator login, provider
credentials, a selected model, or a project. Instead, it prints the
current readiness state and the next actions required to make the runtime
usable.

```text
Craik Agent Shell
State: unconfigured
Profile: default
Model: not selected
Missing: operator session, provider credentials, active model
Next actions:
- run /auth login or craik auth login
- run /provider login openai, anthropic, gemini, or local
- run /model set <provider/model>
```

Use `craik chat` when you want the shell entrypoint to be explicit:

```sh
craik chat
```

## One-shot mode

Use `-z` for quiet one-shot execution:

```sh
craik -z "Summarize the current readiness state."
```

The one-shot path emits only the final response. If Craik is not fully
ready, the final response names the blocked state and the next action
instead of printing the shell status card.

`craik chat -q` is the conversational alias:

```sh
craik chat -q "What model is active?"
```

## Slash commands

The shell command surface is slash-command first. The same registry is
used by the shell and by testable command dispatch.

```text
/help
/status
/setup
/auth
/provider login openai
/model
/sessions
/approvals
/receipts
/skills
/exit
```

Unknown commands suggest the nearest known command. Readiness-gated
commands explain what is missing instead of failing with an opaque stack
trace.

## Automation

Subsystem CLI commands remain available for scripts:

```sh
craik status
craik model status
craik session list
craik profile list
```

Use the shell for discovery and day-to-day interaction. Use subsystem
commands when you need stable JSON output in automation.
