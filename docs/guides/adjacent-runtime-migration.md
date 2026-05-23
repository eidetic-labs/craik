# Adjacent Runtime Migration

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll do**

Inspect an adjacent agent-runtime export, generate a deterministic
migration plan, and run an import dry-run without modifying the source
runtime or writing Craik state.

</div>

<div className="craik-keypoint">

**Dry-run first.**

The v0.12.0 migration CLI is read-only by default. It discovers JSON
runtime records, maps them to target Craik surfaces, reports skipped
secret-like fields, and keeps raw secret values out of terminal output,
JSON output, receipts, and docs examples.

</div>

## Inspect

Use `inspect` to inventory a source directory or one JSON export file:

```bash
craik migrate inspect --source ./adjacent-runtime --kind agent-runtime
```

The text output shows the source path, record count, record types, and
whether any records contain secret-like fields. JSON output is
available for automation:

```bash
craik migrate inspect --source ./adjacent-runtime --kind agent-runtime --json
```

## Plan

Use `plan` to build a deterministic dry-run report:

```bash
craik migrate plan --source ./adjacent-runtime --kind agent-runtime
```

The plan links each discovered source object to a proposed Craik target
schema and target id. Records containing secret-like fields are marked
with warnings. Unsupported source shapes are sent to manual review.

## Import Dry-Run

`import` defaults to dry-run mode:

```bash
craik migrate import --source ./adjacent-runtime --kind agent-runtime
```

The command produces the same redacted dry-run report as `plan`.
Explicit apply mode is reserved for later migration goals and is
rejected until the full map, report, secret-migration, and fixture
pipeline is complete.

## Secret Handling

Fields with names such as `api_key`, `token`, `password`, `secret`,
`credential`, or `private_key` are treated as secret-like. Craik reports
the field path, not the value. Operators reconfigure those credentials
through the dedicated auth and secret migration flows rather than
copying raw values from adjacent runtime state.

## Validation

Run the focused migration CLI tests after changing this surface:

```bash
uv run pytest tests/test_adjacent_runtime_migration_cli.py
uv run python scripts/generate_cli_reference.py --check
```

## What's Next

<div className="craik-next">

<a href="../../reference/import-dry-run/">
<strong>Reference</strong>
<span>Import dry-run</span>
<small>The report contract used by migration plans.</small>
</a>

<a href="../../reference/migration-maps/">
<strong>Reference</strong>
<span>Migration maps</span>
<small>How source fields map into Craik target surfaces.</small>
</a>

<a href="../../reference/secret-migration-policy/">
<strong>Reference</strong>
<span>Secret migration policy</span>
<small>How secret-like source material is handled.</small>
</a>

</div>
