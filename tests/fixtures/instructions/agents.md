# Agent rules for this project

Use this document to declare invariants every agent must respect.

## Required behaviors

- Always run `pytest -q` before opening a PR.
- Never commit secrets, tokens, or credentials to the repository.
- Prefer editing existing files over creating new files.

## Allowed tools

```bash
# This code block must not appear in extracted statements.
craik run execute --role implementer
```

- Use `craik handoff create` to record a continuation point.
