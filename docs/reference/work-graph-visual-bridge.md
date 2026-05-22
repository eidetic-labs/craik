# Work graph → visual workspace bridge

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The bridge that projects `craik.work_graph_export` records into
portable visual workspace records — and the boundary that keeps the
projection read-only.

</div>

<div className="craik-keypoint">

**Read-only projection.**

The bridge does not mutate the work graph. It creates a read-only
projection that a visual surface can render while preserving source
node and edge ids.

</div>

## Records

<div className="craik-fields">

<div>
<dt>Record</dt>
<dt><span className="craik-fields__type">Captures</span></dt>
<dd>Fields</dd>
</div>

<div>
<dt><code>WorkGraphVisualWorkspace</code></dt>
<dt><span className="craik-fields__type">projection</span></dt>
<dd>Source graph id · task id · visual nodes · visual edges · policy envelope ids · evidence ids · receipt ids · redacted paths · redaction status.</dd>
</div>

<div>
<dt><code>VisualWorkspaceNode</code></dt>
<dt><span className="craik-fields__type">node</span></dt>
<dd>Visual node id · source work-graph node id · type · label · deterministic layout coordinates · redacted metadata.</dd>
</div>

<div>
<dt><code>VisualWorkspaceEdge</code></dt>
<dt><span className="craik-fields__type">edge</span></dt>
<dd>Visual edge id · source work-graph edge id · type · visual source node id · visual target node id · redacted metadata.</dd>
</div>

</div>

## Boundary

<div className="craik-keypoint">

**Portable visual state.**

The bridge uses deterministic layout hints instead of storing
editor-specific canvas state. Consumers can apply their own layout
while keeping the source links.

</div>

## Redaction

Node labels and metadata pass through shared redaction. The visual
workspace record preserves evidence, receipt, and policy references
without copying raw private payloads.

## What's next

<div className="craik-next">

<a href="../visual-workspace/">
<strong>Reference</strong>
<span>Visual workspace decision</span>
<small>Whether a surface may render or interact with the projection.</small>
</a>

<a href="../graph-export/">
<strong>Reference</strong>
<span>Graph export</span>
<small>The source record this bridge projects.</small>
</a>

<a href="../multimodal-artifacts/">
<strong>Reference</strong>
<span>Multimodal artifact references</span>
<small>How visual surfaces cite media without raw payloads.</small>
</a>

</div>
