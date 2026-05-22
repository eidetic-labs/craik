# Runner capability matrix

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The validated capability and trust profile every runner adapter
exposes. The matrix is the capability-profile input the
[prompt compiler](prompt-compiler.md) consumes, and it is what
governance checks consult to decide whether a side effect is supported,
needs an explicit grant, or must be denied outright.

</div>

<div className="craik-keypoint">

**Conservative by default.**

Every capability defaults to `grant_required=True`. Built-in matrices
only relax the requirement for read-only or structured-result outputs.
Adding a runner that wants broader authority must declare it
explicitly — silence is denial.

</div>

## Shape

The matrix is the `RunnerCapabilityMatrix` model
(`craik.runner_capability_matrix`, version `0.1.0`). It bundles four
things:

<div className="craik-grid">

<div><h4><code>runner</code></h4><p>Stable <code>RunnerMetadata</code> snapshot — id, name, adapter, mode, declared capabilities.</p></div>
<div><h4><code>trust</code></h4><p><code>RunnerTrustProfile</code> — level, boundary statement, default grant posture, receipt and redaction requirements.</p></div>
<div><h4><code>capabilities</code></h4><p>List of <code>RunnerCapability</code> entries, one per named capability.</p></div>
<div><h4><code>policy_notes</code></h4><p>Free-text operator guidance that travels with the matrix.</p></div>

</div>

### `RunnerCapability` entries

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Type</span></dt>
<dd>Meaning</dd>
</div>

<div>
<dt><code>name</code></dt>
<dt><span className="craik-fields__type">str</span></dt>
<dd>The capability identifier — see the canonical set below.</dd>
</div>

<div>
<dt><code>support</code></dt>
<dt><span className="craik-fields__type">"unsupported" · "prompt-handoff" · "supported"</span></dt>
<dd>How the runner provides this capability.</dd>
</div>

<div>
<dt><code>grant_required</code></dt>
<dt><span className="craik-fields__type">bool</span></dt>
<dd>Whether use of the capability needs an explicit grant on top of the trust profile. Defaults to <code>True</code>.</dd>
</div>

<div>
<dt><code>notes</code></dt>
<dt><span className="craik-fields__type">str | None</span></dt>
<dd>Optional per-capability rationale.</dd>
</div>

</div>

### Canonical capability names

<div className="craik-grid">

<div><h4><code>file.read</code></h4></div>
<div><h4><code>file.write</code></h4></div>
<div><h4><code>shell.execute</code></h4></div>
<div><h4><code>network.access</code></h4></div>
<div><h4><code>memory.read</code></h4></div>
<div><h4><code>memory.write</code></h4></div>
<div><h4><code>review.comment</code></h4></div>
<div><h4><code>result.structured</code></h4></div>

</div>

Provider runners additionally publish `model.chat`,
`model.streaming`, `model.tool_calls`, `model.structured_output`, and
`model.usage_metadata` to describe the live calls they perform.

## Built-in matrices

`default_runner_capability_matrices()` ships a conservative built-in
for every runner Craik knows about. `get_runner_capability_matrix(runner_id)`
returns one by id and raises `KeyError` with the known set if the id
is unknown.

<div className="craik-fields">

<div>
<dt>Runner id</dt>
<dt><span className="craik-fields__type">Mode</span></dt>
<dd>Default posture</dd>
</div>

<div>
<dt><code>codex</code></dt>
<dt><span className="craik-fields__type">live</span></dt>
<dd>Medium trust; prompts for approval on side effects; supports the full capability set.</dd>
</div>

<div>
<dt><code>claude</code></dt>
<dt><span className="craik-fields__type">prompt-handoff</span></dt>
<dd>Medium trust; deny-by-default; side effects return through Craik review and receipt flows. No shell or network.</dd>
</div>

<div>
<dt><code>gemini</code></dt>
<dt><span className="craik-fields__type">prompt-handoff</span></dt>
<dd>Low trust; deny-by-default; read- and review-oriented in v0.1.0. No file writes, shell, network, or memory writes.</dd>
</div>

<div>
<dt><code>fixture</code></dt>
<dt><span className="craik-fields__type">fixture</span></dt>
<dd>High trust deterministic in-process adapter for contract tests. Does not widen runtime authority.</dd>
</div>

<div>
<dt><code>provider_openai</code>, <code>provider_openai_responses</code>, <code>provider_openai_chat</code>, <code>provider_local_openai_compatible</code>, <code>provider_local_ollama</code>, <code>provider_local_lm_studio</code>, <code>provider_local_vllm</code></dt>
<dt><span className="craik-fields__type">live</span></dt>
<dd>Provider runtime; medium trust; prompts for approval. Network is supported; filesystem, shell, and memory are unsupported.</dd>
</div>

<div>
<dt><code>provider_anthropic</code>, <code>provider_anthropic_messages</code></dt>
<dt><span className="craik-fields__type">live</span></dt>
<dd>Provider runtime; medium trust; secret references and receipts required for every call.</dd>
</div>

</div>

## Helpers

<div className="craik-fields">

<div>
<dt>Function</dt>
<dt><span className="craik-fields__type">Signature</span></dt>
<dd>What it returns</dd>
</div>

<div>
<dt><code>capability_supported</code></dt>
<dt><span className="craik-fields__type">(matrix, name) -&gt; bool</span></dt>
<dd>Direct support only — <code>True</code> when an entry has <code>support == "supported"</code>. Prompt-handoff and unsupported both return <code>False</code>.</dd>
</div>

<div>
<dt><code>capability_requires_grant</code></dt>
<dt><span className="craik-fields__type">(matrix, name) -&gt; bool</span></dt>
<dd>Reads the entry's <code>grant_required</code>. Unknown capabilities are treated as grant-required.</dd>
</div>

</div>

<div className="craik-keypoint">

**Unknown capability ⇒ grant required.**

`capability_requires_grant` returns `True` for any capability name the
matrix does not enumerate. New capability names cannot quietly bypass
the grant flow — they must be added to the matrix first.

</div>

## What's next

<div className="craik-next">

<a href="../runner-adapter-contract/">
<strong>Reference</strong>
<span>Runner adapter contract</span>
<small>How adapters consume the matrix and surface results.</small>
</a>

<a href="../runner-metadata/">
<strong>Reference</strong>
<span>Runner metadata</span>
<small>The stable identity snapshot embedded in every matrix.</small>
</a>

<a href="../prompt-compiler/">
<strong>Reference</strong>
<span>Prompt compiler</span>
<small>The component that compiles tasks against the runner's capability profile.</small>
</a>

<a href="../../concepts/governance/">
<strong>Read</strong>
<span>Governance</span>
<small>Why capability and grant decisions are receipt-backed.</small>
</a>

</div>
