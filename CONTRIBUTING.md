# Contributing to Craik

Craik is an early-stage public project. Contributions are welcome, but the architecture is still forming. For now, open an issue or discussion before starting large design, runtime contract, storage, security, orchestration, or Stigmem integration changes.

## Project Positioning

Craik is an audit-first agent runtime. Before proposing broad product or
architecture changes, read [Positioning](docs/guides/positioning.md) so the
change stays aligned with the runtime's evidence, policy, receipt, and handoff
boundaries.

## Contribution Flow

1. Open or find an issue describing the change.
2. For design-sensitive work, wait for maintainer direction before implementation.
3. Keep changes focused.
4. Include tests or fixtures once code exists.
5. Update docs when behavior, contracts, policy, or user workflow changes.
6. Submit a pull request with a clear description of what changed and how it was validated.

## Commit Signoff

Craik uses the Developer Certificate of Origin (DCO) instead of a contributor license agreement.

By signing off a commit, you certify that you have the right to submit the contribution under this project's license.

Use:

```text
git commit -s
```

Each commit should include a line like:

```text
Signed-off-by: Your Name <you@example.com>
```

The DCO text is available at https://developercertificate.org/.

## Scope Boundaries

Craik owns the durable agent runtime:

- orchestration,
- project case files,
- handoffs,
- capability policy,
- receipts,
- work graph state,
- local runtime state,
- and agent/operator workflows.

Stigmem owns the memory and truth substrate:

- facts,
- provenance,
- scopes,
- trust metadata,
- contradiction tracking,
- federation,
- auth,
- and memory/plugin hooks.

Issues or PRs that belong in Stigmem may be redirected there.

## Quality Expectations

Before merging implementation work, maintainers should expect:

- schema validation tests,
- unit tests for runtime behavior,
- fixture tests for case-file and handoff generation,
- clear error messages,
- no secret leakage in logs or receipts,
- and documentation for new user-visible behavior.

Use [Coverage Reports](docs/guides/coverage.md) when evaluating whether a
change needs additional tests beyond the minimum local validation.

## Security Issues

Do not report security vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md).

## Code of Conduct

Participation in Craik is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
