# Role Dispatch

Role dispatch maps a task to a specialist role and provider runner.
Craik ships built-in roles for orchestrator, implementer, verifier,
adversarial reviewer, policy reviewer, docs reviewer, memory curator,
and adjudicator.

## Policy Requirements

Role dispatch is policy-bound. A policy must explicitly allow role IDs
or role kinds through `allowed_agent_role_ids` or
`allowed_agent_role_kinds`; a stock strict envelope does not permit all
roles by default.

Runner overrides are also policy-bound. Passing a caller-supplied
runner requires the `role.runner.override` capability in the policy
envelope.

## Receipts

Dispatch decisions produce `role.dispatch` receipts naming the role,
role kind, runner id, and runner mode. Denied receipts record the
missing allowlist, denied role, or capability conflict.
