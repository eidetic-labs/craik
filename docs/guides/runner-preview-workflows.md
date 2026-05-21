# Runner preview workflows

<p className="craik-meta"><span>6 min read</span><span>For contributors</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll do**

Walk through Craik's v0.1.0 runner-preview surface: context discovery
and case files · policy-aware prompt compilation · fixture or
prompt-handoff execution · receipt and handoff metadata capture. The
preview validates the runner boundary before live side effects are
trusted.

</div>

<div className="craik-keypoint">

**Preview adapters do not grant authority.**

Fixture mode, prompt handoff, and governed provider execution are the
expected paths. Side effects still require explicit capability grants.

</div>

## Workflow

<ol className="craik-steps">
<li>Register or select a project.</li>
<li>Create a task with explicit scope, constraints, and expected outputs.</li>
<li>Build the task case file.</li>
<li>Compile a runner-targeted prompt.</li>
<li>Build a runner adapter request from the compiled prompt.</li>
<li>Run the preview adapter in fixture or prompt-handoff mode.</li>
<li>Persist receipts and handoffs from the normalized result when appropriate.</li>
<li>Review runner metadata, policy boundaries, omitted context, and diagnostics before treating output as evidence.</li>
</ol>

## Context and overrides

Case files decide what context reaches the prompt. Configure project
docs, immutable paths, discovery includes, and discovery excludes
before building the case file.

<div className="craik-keypoint">

**Omissions are stop-or-ask conditions.**

Compiled prompts surface omitted or excluded context in
`context_omissions`. Runners must treat omissions as stop-or-ask
conditions — not as evidence that omitted material is irrelevant.

</div>

## Compile a prompt

Use the runner capability matrix to choose the runner:

```sh
craik runners matrix
craik runners matrix --runner codex
```

Compile the prompt:

```sh
craik prompt compile <task-id> --runner codex
craik prompt compile <task-id> --runner claude
craik prompt compile <task-id> --runner gemini
```

The compiler persists a `craik.compiled_prompt` and includes:

<div className="craik-grid">

<div><h4>Task and policy boundaries</h4></div>
<div><h4>Capability grants</h4></div>
<div><h4>Runner trust profile</h4></div>
<div><h4>Unsupported / prompt-handoff capabilities</h4></div>
<div><h4>Context omissions</h4></div>
<div><h4>Governing distillations</h4><p>Rendered as their own authoritative section with provenance annotations.</p></div>
<div><h4>Expected output schemas</h4></div>
<div><h4>Stop conditions</h4></div>

</div>

## Run a preview adapter

Each preview adapter implements the same runtime shape:

```python
from craik.runtime.codex_adapter import CodexRunnerAdapter, request_from_compiled_prompt

adapter = CodexRunnerAdapter()
request = request_from_compiled_prompt(compiled_prompt, adapter=adapter)
result = adapter.run(request)
```

<div className="craik-grid">

<div><h4><code>craik.runtime.codex_adapter</code></h4></div>
<div><h4><code>craik.runtime.claude_adapter</code></h4></div>
<div><h4><code>craik.runtime.gemini_adapter</code></h4></div>

</div>

Fixture outcomes are controlled through request context:

```python
request = request_from_compiled_prompt(
    compiled_prompt,
    context={
        "fixture_status": "blocked",
        "blocked_reason": "missing approval for shell.execute",
    },
)
```

Supported fixture statuses: `completed` · `blocked` · `failed` · `partial`.

## Result shape

Adapters return `craik.runner_adapter_result`.

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Purpose</span></dt>
<dd>Contents</dd>
</div>

<div>
<dt><code>outputs.prompt_handoff</code></dt>
<dt><span className="craik-fields__type">handoff bundle</span></dt>
<dd>Compiled prompt + runner id.</dd>
</div>

<div>
<dt><code>outputs.receipt_inputs</code></dt>
<dt><span className="craik-fields__type">receipt drafts</span></dt>
<dd>For granted capabilities.</dd>
</div>

<div>
<dt><code>outputs.handoff_input</code></dt>
<dt><span className="craik-fields__type">handoff bundle</span></dt>
<dd>Fields suitable for handoff creation.</dd>
</div>

<div>
<dt><code>outputs.runner_metadata</code></dt>
<dt><span className="craik-fields__type">audit</span></dt>
<dd>Stable runner · adapter · trust · capability metadata.</dd>
</div>

<div>
<dt><code>diagnostics</code></dt>
<dt><span className="craik-fields__type">surface notes</span></dt>
<dd>Fixture and prompt-handoff limitations or runner diagnostics.</dd>
</div>

</div>

Receipts and handoffs preserve stable runner metadata so future agents
can see which adapter, version, execution mode, trust profile, and
capability profile were involved. Runner-specific fields remain nested
and redacted.

## Policy boundary

<div className="craik-keypoint">

**Preview adapters do not grant authority.**

Side effects require explicit capability grants. Unsupported
capabilities are blocked. Prompt-handoff side effects must return
through Craik review. Fixture results are deterministic test outputs,
not proof of live execution. Receipt metadata describes runner context
but does not replace concrete side-effect receipts.

</div>

## Smoke-test checklist

<ol className="craik-steps">
<li>Run <code>craik runners matrix --runner &lt;id&gt;</code> and confirm the trust profile.</li>
<li>Run <code>craik prompt compile &lt;task-id&gt; --runner &lt;id&gt;</code>.</li>
<li>Build a request with the matching adapter module.</li>
<li>Run one <code>completed</code>, one <code>blocked</code>, and one <code>failed</code> fixture path.</li>
<li>Confirm <code>outputs.runner_metadata</code>, <code>outputs.receipt_inputs</code>, and <code>outputs.handoff_input</code> are present.</li>
<li>Confirm secrets in runner-specific metadata are redacted.</li>
<li>Run the project validation command from <a href="../development/">Development checks</a>.</li>
</ol>

## What's next

<div className="craik-next">

<a href="../../reference/runner-adapter-contract/">
<strong>Reference</strong>
<span>Runner adapter contract</span>
<small>The shipped contract every preview adapter implements.</small>
</a>

<a href="../../reference/prompt-compiler/">
<strong>Reference</strong>
<span>Prompt compiler</span>
<small>The compiler output shape that drives preview adapters.</small>
</a>

<a href="../single-agent-fixture-loop/">
<strong>Guide</strong>
<span>Single-agent fixture loop</span>
<small>Compose preview adapters into the full loop boundary.</small>
</a>

</div>
