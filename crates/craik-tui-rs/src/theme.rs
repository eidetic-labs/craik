use ratatui::style::{Color, Modifier, Style};

pub fn accent() -> Color {
    Color::Rgb(180, 172, 230)
}

pub fn primary() -> Color {
    Color::Rgb(214, 214, 222)
}

pub fn dim() -> Color {
    Color::Rgb(138, 138, 153)
}

pub fn mute() -> Color {
    Color::Rgb(90, 90, 104)
}

pub fn sage() -> Color {
    Color::Rgb(143, 184, 154)
}

pub fn amber() -> Color {
    Color::Rgb(212, 168, 102)
}

pub fn cyan() -> Color {
    Color::Rgb(134, 184, 196)
}

pub fn red() -> Color {
    Color::Rgb(207, 139, 139)
}

pub fn surface() -> Color {
    Color::Rgb(25, 25, 31)
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
