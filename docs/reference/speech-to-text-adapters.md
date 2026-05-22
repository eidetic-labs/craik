# Speech-to-text adapter contract

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The three records that compose a speech-to-text adapter result, the
validation rules, and the redaction boundary.

</div>

<div className="craik-keypoint">

**Audio in, transcript out — never raw payloads in receipts.**

Speech-to-text results must not persist raw audio, audio bytes,
waveforms, raw payloads, private transcript metadata, credentials,
tokens, or private local state. Transcript text, segment text, and
metadata all pass through the shared redaction boundary before storage.

</div>

## Records

<div className="craik-fields">

<div>
<dt>Record</dt>
<dt><span className="craik-fields__type">Captures</span></dt>
<dd>Fields</dd>
</div>

<div>
<dt><code>SpeechToTextInputMetadata</code></dt>
<dt><span className="craik-fields__type">input</span></dt>
<dd>Media artifact id · MIME type · duration (ms) · language hint · channel count · redacted metadata.</dd>
</div>

<div>
<dt><code>SpeechToTextTranscript</code></dt>
<dt><span className="craik-fields__type">output</span></dt>
<dd>Transcript text · language · confidence · transcript segments · redacted metadata · redaction status.</dd>
</div>

<div>
<dt><code>SpeechToTextResult</code></dt>
<dt><span className="craik-fields__type">envelope</span></dt>
<dd>Result id · task id · adapter id · status (<code>completed</code> / <code>partial</code> / <code>failed</code>) · input metadata · transcript · errors · policy envelope id · evidence ids · receipt ids · redacted paths · creation timestamp.</dd>
</div>

</div>

## Validation

<div className="craik-grid">

<div><h4>Completed / partial</h4><p>Require a transcript.</p></div>
<div><h4>Failed</h4><p>Require at least one error.</p></div>
<div><h4>All</h4><p>Require policy envelope, evidence, and receipt links.</p></div>
<div><h4>Segment offsets</h4><p>When both present, end ≥ start.</p></div>

</div>

## What's next

<div className="craik-next">

<a href="../voice-posture/">
<strong>Reference</strong>
<span>Voice posture</span>
<small>The decision that authorizes adapter calls.</small>
</a>

<a href="../text-to-speech-adapters/">
<strong>Reference</strong>
<span>Text-to-speech adapters</span>
<small>The output-direction counterpart.</small>
</a>

<a href="../multimodal-artifacts/">
<strong>Reference</strong>
<span>Multimodal artifact references</span>
<small>How adapters cite audio without raw payloads.</small>
</a>

</div>
