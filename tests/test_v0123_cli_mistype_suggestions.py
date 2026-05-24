from __future__ import annotations

import click
from typer.testing import CliRunner

from craik.cli import app

runner = CliRunner()


def _output(args: list[str]) -> tuple[int, str]:
    result = runner.invoke(app, args)
    return result.exit_code, click.unstyle(result.output)


def test_top_level_mistype_suggests_close_command() -> None:
    exit_code, output = _output(["udpate"])

    assert exit_code == 2
    assert "No such command 'udpate'." in output
    assert "Did you mean 'craik update'?" in output


def test_first_level_subcommand_mistype_suggests_within_group() -> None:
    exit_code, output = _output(["auth", "lgoin"])

    assert exit_code == 2
    assert "No such command 'lgoin'." in output
    assert "Did you mean 'craik auth login'?" in output


def test_no_close_match_does_not_suggest() -> None:
    exit_code, output = _output(["zzzzzz"])

    assert exit_code == 2
    assert "No such command 'zzzzzz'." in output
    assert "Did you mean" not in output


def test_alphabetical_tiebreaker_for_same_edit_distance() -> None:
    exit_code, output = _output(["cas"])

    assert exit_code == 2
    assert "Did you mean 'craik case'?" in output


def test_flag_mistypes_stay_typer_option_errors() -> None:
    exit_code, output = _output(["--versoin"])

    assert exit_code == 2
    assert "No such option" in output
    assert "Did you mean 'craik" not in output
