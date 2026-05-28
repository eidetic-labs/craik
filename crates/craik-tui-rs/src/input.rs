use ratatui::{
    layout::{Position, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
};

use crate::theme;

pub struct SlashHint {
    pub name: String,
    pub usage: String,
    pub summary: String,
    pub category: String,
}

struct SlashSuggestion<'a> {
    usage: &'a str,
    summary: &'a str,
    category: &'a str,
    exact_prefix: bool,
    score: usize,
}

pub fn render_input_lines(input: &str, slash_catalog: &[SlashHint]) -> Vec<Line<'static>> {
    let mut lines = if input.is_empty() {
        vec![Line::from(Span::styled(
            "Type a prompt or /command...",
            theme::dim_style(),
        ))]
    } else {
        input
            .split('\n')
            .map(|line| Line::from(Span::styled(line.to_owned(), theme::primary_style())))
            .collect::<Vec<_>>()
    };
    if !input.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Ready ", Style::default().fg(theme::sage())),
            Span::styled("Enter sends", Style::default().add_modifier(Modifier::BOLD)),
            Span::styled(" / Alt-Enter newline", theme::dim_style()),
        ]));
    }
    let suggestions = slash_suggestion_rows(input, slash_catalog);
    if !suggestions.is_empty() {
        let total = slash_catalog.len();
        lines.push(Line::from(vec![
            Span::styled("▌ Slash commands", theme::accent_style()),
            Span::styled(
                format!(
                    "  {} of {total}  Tab completes / Enter runs / Esc closes",
                    suggestions.len()
                ),
                theme::dim_style(),
            ),
        ]));
        lines.extend(suggestions.into_iter().map(|suggestion| {
            let prefix = if suggestion.exact_prefix { "▸" } else { " " };
            Line::from(vec![
                Span::styled(prefix, Style::default().fg(theme::sage())),
                Span::raw(" "),
                Span::styled(suggestion.usage.to_owned(), theme::accent_style()),
                Span::styled(
                    format!(" [{}]", suggestion.category),
                    Style::default().fg(theme::amber()),
                ),
                Span::styled(format!("  {}", suggestion.summary), theme::dim_style()),
            ])
        }));
    }
    lines
}

pub fn render_search_lines(
    query: &str,
    match_count: usize,
    selected_match: Option<usize>,
) -> Vec<Line<'static>> {
    let mut lines = vec![Line::from(vec![
        Span::styled("▌ /", theme::accent_style()),
        Span::styled(query.to_owned(), theme::primary_style()),
    ])];
    let summary = if query.trim().is_empty() {
        "Type to search transcript".to_owned()
    } else if match_count == 0 {
        "No matches".to_owned()
    } else if let Some(selected_match) = selected_match {
        format!("Match {} of {match_count}", selected_match + 1)
    } else {
        format!("{match_count} matches")
    };
    lines.push(Line::from(vec![
        Span::styled(summary, theme::dim_style()),
        Span::styled("  Ctrl-N next / Ctrl-P previous", theme::dim_style()),
    ]));
    lines
}

#[cfg(test)]
fn slash_suggestions(input: &str, slash_catalog: &[SlashHint]) -> Vec<String> {
    slash_suggestion_rows(input, slash_catalog)
        .into_iter()
        .map(|hint| format!("{} [{}] - {}", hint.usage, hint.category, hint.summary))
        .collect()
}

pub fn slash_completion(input: &str, slash_catalog: &[SlashHint]) -> Option<String> {
    let input = input.trim_start();
    if !input.starts_with('/') {
        return None;
    }
    let suggestion = slash_suggestion_rows(input, slash_catalog)
        .into_iter()
        .next()?;
    let command = suggestion
        .usage
        .split_whitespace()
        .next()
        .filter(|value| value.starts_with('/'))?;
    Some(format!("{command} "))
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
    let query = prefix.to_lowercase();
    let mut suggestions = slash_catalog
        .iter()
        .filter_map(|hint| {
            let name = hint.name.to_lowercase();
            let usage = hint.usage.to_lowercase();
            let summary = hint.summary.to_lowercase();
            let exact_prefix = name.starts_with(&query);
            let fuzzy = fuzzy_subsequence_score(&query, &name)
                .or_else(|| fuzzy_subsequence_score(&query, &usage))
                .or_else(|| {
                    (query.chars().count() > 1)
                        .then(|| fuzzy_subsequence_score(&query, &summary))
                        .flatten()
                });
            if exact_prefix
                || fuzzy.is_some()
                || (query.chars().count() > 1 && summary.contains(&query))
            {
                Some(SlashSuggestion {
                    usage: &hint.usage,
                    summary: &hint.summary,
                    category: &hint.category,
                    exact_prefix,
                    score: if exact_prefix {
                        0
                    } else {
                        fuzzy.unwrap_or(500)
                    },
                })
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    suggestions.sort_by_key(|hint| {
        (
            !hint.exact_prefix,
            hint.score,
            hint.usage.split_whitespace().next().unwrap_or("").len(),
            hint.category,
            hint.usage,
        )
    });
    suggestions
        .into_iter()
        .take(8)
        .map(|hint| SlashSuggestion {
            usage: hint.usage,
            summary: hint.summary,
            category: hint.category,
            exact_prefix: hint.exact_prefix,
            score: hint.score,
        })
        .collect()
}

fn fuzzy_subsequence_score(query: &str, candidate: &str) -> Option<usize> {
    if query.is_empty() {
        return Some(0);
    }
    let mut score = 0;
    let mut cursor = 0;
    for needle in query.chars() {
        let found = candidate[cursor..].find(needle)?;
        score += found;
        cursor += found + needle.len_utf8();
    }
    Some(score)
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
        slash_completion, slash_suggestions,
    };
    use ratatui::layout::Rect;

    #[test]
    fn slash_suggestions_use_catalog_usage() {
        let catalog = vec![
            SlashHint {
                name: "run".to_owned(),
                usage: "/run <prompt>".to_owned(),
                summary: "Run an audited prompt.".to_owned(),
                category: "Run".to_owned(),
            },
            SlashHint {
                name: "status".to_owned(),
                usage: "/status".to_owned(),
                summary: "Show readiness.".to_owned(),
                category: "Session".to_owned(),
            },
        ];

        assert_eq!(
            slash_suggestions("/r", &catalog),
            ["/run <prompt> [Run] - Run an audited prompt."]
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
        assert_eq!(lines[0].spans[0].style.fg, Some(crate::theme::dim()));
    }

    #[test]
    fn input_rendering_stacks_slash_suggestions_for_scanning() {
        let catalog = vec![
            SlashHint {
                name: "run".to_owned(),
                usage: "/run <prompt>".to_owned(),
                summary: "Run an audited prompt.".to_owned(),
                category: "Run".to_owned(),
            },
            SlashHint {
                name: "receipt".to_owned(),
                usage: "/receipt latest".to_owned(),
                summary: "Show latest receipt.".to_owned(),
                category: "Evidence".to_owned(),
            },
        ];

        let lines = render_input_lines("/r", &catalog);
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("Slash commands"));
        assert!(rendered.contains("▸ /run <prompt> [Run]  Run an audited prompt."));
        assert!(rendered.contains("▸ /receipt latest [Evidence]  Show latest receipt."));
    }

    #[test]
    fn search_rendering_shows_query_and_match_count() {
        let lines = render_search_lines("cargo", 3, Some(1));

        assert_eq!(lines[0].to_string(), "▌ /cargo");
        assert!(lines[1].to_string().contains("Match 2 of 3"));
    }

    #[test]
    fn slash_completion_uses_first_matching_command_name() {
        let catalog = vec![
            SlashHint {
                name: "receipt".to_owned(),
                usage: "/receipt latest".to_owned(),
                summary: "Show latest receipt.".to_owned(),
                category: "Evidence".to_owned(),
            },
            SlashHint {
                name: "run".to_owned(),
                usage: "/run <prompt>".to_owned(),
                summary: "Run an audited prompt.".to_owned(),
                category: "Run".to_owned(),
            },
        ];

        assert_eq!(slash_completion("/r", &catalog).as_deref(), Some("/run "));
    }

    #[test]
    fn slash_suggestions_fall_back_to_summary_search() {
        let catalog = vec![SlashHint {
            name: "receipt".to_owned(),
            usage: "/receipt latest".to_owned(),
            summary: "Show latest provenance receipt.".to_owned(),
            category: "Evidence".to_owned(),
        }];

        assert_eq!(
            slash_suggestions("/provenance", &catalog),
            ["/receipt latest [Evidence] - Show latest provenance receipt."]
        );
    }
}
