# Prompt compiler

<p className="craik-meta"><span>3 min read</span><span>Reference</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

`craik prompt compile` turns existing Craik runtime state into a
deterministic, runner-ready prompt. It does not invoke a runner — it
prepares the prompt boundary for adapter previews.

</div>

<div className="craik-keypoint">

**Makes policy visible without granting authority.**

Runners still need explicit grants for side effects. Unsupported
capabilities are not requested. Omitted context, assumptions, and
stale risks are surfaced so a runner can stop or ask, not infer.

</div>

## Command

```sh
craik prompt compile <task-id> --runner <runner-id>
```

<div className="craik-fields">

<div>
<dt>Option</dt>
<dt><span className="craik-fields__type">Type</span></dt>
<dd>Purpose</dd>
</div>

<div>
<dt><code>--runner &lt;runner-id&gt;</code></dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Runner id from <code>craik runners matrix</code>.</dd>
</div>

<div>
<dt><code>--expected-output-schema &lt;schema&gt;</code></dt>
<dt><span className="craik-fields__type">repeatable</span></dt>
<dd>Output schema to request.</dd>
</div>

</div>

The command persists and prints a `craik.compiled_prompt` contract.

## Inputs

<div className="craik-grid">

<div><h4><code>craik.task_request</code></h4></div>
<div><h4>Latest <code>craik.case_file</code></h4></div>
<div><h4><code>craik.policy_envelope</code></h4><p>Or deterministic strict fallback.</p></div>
<div><h4>Task-scoped grants</h4></div>
<div><h4>Selected <code>craik.runner_capability_matrix</code></h4></div>
<div><h4>Context-budget omissions</h4><p>And discovery exclusions.</p></div>
<div><h4>Case-file signals</h4><p>Assumptions · stale risks · contradictions · docs · immutable docs.</p></div>
<div><h4>Governing distillations</h4><p>Approved instruction distillations with provenance annotations and stale-exclusion warnings.</p></div>
<div><h4>Expected output schemas</h4></div>

</div>

## Output

`craik.compiled_prompt` includes:

<div className="craik-grid">

<div><h4>Task · case file · policy · runner ids</h4></div>
<div><h4>Runner mode</h4></div>
<div><h4>Capability grant ids</h4></div>
<div><h4>Expected output schemas</h4></div>
<div><h4>Context omissions</h4></div>
<div><h4>Stop conditions</h4></div>
<div><h4>Distillations</h4><p>Typed ordered items rendered in a separate authoritative section.</p></div>
<div><h4>Distillation warnings</h4><p>Typed warnings for stale governing items excluded from prompt context.</p></div>
<div><h4>Named prompt sections</h4></div>
<div><h4>Rendered prompt text</h4></div>

</div>

<div className="craik-keypoint">

**Stable section order.**

The rendered prompt has stable section order so fixture tests can
compare output across runs.

</div>

The `Distillations` section is present even when no governing
distillations exist. Items are grouped by deterministic category order
and render as `(category) statement [source_id @ path:line-range]`.
Only `governing` distillations are included; stale governing items are
excluded and recorded in `distillation_warnings`.

## What's next

<div className="craik-next">

<a href="../../guides/runner-preview-workflows/">
<strong>Guide</strong>
<span>Runner preview workflows</span>
<small>The full compile, fixture, receipt, and handoff flow.</small>
</a>

<a href="../runner-adapter-contract/">
<strong>Reference</strong>
<span>Runner adapter contract</span>
<small>The contract every compiled-prompt consumer implements.</small>
</a>

<a href="../runner-capability-matrix/">
<strong>Reference</strong>
<span>Runner capability matrix</span>
<small>The capability-profile input the compiler consumes.</small>
</a>

</div>
