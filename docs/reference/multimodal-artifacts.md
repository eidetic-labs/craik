# Multimodal artifact references

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

How Craik workflows cite audio, image, video, transcript, canvas,
document, and other media without embedding raw payloads in portable
records.

</div>

<div className="craik-keypoint">

**Locators, not raw media.**

Artifact references store locators — not raw media payloads.
`relative_path` locators must be portable relative paths, never
absolute local filesystem paths.

</div>

## What it records

`MultimodalArtifactReference`:

<div className="craik-grid">

<div><h4>Artifact id</h4></div>
<div><h4>Task id</h4></div>
<div><h4>Kind</h4><p><code>audio</code> · <code>image</code> · <code>video</code> · <code>transcript</code> · <code>canvas</code> · <code>document</code> · <code>other</code>.</p></div>
<div><h4>Locator kind</h4><p><code>artifact_id</code> · <code>content_hash</code> · <code>url</code> · <code>relative_path</code> · <code>external_ref</code>.</p></div>
<div><h4>Locator</h4></div>
<div><h4>Media MIME type</h4></div>
<div><h4>Redacted media metadata</h4></div>
<div><h4>Policy envelope id</h4></div>
<div><h4>Evidence ids</h4></div>
<div><h4>Receipt ids</h4></div>
<div><h4>Redacted paths</h4></div>
<div><h4>Redaction status</h4></div>
<div><h4>Creation timestamp</h4></div>

</div>

## Portability

<div className="craik-fields">

<div>
<dt>Locator</dt>
<dt><span className="craik-fields__type">Use when</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Artifact id / content hash</dt>
<dt><span className="craik-fields__type">survives moves</span></dt>
<dd>Use when a record must survive machine moves.</dd>
</div>

<div>
<dt>URL</dt>
<dt><span className="craik-fields__type">safe to persist</span></dt>
<dd>Only when the URL does not carry credentials or private query parameters.</dd>
</div>

</div>

## Redaction boundary

<div className="craik-keypoint">

**Never raw payloads.**

Media metadata must not persist raw audio, image, video, media bytes,
private metadata, credentials, tokens, or private payloads. Private
media payload fields are replaced with <code>[REDACTED]</code>.

</div>

Artifact references preserve evidence, receipt, and policy links so
later speech, visual workspace, accessibility, and review surfaces can
audit how the artifact entered the workflow.

## What's next

<div className="craik-next">

<a href="../voice-posture/">
<strong>Reference</strong>
<span>Voice posture</span>
<small>The voice surface that consumes audio artifacts.</small>
</a>

<a href="../speech-to-text-adapters/">
<strong>Reference</strong>
<span>Speech-to-text adapters</span>
<small>How audio artifacts become transcripts.</small>
</a>

<a href="../visual-workspace/">
<strong>Reference</strong>
<span>Visual workspace</span>
<small>The canvas surface that renders artifact references.</small>
</a>

</div>
