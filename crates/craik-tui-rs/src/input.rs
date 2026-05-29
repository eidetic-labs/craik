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

#[derive(Clone)]
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

const MAX_SLASH_SUGGESTIONS: usize = 5;

pub fn render_input_lines(input: &str, _slash_catalog: &[SlashHint]) -> Vec<Line<'static>> {
    if input.is_empty() {
        vec![Line::from(Span::styled(
            "Message craik or type / for commands",
            theme::dim_style(),
        ))]
    } else {
        input
            .split('\n')
            .map(|line| Line::from(Span::styled(line.to_owned(), theme::primary_style())))
            .collect::<Vec<_>>()
    }
}

pub fn render_slash_palette_lines(
    input: &str,
    slash_catalog: &[SlashHint],
    selected_index: usize,
) -> Vec<Line<'static>> {
    let suggestions = slash_suggestion_rows(input, slash_catalog);
    let mut lines = Vec::new();
    if !suggestions.is_empty() {
        let total = slash_catalog.len();
        let selected = selected_index.min(suggestions.len().saturating_sub(1));
        lines.push(Line::from(vec![
            Span::styled("/", theme::accent_style()),
            Span::styled(" commands", theme::primary_style()),
            Span::styled(
                format!(
                    "  {} of {total}  {} selected",
                    suggestions.len(),
                    selected + 1
                ),
                theme::dim_style(),
            ),
        ]));
        for (index, suggestion) in suggestions.into_iter().enumerate() {
            let selected = index == selected;
            let mut command_spans = vec![Span::styled(
                if selected { "▌ " } else { "  " },
                if selected {
                    theme::accent_style()
                } else {
                    theme::mute_style()
                },
            )];
            command_spans.extend(highlight_usage(
                &suggestion.usage,
                &suggestion.query,
                selected,
            ));
            command_spans.extend([
                Span::styled("  ", theme::mute_style()),
                Span::styled(
                    suggestion.category.to_lowercase(),
                    category_style(&suggestion, selected),
                ),
                Span::styled("  ", theme::mute_style()),
                Span::styled(
                    suggestion.summary,
                    if selected {
                        theme::primary_style()
                    } else {
                        theme::dim_style()
                    },
                ),
            ]);
            if !suggestion.hint.is_empty() {
                command_spans.extend([
                    Span::styled("  ", theme::mute_style()),
                    Span::styled(
                        suggestion.hint.clone(),
                        right_hint_style(&suggestion.hint, selected),
                    ),
                ]);
            }
            lines.push(Line::from(command_spans));
        }
    }
    lines
}

#[cfg(test)]
pub fn input_cursor_row_offset(input: &str, slash_catalog: &[SlashHint]) -> u16 {
    let _ = (input, slash_catalog);
    0
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

pub fn slash_completion_at(
    input: &str,
    slash_catalog: &[SlashHint],
    selected_index: usize,
) -> Option<String> {
    let input = input.trim_start();
    if !input.starts_with('/') {
        return None;
    }
    let suggestions = slash_suggestion_rows(input, slash_catalog);
    let suggestion = suggestions.get(selected_index.min(suggestions.len().saturating_sub(1)))?;
    if input.ends_with(' ') && suggestion.usage.split_whitespace().count() > 1 {
        return Some(format!("{} ", suggestion.usage));
    }
    let command = suggestion
        .usage
        .split_whitespace()
        .next()
        .filter(|value| value.starts_with('/'))?;
    Some(format!("{command} "))
}

pub fn slash_suggestion_count(input: &str, slash_catalog: &[SlashHint]) -> usize {
    slash_suggestion_rows(input, slash_catalog).len()
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
        .take(MAX_SLASH_SUGGESTIONS)
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

fn highlight_usage(usage: &str, query: &str, selected: bool) -> Vec<Span<'static>> {
    let query = query.trim_start_matches('/').to_lowercase();
    if query.is_empty() {
        return vec![Span::styled(
            usage.to_owned(),
            if selected {
                Style::default()
                    .fg(theme::primary())
                    .add_modifier(Modifier::BOLD)
            } else {
                theme::accent_style()
            },
        )];
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
            spans.push(Span::styled(
                ch.to_string(),
                if selected {
                    Style::default().fg(theme::accent())
                } else {
                    theme::accent_style()
                },
            ));
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
        return "example".to_owned();
    }
    if let Some(cli_mirror) = &hint.cli_mirror {
        return format!("cli: {cli_mirror}");
    }
    String::new()
}

fn right_hint_style(hint: &str, selected: bool) -> Style {
    if hint.contains('⚠') || hint.contains("read-only") {
        Style::default()
            .fg(theme::amber())
            .add_modifier(Modifier::BOLD)
    } else if hint.contains("current") || hint.starts_with("now:") {
        Style::default().fg(theme::sage())
    } else if hint.starts_with("cli:") || hint.starts_with("needs ") {
        theme::dim_style()
    } else if selected {
        Style::default().fg(theme::accent())
    } else {
        theme::mute_style()
    }
}

fn category_style(suggestion: &SlashSuggestion, selected: bool) -> Style {
    if suggestion.hint.contains('⚠') || suggestion.hint.contains("read-only") {
        Style::default()
            .fg(theme::amber())
            .add_modifier(Modifier::BOLD)
    } else if selected {
        Style::default().fg(theme::accent())
    } else {
        theme::mute_style()
    }
}

fn usage_has_subcommands(usage: &str) -> bool {
    usage.contains('|') || usage.contains('[')
}

fn fallback_choices(name: &str) -> Vec<String> {
    match name {
        "mode" => [
            "default",
            "acceptEdits",
            "plan",
            "auto",
            "dontAsk",
            "bypassPermissions",
        ]
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
pub fn input_cursor_position_with_row_offset(
    input: &str,
    input_cursor: usize,
    area: Rect,
    row_offset: u16,
) -> Position {
    let mut position = input_cursor_position(input, input_cursor, area);
    position.y = position
        .y
        .saturating_add(row_offset)
        .min(area.y.saturating_add(area.height.saturating_sub(1)));
    position
}

#[cfg(test)]
mod tests {
    use super::{
        SlashHint, input_cursor_position, input_cursor_position_with_row_offset,
        input_cursor_row_offset, render_input_lines, render_search_lines,
        render_slash_palette_lines, slash_completion_at, slash_suggestions,
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
    fn cursor_position_can_account_for_palette_above_prompt() {
        let input = "/r";
        let catalog = vec![
            SlashHint::new("run", "/run <prompt>", "Run an audited prompt.", "Run"),
            SlashHint::new(
                "receipt",
                "/receipt latest",
                "Show latest receipt.",
                "Evidence",
            ),
        ];
        let area = Rect::new(10, 20, 40, 12);

        let offset = input_cursor_row_offset(input, &catalog);
        let position = input_cursor_position_with_row_offset(input, input.len(), area, offset);

        assert_eq!(offset, 0);
        assert_eq!(position.x, 12);
        assert_eq!(position.y, 20);
    }

    #[test]
    fn input_rendering_preserves_trailing_blank_line() {
        let lines = render_input_lines("hello\n", &[]);

        assert_eq!(lines[0].to_string(), "hello");
        assert_eq!(lines[1].to_string(), "");
        assert_eq!(lines.len(), 2);
    }

    #[test]
    fn empty_input_renders_compact_prompt_placeholder() {
        let lines = render_input_lines("", &[]);

        assert_eq!(lines[0].to_string(), "Message craik or type / for commands");
        assert_eq!(lines.len(), 1);
    }

    #[test]
    fn input_rendering_keeps_slash_text_in_prompt_surface() {
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

        assert_eq!(rendered, "/r");
        assert!(!rendered.contains("/ commands"));
    }

    #[test]
    fn slash_palette_renders_single_line_commands_with_selected_focus() {
        let catalog = vec![
            SlashHint::new("run", "/run <prompt>", "Run an audited prompt.", "Run"),
            SlashHint::new(
                "receipt",
                "/receipt latest",
                "Show latest receipt.",
                "Evidence",
            ),
        ];

        let lines = render_slash_palette_lines("/r", &catalog, 0);
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert_eq!(lines.len(), 3);
        assert!(rendered.contains("/ commands"));
        assert!(rendered.contains("1 selected"));
        assert!(rendered.contains("▌ /run <prompt>"));
        assert!(rendered.contains("/run <prompt>  run  Run an audited prompt."));
        assert!(rendered.contains("/receipt latest  evidence  Show latest receipt."));
        assert!(!rendered.contains("▸"));
    }

    #[test]
    fn slash_palette_limits_rows_to_preserve_composer_space() {
        let catalog = vec![
            SlashHint::new("help", "/help", "Show help.", "Session"),
            SlashHint::new("history", "/history", "Show history.", "Session"),
            SlashHint::new("handoff", "/handoff", "Create handoff.", "Workflow"),
            SlashHint::new("health", "/health", "Show health.", "Session"),
            SlashHint::new("headers", "/headers", "Show headers.", "Debug"),
            SlashHint::new("hidden", "/hidden", "Hidden overflow.", "Debug"),
        ];

        let lines = render_slash_palette_lines("/h", &catalog, 0);
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("5 of 6"));
        assert!(rendered.contains("/help"));
        assert!(rendered.contains("/headers"));
        assert!(!rendered.contains("/hidden"));
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
            slash_completion_at("/r", &catalog, 0).as_deref(),
            Some("/receipt ")
        );
    }

    #[test]
    fn slash_completion_uses_selected_candidate_and_drilldown_value() {
        let mut mode = SlashHint::new(
            "mode",
            "/mode [default|acceptEdits|plan|auto|dontAsk|bypassPermissions]",
            "Set mode.",
            "Run",
        );
        mode.current_value = Some("default".to_owned());
        let catalog = vec![
            SlashHint::new("receipt", "/receipt latest", "Show receipt.", "Evidence"),
            SlashHint::new("run", "/run <prompt>", "Run audited prompt.", "Run"),
            mode,
        ];

        assert_eq!(
            slash_completion_at("/r", &catalog, 1).as_deref(),
            Some("/run ")
        );
        assert_eq!(
            slash_completion_at("/mode ", &catalog, 2).as_deref(),
            Some("/mode plan ")
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
            "/mode [default|acceptEdits|plan|auto|dontAsk|bypassPermissions]",
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

    #[test]
    fn slash_palette_renders_current_and_confirm_hints_as_row_metadata() {
        let mut mode = SlashHint::new(
            "mode",
            "/mode [default|acceptEdits|plan|auto|dontAsk|bypassPermissions]",
            "Inspect or set mode.",
            "Run",
        );
        mode.current_value = Some("default".to_owned());
        let mut clear = SlashHint::new("clear", "/clear", "Clear transcript.", "Workflow");
        clear.requires_confirmation = true;
        let catalog = vec![mode, clear];

        let root = render_slash_palette_lines("/m", &catalog, 0)
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");
        assert!(root.contains("/mode [default|acceptEdits|plan|auto|dontAsk|bypassPermissions]  run  Inspect or set mode."));
        assert!(root.contains("now: default"));
        assert!(root.contains("run  Inspect or set mode."));

        let confirm = render_slash_palette_lines("/c", &catalog, 0)
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");
        assert!(confirm.contains("/clear  workflow  Clear transcript.  ⚠ confirms"));
        assert!(confirm.contains("workflow  Clear transcript."));

        let drilldown = render_slash_palette_lines("/mode ", &catalog, 0)
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");
        assert!(drilldown.contains("/mode default  run  Current value  ● current"));
        assert!(drilldown.contains("/mode plan  run  Read-only planning mode.  read-only"));
    }
}
