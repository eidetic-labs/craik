# Receipt Verification

<p className="craik-meta"><span>4 min read</span><span>For operators and reviewers</span><span>Updated 2026-05-24</span></p>

<div className="craik-lead">

**What you'll verify**

Craik receipts can be checked outside the producing runtime. The verifier
confirms the receipt HMAC, redaction posture, and optional shell side-log
digests, then returns a machine-readable pass/fail result.

</div>

## Verify a Receipt File

Use `craik receipt verify` when reviewing a receipt copied from another
machine, attached to a release, or included in a handoff bundle.

```bash title="Verify with explicit key material"
craik receipt verify receipt.json --public-key /path/to/instruction-approval-hmac.key
```

The command prints JSON:

```json
{
  "failures": [],
  "hmac_status": "verified",
  "outcome": "pass",
  "passed": true,
  "receipt_id": "receipt_123",
  "redaction_status": "verified",
  "side_log_status": "not_applicable"
}
```

Exit code `0` means the receipt passed every requested check. Exit code `1`
means verification ran and found a failure. Typer usage errors, such as an
unknown flag, keep their normal CLI error behavior.

## Read from Stdin

Use `-` to verify a receipt from a pipeline:

```bash title="Verify from stdin"
cat receipt.json | craik receipt verify - --public-key /path/to/key
```

## Auto-Discover Local Key Material

`--auto-discover` looks for the local HMAC key under
`$CRAIK_HOME/secrets/instruction-approval-hmac.key`, or under
`~/.craik/secrets/` when `CRAIK_HOME` is unset.

```bash title="Verify with local key discovery"
craik receipt verify receipt.json --auto-discover
```

Only use auto-discovery on a machine that should be trusted to inspect the
local Craik state. For portable review, pass the key path explicitly.

:::note
The CLI flag is named `--public-key` for verifier ergonomics, but current
receipt integrity uses symmetric HMAC key material. Treat that file as a
secret and avoid committing it, sharing it in issues, or attaching it to
releases.
:::

## Shell Side Logs

Shell invocation receipts may contain `stdout_sha256` and `stderr_sha256`
fields. Pass the side-log directory to verify those files against the receipt:

```bash title="Verify receipt and side logs"
craik receipt verify shell-receipt.json \
  --public-key /path/to/key \
  --side-log-base ~/.craik/state/shell-output
```

The verifier expects files named `<digest>.stdout.log` and
`<digest>.stderr.log`. Digest fields must be lowercase SHA-256 hex strings
before the verifier constructs side-log paths. Missing, malformed, or
mismatched side logs fail verification.

## Library Use

The verifier is also importable without invoking the CLI:

```python
from craik.tools.receipt_verifier import verify_receipt_file

result = verify_receipt_file("receipt.json", public_key_path="/path/to/key")
if not result.passed:
    raise RuntimeError(result.failures)
```

Use `verify_receipt_bytes()` when a receipt is already loaded from an artifact,
HTTP response, or signed bundle.
