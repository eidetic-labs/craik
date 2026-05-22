# Companion app security

<p className="craik-meta"><span>4 min read</span><span>For integrators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The security posture for companion surfaces — desktop, mobile, voice,
multimodal. Companion surfaces are governed operator surfaces. They
expose status, review notifications, and explicit operator-triggered
actions, but must never become unreviewed background automation
channels.

</div>

<div className="craik-keypoint">

**Companion surfaces don't store secrets.**

If a companion action needs authority, it references an existing
policy envelope, capability grant, or approval record — never cached
credentials.

</div>

## Read alongside

<div className="craik-grid">

<div><h4><a href="../../reference/desktop-companion/">Desktop companion</a></h4></div>
<div><h4><a href="../../reference/mobile-companion/">Mobile companion</a></h4></div>
<div><h4><a href="../../reference/voice-posture/">Voice posture</a></h4></div>
<div><h4><a href="../../reference/multimodal-artifacts/">Multimodal artifacts</a></h4></div>
<div><h4><a href="../../reference/accessibility-requirements/">Accessibility requirements</a></h4></div>

</div>

## Credential handling

<div className="craik-decision">

<div>
<h4>Companion records may preserve</h4>
<ul>
<li>Policy envelope ids</li>
<li>Capability grant ids</li>
<li>Approval receipt ids</li>
<li>Evidence ids</li>
<li>Task ids</li>
<li>Sanitized summaries</li>
</ul>
</div>

<div>
<h4>Companion records must NOT preserve</h4>
<ul>
<li>Raw tokens · passwords · API keys</li>
<li>Private payloads</li>
<li>Unredacted prompts</li>
<li>Credential-bearing URLs</li>
</ul>
</div>

</div>

## Local storage

Desktop and mobile companion state must be encrypted when persisted.
Stored records must be minimal and reconstructable from durable Craik
records.

<div className="craik-decision">

<div>
<h4>Allowed companion state</h4>
<ul>
<li>User-visible notification ids</li>
<li>Last-viewed task ids</li>
<li>Display preferences</li>
<li>Redacted artifact references</li>
<li>Receipt ids for recorded actions</li>
</ul>
</div>

<div>
<h4>Prohibited companion state</h4>
<ul>
<li>Secrets or credentials</li>
<li>Raw multimodal payloads</li>
<li>Private local workspace paths</li>
<li>Unredacted transcripts</li>
<li>Generated speech payloads</li>
<li>Raw canvas state exposing private content</li>
</ul>
</div>

</div>

## Notifications

Companion notifications require operator controls — operators must be
able to disable, filter, or defer notifications. Notifications link
back to reviewable Craik records instead of embedding private content.

<div className="craik-fields">

<div>
<dt>Field</dt>
<dt><span className="craik-fields__type">Status</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt>Task id</dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Always present.</dd>
</div>

<div>
<dt>Short sanitized summary</dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd>Redacted before display.</dd>
</div>

<div>
<dt>Severity or review state</dt>
<dt><span className="craik-fields__type">required</span></dt>
<dd></dd>
</div>

<div>
<dt>Receipt or evidence id</dt>
<dt><span className="craik-fields__type">when available</span></dt>
<dd></dd>
</div>

<div>
<dt>Raw prompts · secrets · transcripts · media · local-only paths</dt>
<dt><span className="craik-fields__type">never</span></dt>
<dd>Prohibited in notification payloads.</dd>
</div>

</div>

## Approvals and actions

<div className="craik-keypoint">

**Operator intent is required.**

Companion-triggered actions require explicit operator intent.
Background actions are disabled unless a later product surface defines
a reviewable action queue with policy and receipt guarantees.

</div>

Every companion-triggered action preserves:

<div className="craik-grid">

<div><h4>Actor identity</h4></div>
<div><h4>Policy envelope id</h4></div>
<div><h4>Evidence ids</h4></div>
<div><h4>Receipt id</h4></div>
<div><h4>Action summary</h4></div>
<div><h4>Result status</h4></div>

</div>

Mobile offline action queues are deferred unless they can guarantee
receipts, ordering, replay protection, and operator review before side
effects occur.

## Redaction boundary

Companion surfaces use the same redaction posture as other Craik
runtime records — preserve ids and summaries, not raw payloads.

**Redact:** secrets and credentials · local-only paths · private
prompts · raw transcripts · raw audio, image, video, or generated
speech payloads · raw canvas state · private notification payloads.

## Validation

```sh
uv run --extra dev pytest tests/test_desktop_companion.py tests/test_mobile_companion.py
uv run --extra dev pytest tests/test_voice_posture.py tests/test_multimodal_artifacts.py
uv run --extra dev pytest tests/test_accessibility.py tests/test_docs.py
```

Expected: `passed`.

For the desktop companion MVP, also validate the CLI wrappers:

```sh
craik desktop status
craik desktop menu
craik desktop action open_dashboard
craik desktop notify-approval approval_123 model.chat "provider request"
```

The output must remain redacted, local-vs-remote posture must be
explicit, and gateway start/stop/restart actions must require
confirmation rather than running silently in the background.

## What's next

<div className="craik-next">

<a href="../../reference/desktop-companion/">
<strong>Reference</strong>
<span>Desktop companion</span>
<small>The shipped desktop surface decision and contract.</small>
</a>

<a href="../../reference/voice-posture/">
<strong>Reference</strong>
<span>Voice posture</span>
<small>The shipped voice-adapter contract.</small>
</a>

<a href="../../reference/accessibility-requirements/">
<strong>Reference</strong>
<span>Accessibility requirements</span>
<small>The minimum accessibility floor across companion surfaces.</small>
</a>

</div>
