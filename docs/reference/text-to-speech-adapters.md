# Text-to-speech adapter contract

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The three records that compose a text-to-speech adapter result,
validation rules, and the redaction boundary.

</div>

<div className="craik-keypoint">

**Text in, artifact reference out.**

Text-to-speech results must not persist raw prompts, private payloads,
adapter request payloads, raw generated speech, responses,
credentials, tokens, or private media metadata.

</div>

## Records

<div className="craik-fields">

<div>
<dt>Record</dt>
<dt><span className="craik-fields__type">Captures</span></dt>
<dd>Fields</dd>
</div>

<div>
<dt><code>TextToSpeechRequestMetadata</code></dt>
<dt><span className="craik-fields__type">input</span></dt>
<dd>Redacted text summary · voice id · language · speaking rate · redacted metadata.</dd>
</div>

<div>
<dt><code>TextToSpeechArtifact</code></dt>
<dt><span className="craik-fields__type">output</span></dt>
<dd>Media artifact id · MIME type · duration (ms) · byte count · redacted metadata · redaction status.</dd>
</div>

<div>
<dt><code>TextToSpeechResult</code></dt>
<dt><span className="craik-fields__type">envelope</span></dt>
<dd>Result id · task id · adapter id · status (<code>completed</code> / <code>partial</code> / <code>failed</code>) · request metadata · generated artifact reference · errors · policy envelope id · evidence ids · receipt ids · redacted paths · creation timestamp.</dd>
</div>

</div>

## Validation

<div className="craik-grid">

<div><h4>Completed / partial</h4><p>Require a generated artifact reference.</p></div>
<div><h4>Failed</h4><p>Require at least one error.</p></div>
<div><h4>All</h4><p>Require policy envelope, evidence, and receipt links.</p></div>

</div>

## What's next

<div className="craik-next">

<a href="../voice-posture/">
<strong>Reference</strong>
<span>Voice posture</span>
<small>The decision that authorizes adapter calls.</small>
</a>

<a href="../speech-to-text-adapters/">
<strong>Reference</strong>
<span>Speech-to-text adapters</span>
<small>The input-direction counterpart.</small>
</a>

<a href="../multimodal-artifacts/">
<strong>Reference</strong>
<span>Multimodal artifact references</span>
<small>How adapters cite generated speech without raw payloads.</small>
</a>

</div>
