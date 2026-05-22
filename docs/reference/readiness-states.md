# Readiness states

<p className="craik-meta"><span>6 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

Craik resolves a progressive readiness state before shell actions,
status checks, and slash-command dispatch. The resolver is intentionally
non-blocking: it reports what is missing without requiring setup to
already be complete.

</div>

## States

<div className="craik-fields">

<div>
<dt><code>unconfigured</code></dt>
<dt><span className="craik-fields__type">first launch</span></dt>
<dd>No initialized local state, operator session, provider profile, or active model has been detected.</dd>
</div>

<div>
<dt><code>fixture</code></dt>
<dt><span className="craik-fields__type">deterministic mode</span></dt>
<dd>Fixture mode is selected for local demos or tests. Live provider calls are not assumed.</dd>
</div>

<div>
<dt><code>local-model</code></dt>
<dt><span className="craik-fields__type">local endpoint</span></dt>
<dd>A local OpenAI-compatible provider profile is configured without a full operator session.</dd>
</div>

<div>
<dt><code>operator-only</code></dt>
<dt><span className="craik-fields__type">identity ready</span></dt>
<dd>An operator session exists, but no provider credential profile has been configured.</dd>
</div>

<div>
<dt><code>provider-only</code></dt>
<dt><span className="craik-fields__type">credential ready</span></dt>
<dd>A provider credential profile exists, but no operator session is active.</dd>
</div>

<div>
<dt><code>fully-ready</code></dt>
<dt><span className="craik-fields__type">runtime ready</span></dt>
<dd>Operator identity, provider credentials, and active model selection are all present.</dd>
</div>

<div>
<dt><code>restricted/offline</code></dt>
<dt><span className="craik-fields__type">network constrained</span></dt>
<dd><code>CRAIK_OFFLINE=1</code> is active. Remote provider actions should not be attempted.</dd>
</div>

</div>

## Surfaces

Use either command to inspect the same readiness payload:

```sh
craik status
craik slash /status
```

The JSON payload includes:

- `state`
- `home`
- `initialized`
- `operator_authenticated`
- `provider_configured`
- `local_model_configured`
- `active_profile`
- `active_model`
- `missing`
- `next_actions`
- `warnings`

## Blocking behavior

Slash commands declare the readiness they need. Commands that only guide
setup are always available. Commands that inspect protected runtime state
return a clear blocked message until the required operator or provider
state exists.
