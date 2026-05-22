# Doctor Diagnostics

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll do**

Run `craik doctor` to health-check your Craik home, identity, credentials,
and gateway posture — without making a single live API call, writing a
receipt, or starting a daemon. By the end, you'll know exactly what's
configured, what's broken, and what to fix first.

</div>

<div className="craik-keypoint">

**Doctor is read-only**

`craik doctor` inspects existing local state and environment variables.
It does **not** create `CRAIK_HOME`, initialize a database, contact
Stigmem, start a gateway, or write receipts. Run it any time without
worrying about side effects. Because those diagnostics read local
operator state, the CLI requires an active operator session before it
prints the report.

</div>

## When to run doctor

<div className="craik-grid">

<div>
<h4>First-time setup</h4>
<p>Right after <code>craik setup</code> — confirm Craik home, store, and gateway config are valid.</p>
</div>

<div>
<h4>Before going live</h4>
<p>Before binding a public gateway, running automation, or making a live provider call.</p>
</div>

<div>
<h4>On a fresh shell</h4>
<p>To make sure <code>CRAIK_HOME</code> is pointing where you think it is.</p>
</div>

<div>
<h4>When something feels off</h4>
<p>Faster than guessing — every check has a status and an action when one is needed.</p>
</div>

</div>

## Run it

```bash title="One command, structured output"
craik doctor
```

Each check reports a status:

<div className="craik-fields">

<div>
<dt>Status</dt>
<dt><span className="craik-fields__type">Meaning</span></dt>
<dd>What to do</dd>
</div>

<div>
<dt><code>pass</code></dt>
<dt><span className="craik-fields__type">healthy</span></dt>
<dd>Nothing to fix.</dd>
</div>

<div>
<dt><code>warning</code></dt>
<dt><span className="craik-fields__type">soft fail</span></dt>
<dd>Something is misconfigured or expired but not blocking. Read the <code>action</code> field for guidance.</dd>
</div>

<div>
<dt><code>fail</code></dt>
<dt><span className="craik-fields__type">blocking</span></dt>
<dd>Real problem — provider calls will fail, gateway won't start, etc. Fix before proceeding.</dd>
</div>

</div>

## The checks

<div className="craik-grid">

<div>
<h4><code>local_home</code></h4>
<p>Whether the resolved Craik home exists. Run <code>craik home init</code> if missing.</p>
</div>

<div>
<h4><code>local_store</code></h4>
<p>Whether the SQLite store at <code>state/craik.sqlite</code> exists and is readable.</p>
</div>

<div>
<h4><code>memory_backend</code></h4>
<p>Whether a shared Stigmem memory backend is configured (and reachable, if env vars are present).</p>
</div>

<div>
<h4><code>auth_profiles</code></h4>
<p>Whether configured auth profiles can be inspected. No credentials are printed — only structural validity.</p>
</div>

<div>
<h4><code>auth_profile:&lt;id&gt;</code></h4>
<p>Per-profile credential health: env-var presence, token expiry, and local credential-file readability when applicable.</p>
</div>

<div>
<h4><code>gateway_config</code></h4>
<p>Whether a default gateway config is stored. Required before <code>craik setup --enable-gateway</code> can persist a public bind.</p>
</div>

<div>
<h4><code>gateway_prerequisites</code></h4>
<p>Whether daemon-mode prerequisites are present (ports, binaries, dependencies).</p>
</div>

<div>
<h4><code>policy</code></h4>
<p>Whether gateway policy state is inspectable — the envelope is loaded, parsed, and structurally valid.</p>
</div>

</div>

## Reading a profile check

A healthy profile looks like this:

```json title="auth_profile:anthropic:work · pass"
{
  "name": "auth_profile:anthropic:work",
  "status": "pass",
  "summary": "Auth profile anthropic:work is ok.",
  "action": null
}
```

A degraded profile reports a warning **without** printing the secret value:

```json title="auth_profile:anthropic:work · warning"
{
  "name": "auth_profile:anthropic:work",
  "status": "warning",
  "summary": "Auth profile anthropic:work is rejected. secret reference could not resolve",
  "action": "Refresh or replace the credential before running live providers."
}
```

The `action` field is the human-readable next step. Doctor never tells you
*"check your env vars"* and stops there — it names the profile and tells
you what to do.

## A practical first-run checklist

<ol className="craik-steps">
<li>

**Run setup if you haven't.** `craik setup` creates the local home and
default gateway config doctor needs to inspect.

</li>
<li>

**Run `craik doctor`.** Read the output top-to-bottom.

</li>
<li>

**Fix every `fail` first.** Blocking issues prevent the next checks from
being meaningful.

</li>
<li>

**Address warnings.** Expired tokens, missing env vars, unreachable
backends. Use the `action` field as your script.

</li>
<li>

**Re-run doctor until clean.** No noise, no surprises.

</li>
</ol>

## Doctor in CI

`craik doctor` works headlessly. Pipe it into your favorite log collector
or fail your CI job if any check is `fail`:

```bash title="Fail CI on any blocking doctor check"
craik doctor --json | jq -e 'all(.checks[]; .status != "fail")'
```

The `--json` output is stable across releases — the keys are part of the
public contract.

## What's next

<div className="craik-next">

<a href="../authentication/">
<strong>Do</strong>
<span>Authentication &amp; credentials</span>
<small>Add, rotate, or replace credential profiles that doctor flagged.</small>
</a>

<a href="../setup/">
<strong>Do</strong>
<span>Run setup</span>
<small>If doctor reported a missing home, run setup first.</small>
</a>

<a href="../../reference/gateway-daemon/">
<strong>Reference</strong>
<span>Gateway daemon mode</span>
<small>The gateway prerequisites doctor inspects in detail.</small>
</a>

</div>
