# Slash commands

<p className="craik-meta"><span>7 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

Craik's interactive shell uses a central slash-command registry. The
registry gives every command a name, aliases, summary, usage, examples,
and readiness requirement so shell, TUI, dashboard, and tests can share
one command contract.

</div>

## Core commands

```text
/help
/setup
/auth
/provider
/provider login <provider>
/model
/status
/doctor
/sessions
/resume <session-id>
/approvals
/handoffs
/receipts
/skills
/memory
/gateway
/exit
```

Use `/help <command>` for command-specific syntax:

```text
/help provider
```

Unknown commands return a nearest-match suggestion when possible:

```text
unknown slash command: /stats. Did you mean /status?
```

## Readiness gates

Setup commands are available before auth. Commands that inspect governed
runtime objects may require an operator session and return a blocked
message until the state exists.

The registry is also exposed for automation tests:

```sh
craik slash /status
craik slash "/help provider"
```

Use direct subsystem commands for full JSON outputs and mutation flows:

```sh
craik auth login openai
craik model set openai/gpt-5
craik session list
```
