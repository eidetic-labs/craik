# Updating Craik

<p className="craik-meta"><span>2 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll do**

Read the non-mutating update guidance `craik update` prints, then run
the recommended manual flow. `craik update` never modifies the
installed package, source checkouts, remote release metadata, or local
state.

</div>

<div className="craik-keypoint">

**Non-mutating by default.**

Update guidance is informational. Craik will not silently upgrade
itself or migrate local state.

</div>

## Run it

```sh
craik update
```

For automation, use check mode:

```sh
craik update --check
```

Output covers:

<div className="craik-grid">

<div><h4>Installed version</h4></div>
<div><h4>Supported Python range</h4></div>
<div><h4>Local store migration compatibility</h4></div>
<div><h4>Contract compatibility</h4></div>
<div><h4>Manual update steps</h4></div>
<div><h4>Mode</h4><p><code>check</code> for automation, <code>manual</code> for operator guidance.</p></div>
<div><h4>Boundaries</h4><p>For what Craik will not do automatically.</p></div>

</div>

## Recommended flow

<ol className="craik-steps">
<li>Review release notes and migration notes.</li>
<li>Run <code>craik doctor</code>.</li>
<li>Update Craik with the package manager or source checkout that installed it.</li>
<li>Run <code>craik doctor</code> again.</li>
<li>Run project validation before starting the gateway.</li>
</ol>

<div className="craik-keypoint">

**Patch first, then minor.**

For published <code>0.x.y</code> patch releases, prefer the newest
patch in the current minor line unless release notes call for a
migration. Capability-bearing <code>0.x.0</code> upgrades are minor
compatibility events until Craik reaches <code>1.0.0</code>.

</div>

Future migration commands may add explicit local-state migrations, but
update guidance remains non-mutating by default.

## What's next

<div className="craik-next">

<a href="../doctor/">
<strong>Guide</strong>
<span>Doctor diagnostics</span>
<small>The health check to run before and after an upgrade.</small>
</a>

<a href="../local-store-migrations/">
<strong>Guide</strong>
<span>Local store migrations</span>
<small>How forward-only migrations run during <code>LocalStore.initialize()</code>.</small>
</a>

<a href="../release-management/">
<strong>Guide</strong>
<span>Release management</span>
<small>How the releases you're consuming are produced.</small>
</a>

</div>
