# Secret migration policy

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll find here**

The policy that decides what happens to secret-bearing fields during
migration — the four outcomes, the runtime contract, dry-run behavior,
and receipt expectations.

</div>

<div className="craik-keypoint">

**No implicit copying.**

Migration workflows must never copy secret values from an adjacent
tool, workflow engine, or configuration source into the target
runtime. Unknown fields that contain secret material are blocked by
default. A migration policy cannot authorize secret-value copying.
Optional OS-keyring import is a separate, explicit operator-confirmed
step that writes only to a secure credential backend and records a
redacted receipt.

</div>

## Outcomes

<div className="craik-fields">

<div>
<dt>Outcome</dt>
<dt><span className="craik-fields__type">Use for</span></dt>
<dd>Effect</dd>
</div>

<div>
<dt><code>redact</code></dt>
<dt><span className="craik-fields__type">leakage prevention</span></dt>
<dd>Replace source value with a redaction marker in reports and receipts.</dd>
</div>

<div>
<dt><code>reference</code></dt>
<dt><span className="craik-fields__type">handle only</span></dt>
<dd>Preserve only a non-secret reference identifier (e.g. vault key name).</dd>
</div>

<div>
<dt><code>reconfigure</code></dt>
<dt><span className="craik-fields__type">operator action</span></dt>
<dd>Require the operator to recreate or bind the secret in the target environment.</dd>
</div>

<div>
<dt><code>block</code></dt>
<dt><span className="craik-fields__type">stop</span></dt>
<dd>Stop the field or record from migrating until an explicit policy decision exists.</dd>
</div>

</div>

## Runtime contract

`SecretMigrationPolicy` records source, policy envelope, evidence,
receipts, and field-level rules. Each `SecretMigrationPolicyRule`
defines source field, safe handling mode, reason, dry-run warning, and
whether operator action is required.

`evaluate_secret_migration` returns a `SecretMigrationDecision`:

<div className="craik-fields">

<div>
<dt>Source field</dt>
<dt><span className="craik-fields__type">Outcome</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Non-secret</dt>
<dt><span className="craik-fields__type">allowed</span></dt>
<dd>No secret receipt required.</dd>
</div>

<div>
<dt>Matching secret rule</dt>
<dt><span className="craik-fields__type">one of four</span></dt>
<dd><code>redacted</code> / <code>referenced</code> / <code>operator_reconfiguration_required</code> / <code>blocked</code>.</dd>
</div>

<div>
<dt>Unmapped secret</dt>
<dt><span className="craik-fields__type">blocked</span></dt>
<dd>Default for unknown secret-bearing fields.</dd>
</div>

</div>

<div className="craik-keypoint">

**Always <code>copied_secret_value: false</code>.**

Every secret decision sets <code>copied_secret_value</code> to
<code>false</code>.

</div>

## Dry-run behavior

Import dry-run reports include warnings from the secret migration
policy. Warnings describe the safe handling outcome without exposing
the source value. Public docs and public receipts must not include
local filesystem paths, credentials, private task names, or copied
secret bytes.

## Redacted Inventory

`detect_secret_inventory` scans nested source payloads for secret-like
field names such as `api_key`, `token`, `password`, `secret`, and
`credential`. The inventory records:

<div className="craik-grid">

<div><h4>Source id</h4></div>
<div><h4>Field path</h4><p>For example <code>provider.api_key</code>.</p></div>
<div><h4>Value fingerprint</h4><p>A truncated hash for correlation, not the value.</p></div>
<div><h4>Value length</h4><p>Enough for diagnostics without disclosure.</p></div>

</div>

## Optional keyring import

`migrate_secret_inventory_to_keyring` can write detected values to a
secure OS credential backend only when the operator explicitly confirms
the operation. Without confirmation, the function returns dry-run
receipts and writes nothing. If the current backend is the file
fallback or otherwise not secure, the import is blocked and the
operator must reconfigure credentials manually.

## Receipts

Secret migration receipts record:

<div className="craik-grid">

<div><h4>Policy envelope</h4><p>That governed the decision.</p></div>
<div><h4>Classifying evidence</h4></div>
<div><h4>Safe handling outcome</h4></div>
<div><h4>Required operator action</h4><p>When applicable.</p></div>
<div><h4>Confirmation</h4><p>That no secret value was copied.</p></div>
<div><h4>Keyring target</h4><p>When an explicit secure-backend import was confirmed.</p></div>
<div><h4>Fingerprint</h4><p>For correlation without logging the value.</p></div>

</div>

## What's next

<div className="craik-next">

<a href="../migration-maps/">
<strong>Reference</strong>
<span>Migration maps</span>
<small>The field-level mapping contract this policy gates.</small>
</a>

<a href="../import-dry-run/">
<strong>Reference</strong>
<span>Import dry-run reports</span>
<small>How secret warnings reach operators.</small>
</a>

<a href="../../adr/secret-handling/">
<strong>ADR</strong>
<span>0003 · Secret handling</span>
<small>The references-not-values design.</small>
</a>

</div>
