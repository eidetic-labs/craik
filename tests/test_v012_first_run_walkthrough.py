from __future__ import annotations

from _subprocess_harness import CraikSubprocess


def test_first_run_provider_model_chat_walkthrough(tmp_path) -> None:
    cli = CraikSubprocess(
        tmp_path,
        {"CRAIK_LIVE": "0", "OPENAI_API_KEY": "openai-test-key"},
    )

    initial = cli.run()
    login = cli.run(
        "auth",
        "login",
        "openai",
        "--env-var",
        "OPENAI_API_KEY",
        "--json",
    )
    model = cli.run("model", "set", "openai/gpt-4o-mini")
    chat = cli.run("chat", "-q", "-", input_text="hello\n")

    assert initial.exit_code == 0, initial.output
    assert "run craik auth login <provider>" in initial.output
    assert "run craik login" not in initial.output
    assert login.exit_code == 0, login.output
    assert model.exit_code == 0, model.output
    assert chat.exit_code == 0, chat.output
    assert "openai fixture completed plan with status completed." in chat.output
    assert "Audited run `" in chat.output
    assert "Receipts:" in chat.output
    assert "not ready" not in chat.output.lower()
    assert "State: provider-only" not in chat.output
