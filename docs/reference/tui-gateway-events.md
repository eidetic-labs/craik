# TUI Gateway Events

The Rust/Ratatui TUI consumes newline-delimited JSON events from
`craik tui-backend --jsonl`. Python backend emitters must validate events before
writing them to stdout, and the Rust TUI validates every received event before
rendering it.

The machine-readable contract lives at
`src/craik/runtime/backend/gateway_event_contract.json`. Python and Rust
validators both read that artifact; docs and fixtures should be updated with it
when the event surface changes.

Each event is a JSON object with:

- `type`: one of the supported event names below.
- `created_at`: ISO-8601 timestamp.
- `run_id`: run identifier when the event belongs to a run, otherwise `null`.
- `task_id`: task identifier when available, otherwise `null`.
- `data`: event-specific JSON object.

Required fields:

| Event | Required fields |
| --- | --- |
| `prompt.submitted` | prompt_preview string |
| `approval.resolved` | approval_id string; decision string |
| `session.ready` | transport string |
| `session.status` | state string |
| `session.history` | receipts array |
| `slash.completed` | one of text or payload |
| `slash.catalog` | commands array |
| `model.changed` | model string |
| `run.interrupt.requested` | run_id string |
| `run.started` | run_id string |
| `run.working` | backend string; phase string |
| `run.progress` | message string |
| `run.event` | one of text or message |
| `tool.used` | tool string; one of target, command, or message |
| `file.changed` | target string; one of text or message |
| `approval.requested` | message string; one of tool, target, or reason |
| `approval.denied` | message string |
| `model.selected` | one of backend or profile.backend |
| `receipt.created` | run_id string; receipt_id string |
| `run.output` | run_id string; summary string |
| `run.completed` | run_id string; status string |
| `error` | message string |

Provider-specific adapters should preserve provider context when available:
`provider_id`, `provider_family`, `model`, `backend`, and receipt ids. The TUI
must not depend on one provider family; fixtures cover Anthropic Messages,
OpenAI Responses, Gemini, and local OpenAI-compatible models.
