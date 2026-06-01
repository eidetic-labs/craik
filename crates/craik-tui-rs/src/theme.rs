use ratatui::style::{Color, Modifier, Style};
#[cfg(test)]
use std::cell::Cell;
use std::env;
use std::sync::OnceLock;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ThemeMode {
    Dark,
    Light,
    Monochrome,
}

#[derive(Clone, Copy)]
struct Palette {
    accent: Color,
    primary: Color,
    dim: Color,
    mute: Color,
    sage: Color,
    amber: Color,
    cyan: Color,
    red: Color,
    surface: Color,
    sage_surface: Color,
    red_surface: Color,
}

pub fn mode() -> ThemeMode {
    #[cfg(test)]
    if let Some(mode) = test_mode() {
        return mode;
    }
    mode_from_env_and_detected(|key| env::var(key).ok(), detected_terminal_mode().copied())
}

pub fn set_detected_terminal_mode(mode: ThemeMode) {
    let _ = DETECTED_TERMINAL_MODE.set(mode);
}

pub fn set_detected_terminal_mode_from_osc11(response: &str) -> bool {
    let Some(mode) = mode_from_osc11_response(response) else {
        return false;
    };
    set_detected_terminal_mode(mode);
    true
}

/// Decide whether a live OSC 11 background query is worth attempting.
///
/// The query is a terminal round-trip, so it is skipped whenever an existing
/// signal already determines (or pins) the theme and detection would be
/// ignored or redundant:
/// - an explicit `CRAIK_TUI_THEME`/`CRAIK_THEME` pin,
/// - `NO_COLOR=1` (forces monochrome),
/// - a pre-injected `CRAIK_TUI_OSC11_RESPONSE` (tests / launch wrappers),
/// - an already-present `COLORFGBG` background hint.
///
/// Precedence mirrors [`mode_from_env_and_detected`]: explicit theme and
/// `NO_COLOR` always win over a detected mode, so skipping the query in those
/// cases changes no observable behavior. The caller still gates the actual
/// I/O behind a tty check.
pub fn should_query_osc11(env_value: impl Fn(&str) -> Option<String>) -> bool {
    if env_value("CRAIK_TUI_THEME")
        .or_else(|| env_value("CRAIK_THEME"))
        .and_then(|value| mode_from_configured(&value))
        .is_some()
    {
        return false;
    }
    if env_value("NO_COLOR").as_deref() == Some("1") {
        return false;
    }
    if env_value("CRAIK_TUI_OSC11_RESPONSE").is_some() {
        return false;
    }
    if env_value("COLORFGBG").is_some() {
        return false;
    }
    true
}

pub fn accent() -> Color {
    palette().accent
}

pub fn primary() -> Color {
    palette().primary
}

pub fn dim() -> Color {
    palette().dim
}

pub fn mute() -> Color {
    palette().mute
}

pub fn sage() -> Color {
    palette().sage
}

pub fn amber() -> Color {
    palette().amber
}

pub fn cyan() -> Color {
    palette().cyan
}

pub fn red() -> Color {
    palette().red
}

pub fn surface() -> Color {
    palette().surface
}

pub fn sage_surface() -> Color {
    palette().sage_surface
}

pub fn red_surface() -> Color {
    palette().red_surface
}

pub fn primary_style() -> Style {
    Style::default().fg(primary())
}

pub fn dim_style() -> Style {
    Style::default().fg(dim())
}

pub fn mute_style() -> Style {
    Style::default().fg(mute())
}

pub fn accent_style() -> Style {
    Style::default().fg(accent()).add_modifier(Modifier::BOLD)
}

pub fn surface_style() -> Style {
    Style::default().bg(surface()).fg(primary())
}

pub fn selected_style() -> Style {
    Style::default()
        .bg(surface())
        .fg(accent())
        .add_modifier(Modifier::BOLD)
}

fn palette() -> Palette {
    match mode() {
        ThemeMode::Dark => Palette {
            accent: Color::Rgb(180, 172, 230),
            primary: Color::Rgb(214, 214, 222),
            dim: Color::Rgb(138, 138, 153),
            mute: Color::Rgb(90, 90, 104),
            sage: Color::Rgb(143, 184, 154),
            amber: Color::Rgb(212, 168, 102),
            cyan: Color::Rgb(134, 184, 196),
            red: Color::Rgb(207, 139, 139),
            surface: Color::Rgb(25, 25, 31),
            sage_surface: Color::Rgb(24, 43, 31),
            red_surface: Color::Rgb(48, 29, 31),
        },
        ThemeMode::Light => Palette {
            accent: Color::Rgb(124, 114, 199),
            primary: Color::Rgb(42, 42, 50),
            dim: Color::Rgb(92, 92, 106),
            mute: Color::Rgb(138, 138, 150),
            sage: Color::Rgb(74, 128, 86),
            amber: Color::Rgb(150, 104, 44),
            cyan: Color::Rgb(55, 120, 137),
            red: Color::Rgb(176, 77, 77),
            surface: Color::Rgb(243, 243, 247),
            sage_surface: Color::Rgb(220, 240, 224),
            red_surface: Color::Rgb(246, 222, 222),
        },
        ThemeMode::Monochrome => Palette {
            accent: Color::Gray,
            primary: Color::White,
            dim: Color::DarkGray,
            mute: Color::DarkGray,
            sage: Color::White,
            amber: Color::Gray,
            cyan: Color::Gray,
            red: Color::Gray,
            surface: Color::Reset,
            sage_surface: Color::Reset,
            red_surface: Color::Reset,
        },
    }
}

fn mode_from_env_and_detected(
    env_value: impl Fn(&str) -> Option<String>,
    detected: Option<ThemeMode>,
) -> ThemeMode {
    if let Some(configured) = env_value("CRAIK_TUI_THEME")
        .or_else(|| env_value("CRAIK_THEME"))
        .and_then(|value| mode_from_configured(&value))
    {
        return configured;
    }
    if env_value("NO_COLOR").as_deref() == Some("1") {
        return ThemeMode::Monochrome;
    }
    detected
        .or_else(|| env_value("COLORFGBG").and_then(|value| mode_from_colorfgbg(&value)))
        .unwrap_or(ThemeMode::Dark)
}

fn mode_from_configured(configured: &str) -> Option<ThemeMode> {
    match configured.trim().to_lowercase().as_str() {
        "dark" => Some(ThemeMode::Dark),
        "light" => Some(ThemeMode::Light),
        "monochrome" | "mono" => Some(ThemeMode::Monochrome),
        _ => None,
    }
}

fn mode_from_colorfgbg(value: &str) -> Option<ThemeMode> {
    let background = value.rsplit(';').next()?.trim().parse::<u8>().ok()?;
    Some(if background >= 7 {
        ThemeMode::Light
    } else {
        ThemeMode::Dark
    })
}

fn mode_from_osc11_response(response: &str) -> Option<ThemeMode> {
    let rgb = response
        .split("rgb:")
        .nth(1)?
        .trim_end_matches(['\u{1b}', '\\', '\u{7}', ' ']);
    let mut channels = rgb.split('/');
    let red = parse_osc11_channel(channels.next()?)?;
    let green = parse_osc11_channel(channels.next()?)?;
    let blue = parse_osc11_channel(channels.next()?)?;
    let luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    Some(if luminance >= 0.5 {
        ThemeMode::Light
    } else {
        ThemeMode::Dark
    })
}

fn parse_osc11_channel(channel: &str) -> Option<f64> {
    let trimmed = channel.trim();
    if trimmed.is_empty() || trimmed.len() > 4 {
        return None;
    }
    let value = u16::from_str_radix(trimmed, 16).ok()?;
    let max = (1_u32 << (trimmed.len() * 4)) - 1;
    Some(f64::from(value) / f64::from(max))
}

fn detected_terminal_mode() -> Option<&'static ThemeMode> {
    DETECTED_TERMINAL_MODE.get()
}

static DETECTED_TERMINAL_MODE: OnceLock<ThemeMode> = OnceLock::new();

#[cfg(test)]
thread_local! {
    static TEST_MODE: Cell<Option<ThemeMode>> = const { Cell::new(None) };
}

#[cfg(test)]
fn test_mode() -> Option<ThemeMode> {
    TEST_MODE.with(Cell::get)
}

#[cfg(test)]
pub fn with_mode_for_test<T>(mode: ThemeMode, render: impl FnOnce() -> T) -> T {
    TEST_MODE.with(|slot| {
        let previous = slot.replace(Some(mode));
        let result = render();
        slot.set(previous);
        result
    })
}

#[cfg(test)]
mod tests {
    use super::{
        ThemeMode, accent, dim, mode, mode_from_colorfgbg, mode_from_configured,
        mode_from_env_and_detected, mode_from_osc11_response, primary, red, surface,
        with_mode_for_test,
    };
    use ratatui::style::Color;

    #[test]
    fn theme_mode_parses_supported_values() {
        assert_eq!(mode_from_configured("dark"), Some(ThemeMode::Dark));
        assert_eq!(mode_from_configured("light"), Some(ThemeMode::Light));
        assert_eq!(
            mode_from_configured("monochrome"),
            Some(ThemeMode::Monochrome)
        );
        assert_eq!(mode_from_configured("mono"), Some(ThemeMode::Monochrome));
        assert_eq!(mode_from_configured(""), None);
    }

    #[test]
    fn theme_mode_resolver_uses_expected_precedence() {
        assert_eq!(
            mode_from_env_and_detected(
                |key| match key {
                    "CRAIK_TUI_THEME" => Some("light".to_owned()),
                    "CRAIK_THEME" => Some("dark".to_owned()),
                    "NO_COLOR" => Some("1".to_owned()),
                    "COLORFGBG" => Some("15;0".to_owned()),
                    _ => None,
                },
                Some(ThemeMode::Dark),
            ),
            ThemeMode::Light
        );
        assert_eq!(
            mode_from_env_and_detected(
                |key| match key {
                    "NO_COLOR" => Some("1".to_owned()),
                    "COLORFGBG" => Some("0;15".to_owned()),
                    _ => None,
                },
                Some(ThemeMode::Light),
            ),
            ThemeMode::Monochrome
        );
        assert_eq!(
            mode_from_env_and_detected(|_| None, Some(ThemeMode::Light)),
            ThemeMode::Light
        );
        assert_eq!(
            mode_from_env_and_detected(|key| (key == "COLORFGBG").then(|| "15;0".to_owned()), None,),
            ThemeMode::Dark
        );
        assert_eq!(mode_from_env_and_detected(|_| None, None), ThemeMode::Dark);
    }

    #[test]
    fn theme_mode_uses_colorfgbg_background_hint() {
        assert_eq!(mode_from_colorfgbg("15;0"), Some(ThemeMode::Dark));
        assert_eq!(mode_from_colorfgbg("0;15"), Some(ThemeMode::Light));
        assert_eq!(mode_from_colorfgbg("invalid"), None);
    }

    #[test]
    fn theme_mode_parses_osc11_background_response() {
        assert_eq!(
            mode_from_osc11_response("\u{1b}]11;rgb:0000/0000/0000\u{1b}\\"),
            Some(ThemeMode::Dark)
        );
        assert_eq!(
            mode_from_osc11_response("\u{1b}]11;rgb:ffff/ffff/ffff\u{1b}\\"),
            Some(ThemeMode::Light)
        );
        assert_eq!(mode_from_osc11_response("not osc"), None);
    }

    #[test]
    fn osc11_query_is_skipped_when_an_explicit_signal_wins() {
        use super::should_query_osc11;
        // Explicit theme pins win -> no need to interrogate the terminal.
        assert!(!should_query_osc11(
            |key| (key == "CRAIK_TUI_THEME").then(|| "light".to_owned())
        ));
        assert!(!should_query_osc11(
            |key| (key == "CRAIK_THEME").then(|| "dark".to_owned())
        ));
        // NO_COLOR forces monochrome regardless of background.
        assert!(!should_query_osc11(
            |key| (key == "NO_COLOR").then(|| "1".to_owned())
        ));
        // A pre-injected OSC11 response (tests / wrappers) is authoritative.
        assert!(!should_query_osc11(|key| (key
            == "CRAIK_TUI_OSC11_RESPONSE")
        .then(|| "\u{1b}]11;rgb:ffff/ffff/ffff\u{7}".to_owned())));
        // COLORFGBG already answers the question -> skip the round-trip.
        assert!(!should_query_osc11(
            |key| (key == "COLORFGBG").then(|| "0;15".to_owned())
        ));
        // Nothing set -> a live query is worthwhile.
        assert!(should_query_osc11(|_| None));
    }

    #[test]
    fn injected_osc11_response_resolves_to_expected_mode() {
        // The env-override path used by tests / launch wrappers must keep
        // working: a valid light response selects Light, garbage is rejected.
        assert!(super::set_detected_terminal_mode_from_osc11(
            "\u{1b}]11;rgb:ffff/ffff/ffff\u{1b}\\"
        ));
        assert!(!super::set_detected_terminal_mode_from_osc11("garbage"));
    }

    #[test]
    fn theme_mode_can_be_overridden_for_frame_tests() {
        with_mode_for_test(ThemeMode::Light, || {
            assert_eq!(mode(), ThemeMode::Light);
        });
    }

    #[test]
    fn monochrome_palette_degrades_to_terminal_neutral_colors() {
        with_mode_for_test(ThemeMode::Monochrome, || {
            assert_eq!(surface(), Color::Reset);
            assert_eq!(primary(), Color::White);
            assert_eq!(accent(), Color::Gray);
            assert_eq!(dim(), Color::DarkGray);
            assert_eq!(red(), Color::Gray);
        });
    }
}
