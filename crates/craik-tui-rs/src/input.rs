use ratatui::{
    layout::{Position, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

pub struct SlashHint {
    pub name: String,
    pub usage: String,
    pub summary: String,
}

struct SlashSuggestion<'a> {
    usage: &'a str,
    summary: &'a str,
}

pub fn render_input_lines(input: &str, slash_catalog: &[SlashHint]) -> Vec<Line<'static>> {
    let mut lines = if input.is_empty() {
        vec![Line::from(Span::styled(
            "Type a prompt or /command...",
            Style::default().fg(Color::DarkGray),
        ))]
    } else {
        input
            .split('\n')
            .map(|line| {
                Line::from(Span::styled(
                    line.to_owned(),
                    Style::default().fg(Color::White),
                ))
            })
            .collect::<Vec<_>>()
    };
    if !input.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Ready ", Style::default().fg(Color::Green)),
            Span::styled("Enter sends", Style::default().add_modifier(Modifier::BOLD)),
            Span::styled(" / Alt-Enter newline", Style::default().fg(Color::DarkGray)),
        ]));
    }
    let suggestions = slash_suggestion_rows(input, slash_catalog);
    if !suggestions.is_empty() {
        lines.push(Line::from(Span::styled(
            "Suggestions",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )));
        lines.extend(suggestions.into_iter().map(|suggestion| {
            Line::from(vec![
                Span::raw("  "),
                Span::styled(
                    suggestion.usage.to_owned(),
                    Style::default()
                        .fg(Color::LightCyan)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    format!("  {}", suggestion.summary),
                    Style::default().fg(Color::DarkGray),
                ),
            ])
        }));
    }
    lines
}

pub fn render_search_lines(query: &str, match_count: usize) -> Vec<Line<'static>> {
    let mut lines = vec![Line::from(vec![
        Span::styled("/", Style::default().fg(Color::Cyan)),
        Span::styled(query.to_owned(), Style::default().fg(Color::White)),
    ])];
    let summary = if query.trim().is_empty() {
        "Type to search transcript".to_owned()
    } else {
        format!("{match_count} matches")
    };
    lines.push(Line::from(Span::styled(
        summary,
        Style::default().fg(Color::DarkGray),
    )));
    lines
}

#[cfg(test)]
fn slash_suggestions(input: &str, slash_catalog: &[SlashHint]) -> Vec<String> {
    slash_suggestion_rows(input, slash_catalog)
        .into_iter()
        .map(|hint| format!("{} - {}", hint.usage, hint.summary))
        .collect()
}

fn slash_suggestion_rows<'a>(
    input: &str,
    slash_catalog: &'a [SlashHint],
) -> Vec<SlashSuggestion<'a>> {
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
        .map(|hint| SlashSuggestion {
            usage: &hint.usage,
            summary: &hint.summary,
        })
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
    use super::{
        SlashHint, input_cursor_position, render_input_lines, render_search_lines,
        slash_suggestions,
    };
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

    #[test]
    fn input_rendering_preserves_trailing_blank_line() {
        let lines = render_input_lines("hello\n", &[]);

        assert_eq!(lines[0].to_string(), "hello");
        assert_eq!(lines[1].to_string(), "");
        assert!(lines[2].to_string().contains("Enter sends"));
    }

    #[test]
    fn placeholder_is_visible_when_input_is_empty() {
        let lines = render_input_lines("", &[]);

        assert_eq!(lines[0].to_string(), "Type a prompt or /command...");
        assert_eq!(
            lines[0].spans[0].style.fg,
            Some(ratatui::style::Color::DarkGray)
        );
    }

    #[test]
    fn input_rendering_stacks_slash_suggestions_for_scanning() {
        let catalog = vec![
            SlashHint {
                name: "run".to_owned(),
                usage: "/run <prompt>".to_owned(),
                summary: "Run an audited prompt.".to_owned(),
            },
            SlashHint {
                name: "receipt".to_owned(),
                usage: "/receipt latest".to_owned(),
                summary: "Show latest receipt.".to_owned(),
            },
        ];

        let lines = render_input_lines("/r", &catalog);
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("Suggestions"));
        assert!(rendered.contains("  /run <prompt>  Run an audited prompt."));
        assert!(rendered.contains("  /receipt latest  Show latest receipt."));
    }

    #[test]
    fn search_rendering_shows_query_and_match_count() {
        let lines = render_search_lines("cargo", 3);

        assert_eq!(lines[0].to_string(), "/cargo");
        assert_eq!(lines[1].to_string(), "3 matches");
    }
}
