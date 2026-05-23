# Translation Contribution

<p className="craik-meta"><span>2 min read</span><span>For contributors</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll do**

Add or review Craik translations without weakening policy, evidence,
receipt, redaction, or schema semantics.

</div>

## Rules

<ol className="craik-steps">
<li>Add translations under stable message ids in `craik.runtime.i18n`.</li>
<li>Do not translate schema ids, capability slugs, status slugs, or policy profile names.</li>
<li>Keep remediation text actionable and equivalent to the English source.</li>
<li>Add tests for fallback behavior and at least one localized output path.</li>
<li>Update public docs when a new localized surface is added.</li>
</ol>

## Review Checklist

<ul>
<li>Missing translations fall back to English.</li>
<li>Machine-readable JSON remains stable across locales.</li>
<li>Localized text does not expose secrets or local-only paths.</li>
<li>Examples still use safe fixture values.</li>
</ul>
