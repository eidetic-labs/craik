# Security Release Process

<p className="craik-meta"><span>3 min read</span><span>For maintainers</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll find here**

The same package gates as a normal release, with private coordination
before disclosure. Use this when responding to a vulnerability report
or any security-sensitive fix.

</div>

<div className="craik-keypoint">

**Patch first, disclose second.**

No exploit details in public issues, PR titles, changelog drafts, or
generated docs until patched artifacts are available.

</div>

## Security Patch Flow

<ol className="craik-steps">
<li>Triage the report privately and record the impacted versions.</li>
<li>Open a private fix branch or security advisory branch.</li>
<li>Add regression tests that fail without the fix.</li>
<li>Run quality, package, docs, and security checks.</li>
<li>Publish the smallest viable <code>0.x.y</code> patch release.</li>
<li>Publish advisory details after patched artifacts are available.</li>
</ol>

## Private Coordination

<div className="craik-keypoint">

**No public exploit details before patched packages are available.**

Use GitHub Security Advisories or a private maintainer channel for
coordination. Avoid leaking impacted-version detail in public-facing
PR titles or commit messages.

</div>

## Release notes

Security release notes must state:

<div className="craik-grid">

<div><h4>Affected versions</h4></div>
<div><h4>Fixed version</h4></div>
<div><h4>Severity and impact</h4><p>In user terms — not internal jargon.</p></div>
<div><h4>Mitigation</h4><p>For users who cannot upgrade immediately.</p></div>
<div><h4>Exposure scope</h4><p>Whether secrets · receipts · local state · provider calls · or memory writes may have been exposed.</p></div>

</div>

## Disclosure

Disclosure happens only after every gate below is green.

<ol className="craik-steps">
<li>The patch release is published to PyPI.</li>
<li>GitHub release notes are live.</li>
<li>The changelog is updated.</li>
<li>Any required advisory or CVE entry is ready.</li>
</ol>

## Post-Release Verification

<ol className="craik-steps">
<li>Install the patched package from PyPI in a clean environment.</li>
<li>Run the relevant regression tests or smoke workflow.</li>
<li>Confirm that docs and release notes point to the fixed version.</li>
<li>Verify the signed tag with <code>git tag -v vX.Y.Z</code>.</li>
<li>Confirm the GitHub Release includes <code>craik-release-signing-key.asc</code> and that its fingerprint matches the tag-signing key.</li>
</ol>

## What's next

<div className="craik-next">

<a href="../../release-readiness/">
<strong>Read</strong>
<span>Release readiness</span>
<small>The in-repo gates a security patch must still pass.</small>
</a>

<a href="../../guides/release-management/">
<strong>Guide</strong>
<span>Release management</span>
<small>The day-to-day release procedure this overlays on.</small>
</a>

<a href="../../adr/secret-handling/">
<strong>ADR</strong>
<span>0003 · Secret handling</span>
<small>Why receipts and fixtures don't leak credentials by design.</small>
</a>

</div>
