# Gateway daemon mode

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The foreground gateway daemon, the two contracts that describe gateway
lifecycle (`gateway_config` and `gateway_runtime_state`), and the
current boundary between the health service and channel dispatch.

</div>

<div className="craik-keypoint">

**Gateway daemon mode is foreground and local-first, with service-management helpers.**

`craik gateway start` still runs the foreground HTTP service with a
`/health` endpoint, pid-file lock, and persisted lifecycle transitions.
`craik gateway install` now generates launchd/systemd user-service
definitions, while status, logs, stop, restart, and doctor commands
make lifecycle inspection explicit. Channel dispatch remains
policy-bound contract work; do not expose the daemon publicly without
TLS termination and explicit policy.

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

## Commands

Run setup first, then start the foreground daemon:

```bash
craik setup --enable-gateway --policy-envelope-id policy_gateway
craik gateway install
craik gateway status
craik gateway start
craik gateway logs
craik gateway stop
craik gateway restart
craik gateway doctor
```

The command requires an active operator session, loads
`gateway_default`, writes `starting`, writes `running` after the HTTP
server binds, and writes `stopped` on graceful shutdown. If the pid
file already exists, startup fails instead of running a second daemon.

`craik gateway install` writes a generated service definition under
Craik config:

The generated service uses the absolute `craik` executable resolved at
install time, avoiding service-manager `PATH` ambiguity.

<div className="craik-grid">

<div><h4>macOS</h4><p><code>launchd</code> plist for a user LaunchAgent.</p></div>
<div><h4>Linux</h4><p><code>systemd --user</code> service unit.</p></div>
<div><h4>Windows</h4><p>Manual service plan for this release.</p></div>

</div>

`craik gateway stop` records a stop request and recovers stale pid
files. It does not silently kill a process unless the operator passes
`--signal-process`. `craik gateway restart` records the stopped state
and returns the next step for the installed service or foreground
start.

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

This phase defines a runnable health service, lifecycle state,
persistence, and inspection boundaries. It does not yet add:

<div className="craik-grid">

<div><h4>Open inbound messages</h4></div>
<div><h4>Production dispatch loop</h4></div>
<div><h4>Hosted TLS termination</h4></div>

</div>

Those surfaces must attach policy checks and receipts before they can
affect runtime state.

Gateway records are safe to inspect from the operator surface and
local store. Starting a long-running service remains an explicit
operator action.

## What's next

<div className="craik-next">

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
