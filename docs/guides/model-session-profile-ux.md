# Model, session, and profile UX

<p className="craik-meta"><span>9 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

Craik v0.10.0 adds operator-facing commands for model selection,
persistent session inspection, and local profile/persona boundaries.
These commands are designed for shell discovery and automation-friendly
JSON output.

</div>

## Model selection

Set the active model with a provider-qualified reference:

```sh
craik model set openai/gpt-5
craik model status
```

The selected model is stored under `$CRAIK_HOME/config/model-settings.json`
and appears in `craik status` and the shell startup card.

Aliases and fallbacks are managed explicitly:

```sh
craik model alias list
craik model alias add fast openai/gpt-5-mini
craik model fallback add anthropic/claude-sonnet
craik model fallback list
```

Unknown token and cost data is reported as `unknown` until a provider
adapter supplies concrete usage metadata.

## Sessions

Persistent agent session records are read from the local runtime store:

```sh
craik session list
craik session show agent_session_docs
craik session resume agent_session_docs
craik session export agent_session_docs
```

Exports are redacted by default. `prune` and `delete` require `--yes`.
Deletion marks a session stopped rather than removing the record, which
preserves continuity and audit history.

Session and usage commands require an active operator session because
they inspect persisted runtime activity, receipts, and handoff links.

## Profiles and personas

Profiles give operators a local boundary for provider config, model
selection, sessions, skills, memory, and gateway state.

```sh
craik profile create release --description "Release work"
craik profile use release
craik profile list
craik profile export
```

The current active profile is visible in `craik status` and the shell
startup card. Profile exports omit secrets by default.

## Usage and insights

Use `craik usage` or `craik insights` to summarize known runtime
activity:

```sh
craik usage
craik insights
```

The summary names unknown values explicitly instead of silently omitting
them. This keeps early local use honest while leaving a stable place for
provider adapters to attach token, cost, failure, approval, and skill
impact metrics.
