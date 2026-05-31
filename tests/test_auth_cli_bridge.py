import sys

import pytest

from craik.runtime.auth.sources import CLIBridgeCredentialError, CLIBridgeCredentialSource
from craik.runtime.auth.sources.cli_bridge import MAX_CLI_BRIDGE_OUTPUT_BYTES


def test_cli_bridge_stdout_json_extracts_token_without_leaking_in_status() -> None:
    source = CLIBridgeCredentialSource(
        command=(
            sys.executable,
            "-c",
            "import json; print(json.dumps({'token': 'craik-test-not-a-real-key'}))",
        ),
        token_extractor="stdout_json",
    )

    headers = source.headers_for("chat_completions")

    assert headers == {"Authorization": "Bearer craik-test-not-a-real-key"}
    assert source.status().status == "ok"
    assert "craik-test-not-a-real-key" not in str(source.status())


def test_cli_bridge_stdout_line_extracts_first_nonempty_line() -> None:
    source = CLIBridgeCredentialSource(
        command=(sys.executable, "-c", "print('\\nline-token\\n')"),
        token_extractor="stdout_line",
    )

    assert source.headers_for("openai") == {"Authorization": "Bearer line-token"}


@pytest.mark.parametrize("family", ["google", "gemini"])
def test_cli_bridge_returns_google_api_key_header(family: str) -> None:
    source = CLIBridgeCredentialSource(
        command=(sys.executable, "-c", "print('gemini-token')"),
        token_extractor="stdout_line",
    )

    assert source.headers_for(family) == {"x-goog-api-key": "gemini-token"}  # type: ignore[arg-type]


def test_cli_bridge_error_messages_do_not_include_stdout_token_material() -> None:
    source = CLIBridgeCredentialSource(
        command=(sys.executable, "-c", "print('craik-test-not-a-real-key'); raise SystemExit(1)"),
        token_extractor="stdout_line",
    )

    status = source.status()

    assert status.status == "rejected"
    assert status.detail == "CLI bridge command failed"
    assert "craik-test-not-a-real-key" not in str(status)


def test_cli_bridge_rejects_unbounded_stdout() -> None:
    source = CLIBridgeCredentialSource(
        command=(
            sys.executable,
            "-c",
            f"import sys; sys.stdout.write('x' * {MAX_CLI_BRIDGE_OUTPUT_BYTES + 1})",
        ),
        token_extractor="stdout_line",
    )

    with pytest.raises(CLIBridgeCredentialError, match="too much output"):
        source.headers_for("openai")


def test_cli_bridge_error_messages_do_not_include_stderr_token_material() -> None:
    source = CLIBridgeCredentialSource(
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('sk-stderr'); raise SystemExit(1)",
        ),
        token_extractor="stdout_line",
    )

    status = source.status()

    assert status.status == "rejected"
    assert status.detail == "CLI bridge command failed"
    assert "sk-stderr" not in str(status)


def test_cli_bridge_timeout_kills_command() -> None:
    source = CLIBridgeCredentialSource(
        command=(sys.executable, "-c", "import time; time.sleep(5)"),
        token_extractor="stdout_line",
        timeout_seconds=0.1,
    )

    with pytest.raises(CLIBridgeCredentialError, match="timed out"):
        source.headers_for("openai")
