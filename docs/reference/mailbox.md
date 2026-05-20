# Agent Mailbox

The agent mailbox is the receipt-backed coordination channel for one
agent role to ask another agent role for review, status, decisions, or
handoff context.

## CLI

```bash
craik agent-message send \
  --task-id task_123 \
  --from-agent agent:orchestrator \
  --to-agent agent:verifier \
  --subject "Review patch" \
  --body "Please verify the changed files." \
  --run-id run_123 \
  --from-role-id role_orchestrator \
  --from-role-kind orchestrator

craik agent-message receive agent_message_123 --received-by agent:verifier
```

`send` requires `--run-id`. Craik loads the run and verifies that the
requested `--from-agent`, `--from-role-id`, and `--from-role-kind`
match the sender run before persisting the message. The sender string
is not trusted on its own.

## Receipts

Mailbox sends create `agent.message.send` receipts. Receives create
`agent.message.receive` receipts. Message IDs are stable for the first
message with a subject and receive numeric suffixes for repeated
same-subject messages so history is not silently overwritten.

## Prompt Boundary

Mailbox bodies are untrusted peer-agent content. Downstream prompts
must treat them as evidence to inspect, not instructions to obey.
