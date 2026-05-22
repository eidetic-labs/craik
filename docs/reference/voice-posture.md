# Voice input and output posture

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The `VoiceSurface` contract — how voice input and output is bounded
as a governed operator surface, not an always-on assistant layer.

</div>

<div className="craik-keypoint">

**No always-on assistant behavior.**

Voice support is a governed extension point. Always-on or
raw-audio-retaining behavior is deferred.

</div>

## What it records

<div className="craik-grid">

<div><h4>Surface id</h4></div>
<div><h4>Direction</h4><p><code>input</code> · <code>output</code> · <code>bidirectional</code>.</p></div>
<div><h4>Support level</h4><p><code>supported</code> · <code>experimental</code> · <code>deferred</code>.</p></div>
<div><h4>Consent requirement</h4></div>
<div><h4>Policy context preservation</h4></div>
<div><h4>Evidence link preservation</h4></div>
<div><h4>Receipt requirement</h4></div>
<div><h4>Transcript redaction</h4></div>
<div><h4>Media metadata redaction</h4></div>
<div><h4>Raw audio payload persistence</h4></div>
<div><h4>Documentation reference</h4></div>

</div>

## Decision rules

<div className="craik-decision">

<div>
<h4>Allowed (supported)</h4>
<ul>
<li>Explicit operator consent</li>
<li>Transcript redaction</li>
<li>Media metadata redaction</li>
<li>Policy context</li>
<li>Evidence links</li>
<li>Receipts</li>
</ul>
</div>

<div>
<h4>Blocked</h4>
<ul>
<li>Persists raw audio payloads</li>
<li>Skips operator consent</li>
<li>Omits transcript or media metadata redaction</li>
<li>Loses policy or evidence links</li>
<li>Skips receipts</li>
</ul>
</div>

</div>

## Redaction boundary

Voice records preserve ids and summaries — never raw audio or private
transcripts.

<div className="craik-decision">

<div>
<h4>Safe to record</h4>
<ul>
<li>Transcript id</li>
<li>Media artifact reference id</li>
<li>Evidence ids</li>
<li>Receipt ids</li>
<li>Policy envelope id</li>
<li>Adapter id</li>
<li>Redaction status</li>
<li>Short review summary</li>
</ul>
</div>

<div>
<h4>Never record</h4>
<ul>
<li>Raw audio payloads</li>
<li>Credentials</li>
<li>Private prompts</li>
<li>Private transcripts</li>
<li>Local-only paths</li>
<li>Unredacted generated speech metadata</li>
</ul>
</div>

</div>

## What's next

<div className="craik-next">

<a href="../speech-to-text-adapters/">
<strong>Reference</strong>
<span>Speech-to-text adapters</span>
<small>The input-direction adapter contract.</small>
</a>

<a href="../text-to-speech-adapters/">
<strong>Reference</strong>
<span>Text-to-speech adapters</span>
<small>The output-direction adapter contract.</small>
</a>

<a href="../accessibility-requirements/">
<strong>Reference</strong>
<span>Accessibility requirements</span>
<small>The accessibility floor every voice surface respects.</small>
</a>

</div>
