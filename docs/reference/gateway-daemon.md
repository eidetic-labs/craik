# Gateway daemon mode

<p className="craik-meta"><span>2 min read</span><span>Reference · preview</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The two contracts that describe gateway lifecycle (`gateway_config`
and `gateway_runtime_state`), the shipped lifecycle states, and the
boundary between contract-level helpers and a real production daemon.

</div>

<div className="craik-keypoint">

**Gateway daemon mode is post-MVP unless a later proof workflow explicitly pulls it forward.**

The current surface documents contracts and deterministic lifecycle
helpers — not an operational always-on service. See
[Post-MVP Scope](post-mvp-scope.md).

</div>

## Contracts

<div className="craik-fields">

<div>
<dt>Contract</dt>
<dt><span className="craik-fields__type">Records</span></dt>
<dd>Purpose</dd>
</div>

<div>
<dt><code>craik.gateway_config</code></dt>
<dt><span className="craik-fields__type">config</span></dt>
<dd>Local bind settings · mode · policy envelope · pid/log file paths · whether the gateway is enabled.</dd>
</div>

<div>
<dt><code>craik.gateway_runtime_state</code></dt>
<dt><span className="craik-fields__type">supervisor state</span></dt>
<dd>Supervised lifecycle state · process id · timestamps · receipts · supervision notes.</dd>
</div>

</div>

## Lifecycle states

<div className="craik-fields">

<div>
<dt>State</dt>
<dt><span className="craik-fields__type">Transitions</span></dt>
<dd>Meaning</dd>
</div>

<div>
<dt><code>starting</code></dt>
<dt><span className="craik-fields__type">→ running / failed</span></dt>
<dd>A supervisor has accepted a start request and is preparing the process.</dd>
</div>

<div>
<dt><code>running</code></dt>
<dt><span className="craik-fields__type">→ stopping / failed</span></dt>
<dd>The supervisor has a process id and start timestamp.</dd>
</div>

<div>
<dt><code>stopping</code></dt>
<dt><span className="craik-fields__type">→ stopped</span></dt>
<dd>Reserved for future graceful shutdown coordination.</dd>
</div>

<div>
<dt><code>stopped</code></dt>
<dt><span className="craik-fields__type">terminal</span></dt>
<dd>Process is no longer active and has a stop timestamp.</dd>
</div>

<div>
<dt><code>failed</code></dt>
<dt><span className="craik-fields__type">terminal</span></dt>
<dd>Supervisor recorded an explicit failure reason.</dd>
</div>

</div>

<div className="craik-keypoint">

**Public binds require policy and explicit TLS acknowledgement.**

Daemon mode requires a pid file. Public binds such as `0.0.0.0`
require a policy envelope so externally reachable gateway behavior is
never implicit. The setup CLI also requires
`--allow-insecure-public-gateway` for public binds because Craik does
not terminate TLS itself; production deployments should place the
gateway behind TLS termination or keep it on a private network.

</div>

## Boundary

This phase defines lifecycle state, persistence, and inspection
boundaries. It does not add:

<div className="craik-grid">

<div><h4>Open inbound messages</h4></div>
<div><h4>Webhook handling</h4></div>
<div><h4>Channel adapters</h4></div>
<div><h4>Scheduled task creation</h4></div>
<div><h4>Production dispatch loop</h4></div>

</div>

Those surfaces are post-MVP work items and must attach policy checks
and receipts before they can affect runtime state.

Gateway records are safe to inspect from the operator surface and
local store. Starting a real long-running service remains an explicit
supervisor operation; tests use deterministic lifecycle helpers rather
than background processes.

## What's next

<div className="craik-next">

<a href="../post-mvp-scope/">
<strong>Reference</strong>
<span>Post-MVP scope</span>
<small>Why a production gateway daemon is deferred.</small>
</a>

<a href="../../guides/gateway-troubleshooting/">
<strong>Guide</strong>
<span>Gateway troubleshooting</span>
<small>What's diagnosable from the contracts today.</small>
</a>

<a href="../gateway-receipts/">
<strong>Reference</strong>
<span>Gateway receipts</span>
<small>What every channel decision records.</small>
</a>

</div>
