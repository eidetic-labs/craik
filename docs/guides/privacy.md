# Privacy and Data Flow

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-23</span></p>

<div className="craik-lead">

**What you'll understand**

Craik keeps its own telemetry surface at zero, keeps local runtime evidence on
your machine, and sends prompt content only to the provider or local model you
configure for the run.

</div>

## Data Flow Summary

| Category | Where it goes | Operator control |
|---|---|---|
| craik telemetry | Nowhere. Craik does not send product telemetry to a Craik-controlled endpoint. | No opt-out is needed. |
| Third-party analytics | Nowhere. Craik does not embed analytics beacons in the local runtime. | No opt-out is needed. |
| Chat prompts | The configured provider API or local model endpoint for the active model. | Choose the provider, model, endpoint, and provider account settings. |
| Receipts, logs, and history | Local files under `~/.craik/` unless you configure a different `CRAIK_HOME`. | Local, operator-readable, and deletable. |

## Provider Data

When you run a prompt through a remote provider, Craik sends the prompt and
the minimum provider request data needed for that model call to the configured
provider endpoint. Provider retention, abuse monitoring, and account controls
are governed by that provider's terms and account settings.

Local model profiles route to the configured local endpoint. Craik warns when
a local-model endpoint uses plaintext HTTP outside localhost because that can
expose prompts or responses on the network path.

## Local State

Craik stores runtime evidence locally:

- auth profiles and credential references
- model and session settings
- receipts and policy decisions
- shell history
- migration reports and local-store data

Credential material is redacted from operator-facing status, doctor output,
TUI transcripts, dashboard responses, and migration reports. File-backed
credential fallback remains available for environments without keyring support,
but Craik surfaces that storage posture so operators can decide whether it is
acceptable for their machine.

## TUI Privacy

The terminal UI writes prompt and slash-command history to local history files
unless `CRAIK_HISTORY_MAX_ENTRIES=0` is set. In audited operator mode, history
files are scoped by a truncated hash of the operator subject to avoid putting
personally identifying subject values in filenames.

Credential capture modals mask input and never write credential material to
the transcript. Approval modals write only the decision summary and redacted
receipt id back to the transcript.

## Removing Local State

Delete or archive the configured Craik home to remove local runtime state:

```sh
rm -rf ~/.craik
```

For a custom home, remove the directory named by `CRAIK_HOME`.

Use auth logout flows for targeted credential removal:

```text
/auth logout openai:default
```

or from the plain shell:

```sh
craik auth logout openai
```

## Related Guides

<div className="craik-next">

<a href="../authentication/">
<strong>Guide</strong>
<span>Authentication</span>
<small>Provider credential capture and cached profile behavior.</small>
</a>

<a href="../terminal-ui/">
<strong>Guide</strong>
<span>Terminal UI</span>
<small>Interactive runtime history, modal flows, and transcript behavior.</small>
</a>

<a href="../../security/secrets/">
<strong>Security</strong>
<span>Secrets</span>
<small>How secret references and redaction work across the runtime.</small>
</a>

</div>
