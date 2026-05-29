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

Required `data` fields:

| Event | Required fields |
| --- | --- |
| `prompt.submitted` | `prompt_preview` |
| `session.ready` | `transport` |
| `session.status` | `state` |
| `session.history` | `receipts` array |
| `model.changed` | `model` |
| `model.selected` | `backend` or `profile.backend` |
| `run.working` | `backend`, `phase` |
| `run.progress` | `message` |
| `run.started` | `run_id` |
| `tool.used` | `tool`, plus one of `target`, `command`, or `message` |
| `file.changed` | `target`, plus `text` or `message` |
| `approval.requested` | `message`, plus one of `tool`, `target`, or `reason` |
| `approval.resolved` | `approval_id`, `decision` |
| `receipt.created` | `run_id`, `receipt_id` |
| `run.output` | `run_id`, `summary` |
| `run.completed` | `run_id`, `status` |
| `run.event` | `text` or `message` |
| `slash.completed` | `text` or `payload` |
| `slash.catalog` | `commands` array |
| `run.interrupt.requested` | `run_id` |
| `approval.denied` | `message` |
| `error` | `message` |

Provider-specific adapters should preserve provider context when available:
`provider_id`, `provider_family`, `model`, `backend`, and receipt ids. The TUI
must not depend on one provider family; fixtures cover Anthropic Messages,
OpenAI Responses, Gemini, and local OpenAI-compatible models.
