from craik.runtime.i18n import localize, resolve_locale, stable_message_ids, text
from craik.runtime.projects.migration.reports import MigrationReport, format_migration_report
from craik.runtime.shell.slash_commands import dispatch_slash_command


def test_locale_resolution_and_missing_translation_fallback() -> None:
    assert resolve_locale("es-MX") == "es"
    assert resolve_locale("zz") == "en"

    missing = localize("runtime.id.not.translated", locale="es")

    assert missing.text == "runtime.id.not.translated"
    assert missing.fallback is True
    assert "slash.help.title" in stable_message_ids()


def test_slash_help_localizes_stable_command_help() -> None:
    result = dispatch_slash_command("/help provider", env={"CRAIK_LOCALE": "es"})

    assert result.exit_code == 0
    assert "Uso: /provider" in result.text
    assert "Requiere: none" in result.text


def test_migration_report_localizes_section_headers() -> None:
    report = MigrationReport(
        id="migration_report_fixture",
        source_name="fixture",
        summary={"importable": 1},
        recommended_next_commands=["craik migrate plan --source PATH --kind agent-runtime --json"],
        validation_checklist=["Confirm source files were not modified."],
        policy_envelope_id="policy_fixture",
        evidence_ids=["evidence_fixture"],
        receipt_ids=["receipt_fixture"],
    )
    lines = format_migration_report(report, locale="es")

    assert lines[0].startswith("Informe de migracion:")
    assert "Resumen:" in lines
    assert any(line == "Comandos siguientes recomendados:" for line in lines)


def test_i18n_text_helper_formats_values() -> None:
    assert text("slash.unknown", locale="es", name="ayuda") == (
        "comando slash desconocido: /ayuda."
    )
