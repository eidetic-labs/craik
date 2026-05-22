# Desktop Companion

<p className="craik-meta"><span>4 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The desktop companion MVP — required controls, local-vs-remote posture,
menu actions, approval notification links, and the CLI surfaces that
native tray/menu-bar shells can call.

</div>

<div className="craik-keypoint">

**Governed surface, not background automation.**

A desktop companion may present status, notifications, and controlled
actions — it must not become an unreviewed background automation
channel.

</div>

## What It Records

<div className="craik-grid">

<div><h4>Surface id</h4></div>
<div><h4>Support level</h4><p><code>supported</code> · <code>experimental</code> · <code>deferred</code>.</p></div>
<div><h4>Operator consent requirement</h4></div>
<div><h4>Policy context preservation</h4></div>
<div><h4>Evidence link preservation</h4></div>
<div><h4>Receipt requirement</h4></div>
<div><h4>Local storage encryption posture</h4></div>
<div><h4>Secret storage posture</h4></div>
<div><h4>Notification controls</h4></div>
<div><h4>Background action controls</h4></div>
<div><h4>Documentation reference</h4></div>

</div>

## Decision rules

<div className="craik-decision">

<div>
<h4>Allowed (supported)</h4>
<ul>
<li>Explicit operator consent</li>
<li>Encrypted local storage</li>
<li>Notification controls</li>
<li>Background action controls</li>
<li>Policy context</li>
<li>Evidence links</li>
<li>Receipts</li>
</ul>
</div>

<div>
<h4>Blocked</h4>
<ul>
<li>Stores secrets</li>
<li>Skips operator consent</li>
<li>Unencrypted local storage</li>
<li>Omits notification controls</li>
<li>Uncontrolled background actions</li>
<li>Loses policy or evidence links</li>
<li>Skips receipts</li>
</ul>
</div>

</div>

Experimental surfaces require explicit review. Deferred surfaces are
not available as product surfaces.

## MVP Surface

`craik desktop status` returns the companion snapshot:

```sh
craik desktop status
```

The snapshot includes the governed surface status, local dashboard URL,
latest gateway runtime state, provider/auth readiness, local-vs-remote
posture, warnings, and deterministic menu actions.

## Menu Actions

```sh
craik desktop menu
craik desktop action open_dashboard
craik desktop action gateway_status
craik desktop action gateway_start
craik desktop action gateway_stop
craik desktop action gateway_restart
craik desktop action doctor
craik desktop action update_check
```

Gateway start, stop, and restart actions are marked as requiring
confirmation. The MVP exposes commands and posture for a native wrapper
to call; it does not silently execute background actions.

## Approval Notifications

Native notification wrappers can request a redacted approval
notification fixture:

```sh
craik desktop notify-approval approval_123 model.chat "provider request"
```

The payload includes a local dashboard deep link to `/approvals` and
redacts secret-like target text before it reaches notification logs or
crash reports.
Future desktop URL-scheme handlers such as `craik://` must be
review-only entrypoints. They may open local dashboard or approval
detail views, but they must not approve, deny, submit credentials, or
trigger mutating runtime actions directly from a URL.

## Current Posture

<div className="craik-keypoint">

**Supported MVP surface.**

The shipped MVP supports status panels, deterministic menu actions,
local dashboard launch, gateway command surfacing, provider/auth health
summary, approval notification deep links, doctor, and update-check
payloads. Always-on automation, secret caching, uncontrolled background
actions, and private local-state synchronization remain blocked.

</div>

## What's next

<div className="craik-next">

<a href="../mobile-companion/">
<strong>Reference</strong>
<span>Mobile companion</span>
<small>The mobile counterpart.</small>
</a>

<a href="../accessibility-requirements/">
<strong>Reference</strong>
<span>Accessibility requirements</span>
<small>The accessibility floor every companion respects.</small>
</a>

<a href="../../guides/companion-app-security/">
<strong>Guide</strong>
<span>Companion app security</span>
<small>The author-facing security posture.</small>
</a>

</div>
