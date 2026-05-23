"""Locale-aware operator-facing message catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_LOCALE = "en"
LOCALE_ENV_VAR = "CRAIK_LOCALE"


@dataclass(frozen=True)
class LocalizedMessage:
    """Stable message id plus localized text."""

    id: str
    text: str
    locale: str
    fallback: bool = False


MESSAGES: dict[str, dict[str, str]] = {
    "slash.help.title": {
        "en": "Craik slash commands",
        "es": "Comandos slash de Craik",
    },
    "slash.help.usage": {
        "en": "Usage",
        "es": "Uso",
    },
    "slash.help.requires": {
        "en": "Requires",
        "es": "Requiere",
    },
    "slash.unknown": {
        "en": "unknown slash command: /{name}.",
        "es": "comando slash desconocido: /{name}.",
    },
    "slash.suggestion": {
        "en": " Did you mean /{suggestion}?",
        "es": " Quiso decir /{suggestion}?",
    },
    "migration.report.title": {
        "en": "Migration report",
        "es": "Informe de migracion",
    },
    "migration.report.source": {
        "en": "Source",
        "es": "Origen",
    },
    "migration.report.summary": {
        "en": "Summary",
        "es": "Resumen",
    },
    "migration.report.importable": {
        "en": "Importable objects",
        "es": "Objetos importables",
    },
    "migration.report.manual": {
        "en": "Manual actions",
        "es": "Acciones manuales",
    },
    "migration.report.skipped_secrets": {
        "en": "Skipped secrets",
        "es": "Secretos omitidos",
    },
    "migration.report.security": {
        "en": "Security posture changes",
        "es": "Cambios de postura de seguridad",
    },
    "migration.report.unsupported": {
        "en": "Unsupported capabilities",
        "es": "Capacidades no compatibles",
    },
    "migration.report.next": {
        "en": "Recommended next commands",
        "es": "Comandos siguientes recomendados",
    },
    "migration.report.validation": {
        "en": "Validation checklist",
        "es": "Lista de validacion",
    },
    "remediation.auth.login": {
        "en": "run craik auth login",
        "es": "ejecute craik auth login",
    },
    "dashboard.auth.required": {
        "en": "Dashboard access requires an active operator session or token.",
        "es": "El panel requiere una sesion de operador activa o token.",
    },
    "tui.help": {
        "en": "Use /help for slash commands, /redraw to refresh, /exit to quit.",
        "es": "Use /help para comandos slash, /redraw para actualizar, /exit para salir.",
    },
}


def resolve_locale(
    requested: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve a supported locale from an explicit value or environment."""
    value = requested or (env or {}).get(LOCALE_ENV_VAR) or DEFAULT_LOCALE
    normalized = value.split(".", 1)[0].replace("_", "-").lower()
    language = normalized.split("-", 1)[0]
    return language if any(language in values for values in MESSAGES.values()) else DEFAULT_LOCALE


def localize(
    message_id: str,
    *,
    locale: str | None = None,
    env: Mapping[str, str] | None = None,
    **values: object,
) -> LocalizedMessage:
    """Return localized text, falling back to English for missing translations."""
    resolved = resolve_locale(locale, env=env)
    translations = MESSAGES.get(message_id)
    if translations is None:
        return LocalizedMessage(
            id=message_id,
            text=message_id.format(**values),
            locale=resolved,
            fallback=True,
        )
    template = translations.get(resolved)
    fallback = template is None
    if template is None:
        template = translations[DEFAULT_LOCALE]
    return LocalizedMessage(
        id=message_id,
        text=template.format(**values),
        locale=resolved,
        fallback=fallback,
    )


def text(
    message_id: str,
    *,
    locale: str | None = None,
    env: Mapping[str, str] | None = None,
    **values: object,
) -> str:
    """Return localized text only."""
    return localize(message_id, locale=locale, env=env, **values).text


def stable_message_ids() -> tuple[str, ...]:
    """Return message ids in stable sorted order."""
    return tuple(sorted(MESSAGES))
