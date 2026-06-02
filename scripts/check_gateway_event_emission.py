"""Assert every captured Gateway fixture event satisfies the contract.

Structural CI guard for the receipt.created regression class: a bug shipped
where `receipt.created` was emitted without a top-level `run_id`, crashing the
gateway. This guard makes that regression class un-mergeable by validating
every captured gateway fixture against the machine-readable event contract and
additionally asserting that every `receipt.created` carries a top-level
`run_id` and a `data.receipt_id`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from craik.runtime.backend.event_contract import (
    format_gateway_event_contract_issues,
    validate_gateway_event,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_GLOB = "tests/fixtures/gateway/*.jsonl"


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    fixtures = sorted(ROOT.glob(FIXTURE_GLOB))
    if not fixtures:
        print(
            f"Gateway emission guard found no fixtures matching {FIXTURE_GLOB}; "
            "expected at least one captured gateway fixture.",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []

    for fixture in fixtures:
        rel = _rel(fixture)
        for lineno, raw in enumerate(fixture.read_text().splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}:{lineno}: invalid JSON: {exc}")
                continue

            if not isinstance(event, dict):
                errors.append(f"{rel}:{lineno}: event must be a JSON object")
                continue

            issues = validate_gateway_event(event, event_index=lineno)
            if issues:
                errors.append(
                    f"{rel}:{lineno}: {format_gateway_event_contract_issues(issues)}"
                )

            if event.get("type") == "receipt.created":
                if not event.get("run_id"):
                    errors.append(
                        f"{rel}:{lineno}: receipt.created missing top-level run_id"
                    )
                data = event.get("data")
                receipt_id = data.get("receipt_id") if isinstance(data, dict) else None
                if not receipt_id:
                    errors.append(
                        f"{rel}:{lineno}: receipt.created missing data.receipt_id"
                    )

    if errors:
        print("Gateway emission guard found contract violations:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Gateway emission guard OK: {len(fixtures)} fixtures satisfy the contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
