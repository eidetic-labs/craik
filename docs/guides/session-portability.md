# Session Portability

<p className="craik-meta"><span>3 min read</span><span>For operators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll do**

Export Craik sessions and inspect adjacent transcript imports without
turning unsupported tool calls into executable authority.

</div>

<div className="craik-keypoint">

**Imports are inert by default.**

Adjacent transcript tool calls are preserved as unsupported-field
evidence. They do not become Craik capabilities, grants, receipts, or
queued actions.

</div>

## Export

Use the portable export format for migration reviews or support
handoffs:

```bash
craik session export-portable agent_session_docs
```

The output uses `schema: craik.session_export`, preserves the source
session id in provenance, strips process-only state such as pid and
endpoint URL, and redacts event metadata before printing.

## Import Preview

Preview a Craik session export or adjacent transcript file:

```bash
craik session import-portable --path ./transcript.json
```

Craik accepts transcript files shaped as either `messages` or
`transcript` arrays. Imported sessions are marked with:

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Value</span></dt>
<dd>Purpose</dd>
</div>

<div><dt><code>recovery_metadata.imported</code></dt><dt><span className="craik-fields__type"><code>true</code></span></dt><dd>Signals that the session did not originate from a live Craik run.</dd></div>
<div><dt><code>recovery_metadata.source_session_id</code></dt><dt><span className="craik-fields__type">original id</span></dt><dd>Preserves source identity for review and rollback.</dd></div>
<div><dt><code>unsupported_fields</code></dt><dt><span className="craik-fields__type">evidence only</span></dt><dd>Lists unsupported tool calls, attachments, and other fields that require adapter work.</dd></div>

</div>

## Unsupported Tool Calls

Unsupported tool calls are never converted into executable authority.
The importer records their source paths and summaries, then creates
redacted `craik.agent_session_event` entries with
`unsupported_tool_call_count` metadata for audit review.

## Validation

Run the portability tests when changing session state, event metadata,
or transcript migration code:

```bash
uv run pytest tests/test_session_portability.py
```

## What's Next

<div className="craik-next">

<a href="../persistent-agent-runtime/">
<strong>Guide</strong>
<span>Persistent agent runtime</span>
<small>How live sessions are created and resumed.</small>
</a>

<a href="../../reference/agent-lifecycle/">
<strong>Reference</strong>
<span>Agent lifecycle</span>
<small>Session state, events, and recovery metadata.</small>
</a>

<a href="../adjacent-runtime-migration/">
<strong>Guide</strong>
<span>Adjacent runtime migration</span>
<small>How portability fits into broader migration reviews.</small>
</a>

</div>
