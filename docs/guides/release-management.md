# Release Management

<p className="craik-meta"><span>5 min read</span><span>For maintainers</span><span>Updated 2026-05-19</span></p>

<div className="craik-lead">

**What you'll do**

Cut, tag, document, build, and publish a Craik release. Every release
must be installable, documented, and recoverable — `0.x.0` is not a
license to skip discipline.

</div>

<div className="craik-keypoint">

**`0.x.0` MVP, not `1.0.0`.**

The `0.x.0` series can still change contracts between minor releases,
but each published release must pass the same packaging, docs,
quality, and changelog gates as a stable line.

</div>

## Release cadence

<div className="craik-fields">

<div>
<dt>Release line</dt>
<dt><span className="craik-fields__type">Use for</span></dt>
<dd>Notes</dd>
</div>

<div>
<dt><code>0.x.0</code></dt>
<dt><span className="craik-fields__type">capability milestones</span></dt>
<dd>MVP capability increments. Publish when the roadmap gate completes, CI is green, and release notes are reviewed.</dd>
</div>

<div>
<dt><code>0.x.y</code></dt>
<dt><span className="craik-fields__type">patches</span></dt>
<dd>Bug · docs · packaging · compatibility · security fixes.</dd>
</div>

<div>
<dt><code>1.0.0</code></dt>
<dt><span className="craik-fields__type">deferred</span></dt>
<dd>Waits until compatibility promises, upgrade paths, and real-world security soak justify the stability signal.</dd>
</div>

</div>

## Tag Policy

Release tags use `vMAJOR.MINOR.PATCH` — e.g. `v0.1.0` — and must be
signed annotated tags. The embedded tag signature is the release
integrity source of truth; the GitHub Release also carries the public
release signing key as an operator convenience for verification.

<ol className="craik-steps">
<li>Update <code>pyproject.toml</code>, <code>src/craik/__init__.py</code>, and <code>docs/package.json</code>.</li>
<li>Move relevant <code>CHANGELOG.md</code> entries from <code>Unreleased</code> into the target version section.</li>
<li>Run package, docs, quality, and version checks.</li>
<li>Open a release PR that links the completed roadmap issue.</li>
<li>Tag only the merge commit from the release PR with <code>git tag -s vX.Y.Z -m "vX.Y.Z — Release name"</code>.</li>
<li>Push the tag, confirm the GitHub Release is created, and upload the ASCII-armored public signing key as <code>craik-release-signing-key.asc</code>.</li>
</ol>

```sh
git tag -v vX.Y.Z
git push origin vX.Y.Z
gpg --armor --export KEY_FINGERPRINT > craik-release-signing-key.asc
gh release upload vX.Y.Z craik-release-signing-key.asc --repo eidetic-labs/craik --clobber
gh release view vX.Y.Z --repo eidetic-labs/craik --json assets --jq '.assets[].name'
```

`craik-release-signing-key.asc` is a public key export, not a detached
signature. Maintainers must verify that its fingerprint matches the key
reported by `git tag -v vX.Y.Z` before treating the release as complete.
Local signing-key exports are ignored by the repository. Do not commit
`craik-release-signing-key.asc` or any private/secret signing key
export; upload the public key only as a GitHub Release asset.

## Release Notes

Every release needs a GitHub release entry and a matching
`CHANGELOG.md` section. The Publish workflow's `create-github-release`
job extracts the `## X.Y.Z - YYYY-MM-DD` block from `CHANGELOG.md` on
tag push and creates the GitHub Release automatically — title
`Craik X.Y.Z`, body verbatim from the CHANGELOG section, marked latest.
The job fails fast if the CHANGELOG has no section for the tag version,
so the CHANGELOG is the single source of truth for release notes.
After the release entry appears, upload the public release signing key
asset and verify the asset list before announcing the release.

<div className="craik-grid">

<div><h4>User-facing additions and fixes</h4></div>
<div><h4>Migration notes and compatibility risks</h4></div>
<div><h4>Provider · policy · persistence · receipt changes</h4></div>
<div><h4>Known limitations remaining</h4></div>
<div><h4>Links to closing issues and release PR</h4></div>

</div>

## Package verification

Package artifacts are built in CI by the Package workflow, which
checks version consistency, validates release-process docs, builds
`sdist` + wheel artifacts, runs `twine check`, smoke-installs the
wheel, and uploads build artifacts.

Local equivalent:

```sh
python scripts/check_version_consistency.py
python scripts/check_release_readiness.py
python -m build
python -m twine check dist/*
```

## PyPI publishing

<div className="craik-keypoint">

**Tag-driven, OIDC-published.**

Publishing runs only from the immutable release tag (currently
`v0.1.0`) after the workflow verifies tag, package version, and
changelog all agree. Manual dispatch builds and validates artifacts
only.

</div>

Publishing requires the `pypi` Protected Environment:

<div className="craik-grid">

<div><h4>Reviewer approval</h4><p>At least one maintainer.</p></div>
<div><h4>Branch / tag restriction</h4><p>Protected branches and release tags only.</p></div>
<div><h4>Trusted publishing</h4><p>Through GitHub OIDC — not stored PyPI tokens.</p></div>
<div><h4>PyPI publisher config</h4><p>Aligned with <code>eidetic-labs/craik</code>.</p></div>

</div>

## Rollback

PyPI releases are immutable from dependents' perspective. If a bad
release ships:

<ol className="craik-steps">
<li>Publish a patch release with a clear changelog entry and GitHub release note.</li>
<li>Yank only when installation of the bad artifact is actively harmful.</li>
</ol>

## What's next

<div className="craik-next">

<a href="../../security/release-process/">
<strong>Security</strong>
<span>Security release process</span>
<small>The private-coordination overlay for security-sensitive releases.</small>
</a>

<a href="../../release-readiness/">
<strong>Read</strong>
<span>Release readiness</span>
<small>The in-repo readiness gates this procedure verifies.</small>
</a>

<a href="../updating/">
<strong>Guide</strong>
<span>Updating Craik</span>
<small>What operators do after a release publishes.</small>
</a>

</div>
