use ratatui::style::{Color, Modifier, Style};
#[cfg(test)]
use std::cell::Cell;
use std::env;

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
}

pub fn mode() -> ThemeMode {
    #[cfg(test)]
    if let Some(mode) = test_mode() {
        return mode;
    }
    let configured = env::var("CRAIK_TUI_THEME")
        .or_else(|_| env::var("CRAIK_THEME"))
        .unwrap_or_default()
        .to_lowercase();
    mode_from_configured(&configured)
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

pub fn mode_label() -> &'static str {
    match mode() {
        ThemeMode::Dark => "dark",
        ThemeMode::Light => "light",
        ThemeMode::Monochrome => "monochrome",
    }
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
        },
        ThemeMode::Monochrome => Palette {
            accent: Color::Gray,
            primary: Color::White,
            dim: Color::Gray,
            mute: Color::DarkGray,
            sage: Color::White,
            amber: Color::Gray,
            cyan: Color::Gray,
            red: Color::White,
            surface: Color::Reset,
        },
    }
}

fn mode_from_configured(configured: &str) -> ThemeMode {
    match configured {
        "light" => ThemeMode::Light,
        "monochrome" | "mono" => ThemeMode::Monochrome,
        _ => ThemeMode::Dark,
    }
}

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
    use super::{ThemeMode, mode, mode_from_configured, with_mode_for_test};

    #[test]
    fn theme_mode_parses_supported_values() {
        assert_eq!(mode_from_configured(""), ThemeMode::Dark);
        assert_eq!(mode_from_configured("light"), ThemeMode::Light);
        assert_eq!(mode_from_configured("monochrome"), ThemeMode::Monochrome);
        assert_eq!(mode_from_configured("mono"), ThemeMode::Monochrome);
    }

    #[test]
    fn theme_mode_can_be_overridden_for_frame_tests() {
        with_mode_for_test(ThemeMode::Light, || {
            assert_eq!(mode(), ThemeMode::Light);
        });
    }
}
