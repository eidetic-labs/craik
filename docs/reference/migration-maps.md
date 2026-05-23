# Migration maps

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The contracts that describe how adjacent runtime objects and source
fields become Craik surfaces during migration dry-runs.

</div>

<div className="craik-keypoint">

**Importers use maps during dry runs before mutating state.**

Object maps classify each source object as importable, partial, manual,
unsupported, or skipped-secret. Field maps describe the lower-level
field transforms used by importers after an object is accepted.

</div>

## Records

<div className="craik-fields">

<div>
<dt>Contract</dt>
<dt><span className="craik-fields__type">Records</span></dt>
<dd>Fields</dd>
</div>

<div>
<dt><code>MigrationFieldMap</code></dt>
<dt><span className="craik-fields__type">per field</span></dt>
<dd>Source field · target Craik field · support level (<code>supported</code> / <code>partial</code> / <code>unsupported</code>) · transformation notes · redaction requirement · unsupported reason.</dd>
</div>

<div>
<dt><code>MigrationMap</code></dt>
<dt><span className="craik-fields__type">per surface</span></dt>
<dd>Map id · surface · source name · field maps · compatibility notes · policy envelope id · evidence ids · receipt ids.</dd>
</div>

<div>
<dt><code>MigrationObjectMap</code></dt>
<dt><span className="craik-fields__type">per source object</span></dt>
<dd>Source id · source type · target schema · target id · status · required actions · warnings · unsupported reason · skipped secret field paths.</dd>
</div>

<div>
<dt><code>MigrationPlanMap</code></dt>
<dt><span className="craik-fields__type">per source</span></dt>
<dd>Plan id · source name · object maps · policy envelope id · evidence ids · receipt ids · status counts.</dd>
</div>

</div>

## Object Status

<div className="craik-fields">

<div>
<dt>Status</dt>
<dt><span className="craik-fields__type">Meaning</span></dt>
<dd>Operator action</dd>
</div>

<div><dt><code>importable</code></dt><dt><span className="craik-fields__type">automatic</span></dt><dd>Craik has a direct target schema and stable target id.</dd></div>
<div><dt><code>partial</code></dt><dt><span className="craik-fields__type">review</span></dt><dd>Metadata can migrate, but the operator must validate credentials, private facts, unsupported tool calls, or other boundary details.</dd></div>
<div><dt><code>manual</code></dt><dt><span className="craik-fields__type">operator-led</span></dt><dd>The object maps to a Craik surface, but enabling it requires explicit operator review.</dd></div>
<div><dt><code>unsupported</code></dt><dt><span className="craik-fields__type">blocked</span></dt><dd>No target schema is defined; the object remains in the report for manual assessment.</dd></div>
<div><dt><code>skipped-secret</code></dt><dt><span className="craik-fields__type">secret boundary</span></dt><dd>The object contains secret-like fields and waits for secret migration or manual reconfiguration.</dd></div>

</div>

## Covered Surfaces

The default object maps cover agents, profiles and personas, provider
and model config, model aliases, fallback chains, channel accounts and
bindings, skills, memory files, sessions, schedules, sandbox config,
gateway config, and approval/security posture.

## Boundary

<div className="craik-keypoint">

**Secrets stay outside imports.**

Secrets, credentials, private payloads, and local-only paths should be
marked unsupported or redacted — not copied.

</div>

Migration maps preserve policy, evidence, and receipt links so future
importers can explain why a field was transformed, skipped, or
blocked.

## What's next

<div className="craik-next">

<a href="../import-dry-run/">
<strong>Reference</strong>
<span>Import dry-run reports</span>
<small>The dry-run report shape that consumes a map.</small>
</a>

<a href="../adjacent-tool-migration/">
<strong>Reference</strong>
<span>Adjacent-tool migration</span>
<small>The assessment that defines mapping support per concept.</small>
</a>

<a href="../secret-migration-policy/">
<strong>Reference</strong>
<span>Secret migration policy</span>
<small>Why secrets stay outside imports.</small>
</a>

</div>
