use ratatui::{
    layout::{Position, Rect},
    style::{Color, Style},
    text::{Line, Span},
};

pub struct SlashHint {
    pub name: String,
    pub usage: String,
    pub summary: String,
}

pub fn render_input_lines(input: &str, slash_catalog: &[SlashHint]) -> Vec<Line<'static>> {
    let mut lines = input
        .lines()
        .map(|line| Line::from(Span::raw(line.to_owned())))
        .collect::<Vec<_>>();
    if lines.is_empty() {
        lines.push(Line::from(Span::styled(
            "Type a prompt or /command",
            Style::default().fg(Color::DarkGray),
        )));
    }
    let suggestions = slash_suggestions(input, slash_catalog);
    if !suggestions.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Suggestions ", Style::default().fg(Color::Cyan)),
            Span::raw(suggestions.join("  ")),
        ]));
    }
    lines
}

pub fn slash_suggestions(input: &str, slash_catalog: &[SlashHint]) -> Vec<String> {
    let input = input.trim_start();
    if !input.starts_with('/') {
        return Vec::new();
    }
    let prefix = input
        .trim_start_matches('/')
        .split_whitespace()
        .next()
        .unwrap_or("");
    slash_catalog
        .iter()
        .filter(|hint| hint.name.starts_with(prefix))
        .take(5)
        .map(|hint| format!("{} - {}", hint.usage, hint.summary))
        .collect()
}

pub fn input_cursor_position(input: &str, input_cursor: usize, area: Rect) -> Position {
    let before_cursor = &input[..input_cursor.min(input.len())];
    let row = before_cursor.bytes().filter(|byte| *byte == b'\n').count() as u16;
    let col = before_cursor
        .rsplit('\n')
        .next()
        .unwrap_or_default()
        .chars()
        .count() as u16;
    let x = area.x.saturating_add(col.min(area.width.saturating_sub(1)));
    let y = area
        .y
        .saturating_add(row.min(area.height.saturating_sub(1)));
    Position::new(x, y)
}

#[cfg(test)]
mod tests {
    use super::{SlashHint, input_cursor_position, slash_suggestions};
    use ratatui::layout::Rect;

    #[test]
    fn slash_suggestions_use_catalog_usage() {
        let catalog = vec![
            SlashHint {
                name: "run".to_owned(),
                usage: "/run <prompt>".to_owned(),
                summary: "Run an audited prompt.".to_owned(),
            },
            SlashHint {
                name: "status".to_owned(),
                usage: "/status".to_owned(),
                summary: "Show readiness.".to_owned(),
            },
        ];

        assert_eq!(
            slash_suggestions("/r", &catalog),
            ["/run <prompt> - Run an audited prompt."]
        );
    }

    #[test]
    fn cursor_position_tracks_multiline_input() {
        let input = "abc\ndef";

        let position = input_cursor_position(input, input.len(), Rect::new(10, 20, 40, 3));

        assert_eq!(position.x, 13);
        assert_eq!(position.y, 21);
    }
}
