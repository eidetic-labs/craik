# Accessibility requirements

<p className="craik-meta"><span>2 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The `AccessibilityRequirements` contract that keeps multimodal and
companion surfaces usable without relying on a single input mode,
visual presentation, or motion pattern.

</div>

<div className="craik-keypoint">

**Evidence, not approval.**

Accessibility checks do not approve product surfaces by themselves.
They provide evidence for the desktop, mobile, voice, and visual
workspace decisions.

</div>

## What it records

<div className="craik-grid">

<div><h4>Surface kind</h4><p><code>desktop_companion</code> · <code>mobile_companion</code> · <code>visual_workspace</code> · <code>voice</code>.</p></div>
<div><h4>Keyboard navigation</h4></div>
<div><h4>Screen reader labels</h4></div>
<div><h4>Reduced motion support</h4></div>
<div><h4>Contrast checks</h4></div>
<div><h4>Transcript availability</h4></div>
<div><h4>Caption availability</h4></div>
<div><h4>Notification controls</h4></div>
<div><h4>Policy envelope id</h4></div>
<div><h4>Evidence ids</h4></div>
<div><h4>Receipt ids</h4></div>

</div>

`accessibility_check` returns a reviewable result with missing
requirement names when a surface does not meet the baseline.

## Baseline

Companion and visual workspace surfaces provide:

<ol className="craik-steps">
<li>Complete keyboard navigation for controls.</li>
<li>Meaningful labels for screen readers.</li>
<li>Reduced-motion behavior for animated or live surfaces.</li>
<li>Contrast checks for text, controls, and status indicators.</li>
<li>Transcripts for voice or audio interactions.</li>
<li>Captions for video or generated speech playback.</li>
<li>Operator controls for notifications.</li>
</ol>

<div className="craik-keypoint">

**Audit trail required.**

Accessibility reviews preserve policy, evidence, and receipt links so
the decision can be audited later.

</div>

## What's next

<div className="craik-next">

<a href="../desktop-companion/">
<strong>Reference</strong>
<span>Desktop companion</span>
<small>The desktop surface decision this evidence feeds.</small>
</a>

<a href="../mobile-companion/">
<strong>Reference</strong>
<span>Mobile companion</span>
<small>The mobile surface decision.</small>
</a>

<a href="../visual-workspace/">
<strong>Reference</strong>
<span>Visual workspace</span>
<small>The live workspace decision.</small>
</a>

</div>
