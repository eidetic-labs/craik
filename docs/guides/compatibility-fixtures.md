# Compatibility Fixtures

<p className="craik-meta"><span>3 min read</span><span>For maintainers</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll do**

Use sanitized adjacent-runtime fixtures to validate migration inspect,
plan, report, and secret-redaction behavior without depending on
private operator state or third-party exports.

</div>

<div className="craik-keypoint">

**Fixtures are public-safe by design.**

Fixture files may include secret-like field names so redaction paths
are exercised, but values must be fake and must never be real provider,
channel, or operator credentials.

</div>

## Fixture Set

The v0.12.0 fixture suite lives under
`tests/fixtures/adjacent_runtime/`:

<div className="craik-fields">

<div>
<dt>Path</dt>
<dt><span className="craik-fields__type">Purpose</span></dt>
<dd>Coverage</dd>
</div>

<div><dt><code>full/</code></dt><dt><span className="craik-fields__type">happy path</span></dt><dd>Provider config, model fallback, profiles/personas, channel bindings, session transcripts, memory files, skills, schedules, sandbox backends, gateway config, and approval posture.</dd></div>
<div><dt><code>invalid/</code></dt><dt><span className="craik-fields__type">error path</span></dt><dd>Malformed JSON handling for deterministic warnings.</dd></div>

</div>

## Validation

Run the fixture tests when changing migration discovery, maps, reports,
or secret handling:

```bash
uv run pytest tests/test_adjacent_runtime_fixtures.py
```

The tests assert that:

<ul>
<li>Full fixtures drive import-plan output for every v0.12.0 migration surface.</li>
<li>Report sections include manual actions, skipped secrets, and security posture changes.</li>
<li>Secret-like fixture values do not appear in serialized output.</li>
<li>Invalid fixtures produce warnings instead of crashing migration inspection.</li>
</ul>

## Adding Fixtures

Add small JSON files that isolate one compatibility concern. Keep
fixtures deterministic, avoid local filesystem paths, and use fake
secret-like values such as `fixture-openai-key` only when testing
redaction.

## What's Next

<div className="craik-next">

<a href="../adjacent-runtime-migration/">
<strong>Guide</strong>
<span>Adjacent runtime migration</span>
<small>Run inspect, plan, report, and import dry-runs.</small>
</a>

<a href="../../reference/migration-reports/">
<strong>Reference</strong>
<span>Migration reports</span>
<small>How fixture output becomes review evidence.</small>
</a>

<a href="../../reference/secret-migration-policy/">
<strong>Reference</strong>
<span>Secret migration policy</span>
<small>Why fixture secrets stay fake and redacted.</small>
</a>

</div>
