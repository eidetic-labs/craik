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
    pub aliases: Vec<String>,
    pub choices: Vec<String>,
    pub subcommands: Vec<String>,
    pub requires_confirmation: bool,
    pub confirm_message: Option<String>,
    pub cli_mirror: Option<String>,
    pub required_args: Vec<String>,
    pub examples: Vec<String>,
    pub current_value: Option<String>,
}

#[cfg(test)]
impl SlashHint {
    pub fn new(name: &str, usage: &str, summary: &str, category: &str) -> Self {
        Self {
            name: name.to_owned(),
            usage: usage.to_owned(),
            summary: summary.to_owned(),
            category: category.to_owned(),
            aliases: Vec::new(),
            choices: Vec::new(),
            subcommands: Vec::new(),
            requires_confirmation: false,
            confirm_message: None,
            cli_mirror: None,
            required_args: Vec::new(),
            examples: Vec::new(),
            current_value: None,
        }
    }
}

struct SlashSuggestion {
    usage: String,
    summary: String,
    category: String,
    exact_prefix: bool,
    score: usize,
    catalog_index: usize,
    hint: String,
    query: String,
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
            Span::styled("▌ ", theme::accent_style()),
            Span::styled("/", theme::accent_style()),
            Span::styled(" command palette", theme::primary_style()),
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
            let category_style =
                if suggestion.hint.contains('⚠') || suggestion.hint.contains("read-only") {
                    Style::default()
                        .fg(theme::amber())
                        .add_modifier(Modifier::BOLD)
                } else {
                    theme::mute_style()
                };
            let mut spans = vec![
                Span::styled("  ", theme::mute_style()),
                Span::styled(prefix, Style::default().fg(theme::sage())),
                Span::raw("  "),
            ];
            spans.extend(highlight_usage(&suggestion.usage, &suggestion.query));
            spans.extend([
                Span::styled(
                    format!("  {}", suggestion.category.to_lowercase()),
                    category_style,
                ),
                Span::styled("  - ", theme::mute_style()),
                Span::styled(suggestion.summary, theme::dim_style()),
                Span::styled(
                    format!("  {}", suggestion.hint),
                    right_hint_style(&suggestion.hint),
                ),
            ]);
            Line::from(spans)
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
        .map(|hint| {
            format!(
                "{} [{}] - {} ({})",
                hint.usage, hint.category, hint.summary, hint.hint
            )
        })
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

fn slash_suggestion_rows(input: &str, slash_catalog: &[SlashHint]) -> Vec<SlashSuggestion> {
    let input = input.trim_start();
    if !input.starts_with('/') {
        return Vec::new();
    }
    let trimmed = input.trim_start_matches('/');
    let mut tokens = trimmed.split_whitespace();
    let prefix = tokens.next().unwrap_or("");
    let selected_command = input
        .ends_with(' ')
        .then(|| {
            slash_catalog
                .iter()
                .find(|hint| hint.name == prefix || hint.usage.starts_with(&format!("/{prefix} ")))
        })
        .flatten();
    if let Some(command) = selected_command {
        let drilldown = command_drilldown_rows(command);
        if !drilldown.is_empty() {
            return drilldown;
        }
    }
    let query = prefix.to_lowercase();
    let mut suggestions = slash_catalog
        .iter()
        .enumerate()
        .filter_map(|hint| {
            let (catalog_index, hint) = hint;
            let name = hint.name.to_lowercase();
            let usage = hint.usage.to_lowercase();
            let summary = hint.summary.to_lowercase();
            let alias_match = hint
                .aliases
                .iter()
                .any(|alias| alias.to_lowercase().starts_with(&query));
            let exact_prefix = name.starts_with(&query) || alias_match;
            let fuzzy = fuzzy_subsequence_score(&query, &name)
                .or_else(|| {
                    (query.chars().count() > 2)
                        .then(|| fuzzy_subsequence_score(&query, &usage))
                        .flatten()
                })
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
                    usage: hint.usage.clone(),
                    summary: hint.summary.clone(),
                    category: hint.category.clone(),
                    exact_prefix,
                    score: if exact_prefix {
                        0
                    } else {
                        fuzzy.unwrap_or(500)
                    },
                    catalog_index,
                    hint: hint_right_hint(hint),
                    query: query.clone(),
                })
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    suggestions.sort_by_key(|hint| (!hint.exact_prefix, hint.score, hint.catalog_index));
    suggestions
        .into_iter()
        .take(8)
        .map(|hint| SlashSuggestion {
            usage: hint.usage,
            summary: hint.summary,
            category: hint.category,
            exact_prefix: hint.exact_prefix,
            score: hint.score,
            catalog_index: hint.catalog_index,
            hint: hint.hint,
            query: hint.query,
        })
        .collect()
}

fn command_drilldown_rows(hint: &SlashHint) -> Vec<SlashSuggestion> {
    let choices = if hint.choices.is_empty() {
        fallback_choices(&hint.name)
    } else {
        hint.choices.clone()
    };
    if !choices.is_empty() {
        return choices
            .into_iter()
            .map(|choice| {
                let current = hint.current_value.as_deref() == Some(choice.as_str());
                SlashSuggestion {
                    usage: format!("/{} {choice}", hint.name),
                    summary: if current {
                        "Current value"
                    } else if hint.name == "mode" && choice == "plan" {
                        "Read-only planning mode."
                    } else {
                        "Available value."
                    }
                    .to_owned(),
                    category: hint.category.clone(),
                    exact_prefix: current,
                    score: if current { 0 } else { 1 },
                    catalog_index: 0,
                    hint: if current {
                        "● current".to_owned()
                    } else if hint.name == "mode" && choice == "plan" {
                        "read-only".to_owned()
                    } else {
                        "value".to_owned()
                    },
                    query: String::new(),
                }
            })
            .collect();
    }
    hint.subcommands
        .iter()
        .map(|subcommand| SlashSuggestion {
            usage: format!("/{} {subcommand}", hint.name),
            summary: "Subcommand.".to_owned(),
            category: hint.category.clone(),
            exact_prefix: true,
            score: 0,
            catalog_index: 0,
            hint: "set ▸".to_owned(),
            query: String::new(),
        })
        .collect()
}

fn highlight_usage(usage: &str, query: &str) -> Vec<Span<'static>> {
    let query = query.trim_start_matches('/').to_lowercase();
    if query.is_empty() {
        return vec![Span::styled(usage.to_owned(), theme::accent_style())];
    }
    let mut spans = Vec::new();
    let mut query_chars = query.chars();
    let mut next_match = query_chars.next();
    for ch in usage.chars() {
        if next_match.is_some_and(|needle| ch.to_ascii_lowercase() == needle) {
            spans.push(Span::styled(
                ch.to_string(),
                Style::default()
                    .fg(theme::primary())
                    .add_modifier(Modifier::BOLD),
            ));
            next_match = query_chars.next();
        } else {
            spans.push(Span::styled(ch.to_string(), theme::accent_style()));
        }
    }
    spans
}

fn hint_right_hint(hint: &SlashHint) -> String {
    if hint.requires_confirmation {
        let _has_confirm_message = hint.confirm_message.is_some();
        return "⚠ confirms".to_owned();
    }
    if let Some(value) = &hint.current_value {
        return format!("now: {value}");
    }
    if !hint.choices.is_empty() || !fallback_choices(&hint.name).is_empty() {
        return "values ▸".to_owned();
    }
    if !hint.subcommands.is_empty() || usage_has_subcommands(&hint.usage) {
        return "set ▸".to_owned();
    }
    if !hint.required_args.is_empty() {
        return format!("needs {}", hint.required_args.join(","));
    }
    if !hint.examples.is_empty() {
        return "example ▸".to_owned();
    }
    if let Some(cli_mirror) = &hint.cli_mirror {
        return format!("cli: {cli_mirror}");
    }
    String::new()
}

fn right_hint_style(hint: &str) -> Style {
    if hint.contains('⚠') || hint.contains("read-only") {
        Style::default()
            .fg(theme::amber())
            .add_modifier(Modifier::BOLD)
    } else if hint.contains("current") || hint.starts_with("now:") {
        Style::default().fg(theme::sage())
    } else if hint.starts_with("cli:") || hint.starts_with("needs ") {
        theme::dim_style()
    } else {
        theme::mute_style()
    }
}

fn usage_has_subcommands(usage: &str) -> bool {
    usage.contains('|') || usage.contains('[')
}

fn fallback_choices(name: &str) -> Vec<String> {
    match name {
        "mode" => ["default", "acceptEdits", "plan", "auto"]
            .into_iter()
            .map(str::to_owned)
            .collect(),
        "theme" => ["dark", "light", "monochrome"]
            .into_iter()
            .map(str::to_owned)
            .collect(),
        _ => Vec::new(),
    }
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
            SlashHint::new("run", "/run <prompt>", "Run an audited prompt.", "Run"),
            SlashHint::new("status", "/status", "Show readiness.", "Session"),
        ];

        assert_eq!(
            slash_suggestions("/r", &catalog),
            ["/run <prompt> [Run] - Run an audited prompt. ()"]
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
            SlashHint::new("run", "/run <prompt>", "Run an audited prompt.", "Run"),
            SlashHint::new(
                "receipt",
                "/receipt latest",
                "Show latest receipt.",
                "Evidence",
            ),
        ];

        let lines = render_input_lines("/r", &catalog);
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("/ command palette"));
        assert!(rendered.contains("▸  /run <prompt>  run  - Run an audited prompt."));
        assert!(rendered.contains("▸  /receipt latest  evidence  - Show latest receipt."));
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
            SlashHint::new(
                "receipt",
                "/receipt latest",
                "Show latest receipt.",
                "Evidence",
            ),
            SlashHint::new("run", "/run <prompt>", "Run an audited prompt.", "Run"),
        ];

        assert_eq!(
            slash_completion("/r", &catalog).as_deref(),
            Some("/receipt ")
        );
    }

    #[test]
    fn slash_suggestions_fall_back_to_summary_search() {
        let catalog = vec![SlashHint::new(
            "receipt",
            "/receipt latest",
            "Show latest provenance receipt.",
            "Evidence",
        )];

        assert_eq!(
            slash_suggestions("/provenance", &catalog),
            ["/receipt latest [Evidence] - Show latest provenance receipt. ()"]
        );
    }

    #[test]
    fn slash_suggestions_surface_choices_and_confirmation_flags() {
        let mut mode = SlashHint::new(
            "mode",
            "/mode [default|acceptEdits|plan|auto]",
            "Set mode.",
            "Run",
        );
        mode.current_value = Some("default".to_owned());
        let mut policy = SlashHint::new("policy", "/policy reset", "Reset policy.", "Workflow");
        policy.requires_confirmation = true;
        let catalog = vec![mode, policy];

        let root = slash_suggestions("/po", &catalog);
        assert_eq!(
            root,
            ["/policy reset [Workflow] - Reset policy. (⚠ confirms)"]
        );

        let choices = slash_suggestions("/mode ", &catalog).join("\n");
        assert!(choices.contains("/mode default [Run] - Current value (● current)"));
        assert!(choices.contains("/mode plan [Run] - Read-only planning mode. (read-only)"));
    }
}
