use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

use crate::theme;

const TRANSCRIPT_RENDER_BUFFER_LINES: usize = 1_000;

pub struct TranscriptEntry {
    pub kind: TranscriptKind,
    pub title: String,
    pub body: String,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum TranscriptKind {
    System,
    User,
    Assistant,
    Progress,
    Tool,
    File,
    Command,
    Approval,
    Receipt,
    Error,
}

pub struct TranscriptRenderOptions<'a> {
    pub expand_details: bool,
    pub search_query: Option<&'a str>,
}

impl TranscriptEntry {
    pub fn new(kind: TranscriptKind, title: &str, body: &str) -> Self {
        Self {
            kind,
            title: title.to_owned(),
            body: body.to_owned(),
        }
    }

    pub fn system(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::System, title, body)
    }

    pub fn user(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::User, title, body)
    }

    pub fn assistant(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::Assistant, title, body)
    }

    pub fn progress(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::Progress, title, body)
    }

    pub fn error(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::Error, title, body)
    }
}

#[cfg(test)]
impl<'a> TranscriptRenderOptions<'a> {
    pub fn expanded() -> Self {
        Self {
            expand_details: true,
            search_query: None,
        }
    }
}

pub fn transcript_scroll_offset(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
    transcript_scroll: u16,
    visible_height: u16,
) -> u16 {
    let line_count = transcript_line_count(entries, options);
    line_count
        .saturating_sub(visible_height)
        .saturating_sub(transcript_scroll)
}

pub fn transcript_line_count(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> u16 {
    rendered_entry_line_count(entries, options).min(u16::MAX as usize) as u16
}

#[cfg(test)]
pub fn render_transcript_lines(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> Vec<Line<'static>> {
    let entries = entries.iter().collect::<Vec<_>>();
    render_entries(&entries, options)
}

pub fn render_transcript_lines_window(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
    scroll_offset: u16,
    visible_height: u16,
) -> Vec<Line<'static>> {
    let start = usize::from(transcript_render_window_start(scroll_offset));
    let end = usize::from(scroll_offset)
        .saturating_add(usize::from(visible_height))
        .saturating_add(TRANSCRIPT_RENDER_BUFFER_LINES);
    let mut cursor = 0;
    let mut visible_entries = Vec::new();
    for entry in entries {
        let entry_line_count = 2 + entry_body_lines(entry, options.expand_details).len().max(1);
        let entry_end = cursor + entry_line_count;
        if entry_end >= start && cursor <= end {
            visible_entries.push(entry);
        }
        cursor = entry_end;
    }
    render_entries(&visible_entries, options)
}

pub fn transcript_render_window_start(scroll_offset: u16) -> u16 {
    scroll_offset.saturating_sub(TRANSCRIPT_RENDER_BUFFER_LINES.min(usize::from(u16::MAX)) as u16)
}

fn render_entries(
    entries: &[&TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    for entry in entries {
        let (label, color) = transcript_label_style(&entry.kind);
        lines.push(highlight_search(
            vec![
                Span::styled("▌ ", Style::default().fg(color)),
                Span::styled(
                    format!("{label} "),
                    Style::default().fg(color).add_modifier(Modifier::BOLD),
                ),
                Span::styled(entry.title.clone(), title_style(&entry.kind)),
            ],
            options.search_query,
        ));
        let entry_lines = entry_body_lines(entry, options.expand_details);
        let mut body_lines = entry_lines.iter().peekable();
        if body_lines.peek().is_none() {
            lines.push(render_body_line(&entry.kind, "", options.search_query));
        } else {
            for body_line in body_lines {
                lines.push(render_body_line(
                    &entry.kind,
                    body_line,
                    options.search_query,
                ));
            }
        }
        lines.push(Line::default());
    }
    lines
}

pub fn search_match_count(entries: &[TranscriptEntry], query: &str) -> usize {
    let needle = normalized_search(query);
    if needle.is_empty() {
        return 0;
    }
    entries
        .iter()
        .map(|entry| {
            [entry.title.as_str(), entry.body.as_str()]
                .into_iter()
                .map(|value| normalized_search(value).matches(&needle).count())
                .sum::<usize>()
        })
        .sum()
}

fn rendered_entry_line_count(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> usize {
    entries
        .iter()
        .map(|entry| 2 + entry_body_lines(entry, options.expand_details).len().max(1))
        .sum()
}

fn entry_body_lines(entry: &TranscriptEntry, expand_details: bool) -> Vec<String> {
    let body_lines = entry.body.lines().map(str::to_owned).collect::<Vec<_>>();
    if expand_details || !is_collapsible(&entry.kind) || body_lines.len() <= 2 {
        return body_lines;
    }
    let hidden = body_lines.len().saturating_sub(1);
    vec![
        body_lines[0].clone(),
        format!("... {hidden} detail lines hidden (Ctrl-E expand)"),
    ]
}

fn is_collapsible(kind: &TranscriptKind) -> bool {
    matches!(
        kind,
        TranscriptKind::Tool
            | TranscriptKind::Command
            | TranscriptKind::File
            | TranscriptKind::Approval
            | TranscriptKind::Receipt
    )
}

fn transcript_label_style(kind: &TranscriptKind) -> (&'static str, Color) {
    match kind {
        TranscriptKind::System => ("SYSTEM", theme::cyan()),
        TranscriptKind::User => ("YOU", theme::sage()),
        TranscriptKind::Assistant => ("MODEL", theme::primary()),
        TranscriptKind::Progress => ("RUN", theme::amber()),
        TranscriptKind::Tool => ("TOOL", theme::accent()),
        TranscriptKind::File => ("FILE", theme::cyan()),
        TranscriptKind::Command => ("CMD", theme::accent()),
        TranscriptKind::Approval => ("APPROVE", theme::red()),
        TranscriptKind::Receipt => ("RECEIPT", theme::cyan()),
        TranscriptKind::Error => ("ERROR", theme::red()),
    }
}

fn title_style(kind: &TranscriptKind) -> Style {
    match kind {
        TranscriptKind::Assistant => theme::primary_style().add_modifier(Modifier::BOLD),
        TranscriptKind::User => Style::default()
            .fg(theme::sage())
            .add_modifier(Modifier::BOLD),
        TranscriptKind::Approval | TranscriptKind::Error => Style::default()
            .fg(theme::red())
            .add_modifier(Modifier::BOLD),
        TranscriptKind::Progress => Style::default()
            .fg(theme::amber())
            .add_modifier(Modifier::BOLD),
        _ => theme::accent_style(),
    }
}

fn render_body_line(
    kind: &TranscriptKind,
    text: &str,
    search_query: Option<&str>,
) -> Line<'static> {
    let mut spans = vec![Span::styled("  ", theme::mute_style())];
    if let Some(bullet) = text.strip_prefix("- ") {
        spans.push(Span::styled("* ", Style::default().fg(label_color(kind))));
        spans.extend(value_spans(kind, bullet));
    } else if let Some(diff) = diff_line_spans(text) {
        spans.extend(diff);
    } else if let Some((label, value)) = split_key_value(text) {
        spans.push(Span::styled(
            format!("{label}: "),
            Style::default()
                .fg(label_color(kind))
                .add_modifier(Modifier::BOLD),
        ));
        spans.extend(value_spans(kind, value));
    } else {
        spans.extend(value_spans(kind, text));
    }
    highlight_search(spans, search_query)
}

fn diff_line_spans(text: &str) -> Option<Vec<Span<'static>>> {
    if text.starts_with("+++") || text.starts_with("---") {
        return Some(vec![Span::styled(
            text.to_owned(),
            theme::mute_style().add_modifier(Modifier::BOLD),
        )]);
    }
    if text.starts_with('+') {
        return Some(vec![Span::styled(
            text.to_owned(),
            Style::default().fg(theme::sage()),
        )]);
    }
    if text.starts_with('-') {
        return Some(vec![Span::styled(
            text.to_owned(),
            Style::default().fg(theme::red()),
        )]);
    }
    None
}

fn split_key_value(text: &str) -> Option<(&str, &str)> {
    let (label, value) = text.split_once(':')?;
    let trimmed_label = label.trim();
    if trimmed_label.is_empty()
        || trimmed_label.len() > 24
        || !trimmed_label
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == ' ')
    {
        return None;
    }
    Some((trimmed_label, value.trim_start()))
}

fn label_color(kind: &TranscriptKind) -> Color {
    match kind {
        TranscriptKind::Command => theme::accent(),
        TranscriptKind::File => theme::cyan(),
        TranscriptKind::Approval => theme::red(),
        TranscriptKind::Receipt => theme::cyan(),
        TranscriptKind::Error => theme::red(),
        TranscriptKind::Tool => theme::accent(),
        TranscriptKind::Progress => theme::amber(),
        TranscriptKind::System => theme::cyan(),
        TranscriptKind::User => theme::sage(),
        TranscriptKind::Assistant => theme::primary(),
    }
}

fn value_spans(kind: &TranscriptKind, text: &str) -> Vec<Span<'static>> {
    let mut spans = Vec::new();
    match kind {
        TranscriptKind::Command => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(theme::accent()),
        )),
        TranscriptKind::File => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(theme::cyan()),
        )),
        TranscriptKind::Approval => spans.push(Span::styled(
            text.to_owned(),
            Style::default()
                .fg(theme::red())
                .add_modifier(Modifier::BOLD),
        )),
        TranscriptKind::Receipt => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(theme::cyan()),
        )),
        TranscriptKind::Error => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(theme::red()),
        )),
        _ => return highlight_inline_code(text),
    }
    spans
}

fn highlight_inline_code(text: &str) -> Vec<Span<'static>> {
    let mut spans = Vec::new();
    for (index, part) in text.split('`').enumerate() {
        if part.is_empty() {
            continue;
        }
        if index % 2 == 1 {
            spans.push(Span::styled(
                part.to_owned(),
                Style::default()
                    .fg(theme::amber())
                    .add_modifier(Modifier::BOLD),
            ));
        } else {
            spans.push(Span::raw(part.to_owned()));
        }
    }
    if spans.is_empty() {
        spans.push(Span::raw(String::new()));
    }
    spans
}

fn highlight_search(spans: Vec<Span<'static>>, search_query: Option<&str>) -> Line<'static> {
    let Some(query) = search_query else {
        return Line::from(spans);
    };
    let needle = normalized_search(query);
    if needle.is_empty() {
        return Line::from(spans);
    }
    let haystack = normalized_search(
        &spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect::<String>(),
    );
    if !haystack.contains(&needle) {
        return Line::from(spans);
    }
    Line::from(
        spans
            .into_iter()
            .map(|span| {
                Span::styled(
                    span.content.into_owned(),
                    span.style
                        .fg
                        .map_or(span.style, |_| span.style)
                        .add_modifier(Modifier::UNDERLINED),
                )
            })
            .collect::<Vec<_>>(),
    )
}

fn normalized_search(value: &str) -> String {
    value.to_lowercase()
}

#[cfg(test)]
mod tests {
    use super::{
        TranscriptEntry, TranscriptKind, TranscriptRenderOptions, render_transcript_lines,
        render_transcript_lines_window, search_match_count, transcript_scroll_offset,
    };

    #[test]
    fn rendering_labels_entry_kinds() {
        let entries = vec![
            TranscriptEntry::user("You", "hello"),
            TranscriptEntry::new(TranscriptKind::Tool, "Read", "README.md"),
            TranscriptEntry::error("Gateway", "failed"),
        ];

        let rendered = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded())
            .into_iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("YOU You"));
        assert!(rendered.contains("TOOL Read"));
        assert!(rendered.contains("ERROR Gateway"));
    }

    #[test]
    fn scroll_offset_accounts_for_multiline_entries() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "one\ntwo\nthree"),
            TranscriptEntry::progress("Run", "done"),
        ];

        assert_eq!(
            transcript_scroll_offset(&entries, &TranscriptRenderOptions::expanded(), 0, 2),
            6
        );
        assert_eq!(
            transcript_scroll_offset(&entries, &TranscriptRenderOptions::expanded(), 2, 2),
            4
        );
    }

    #[test]
    fn assistant_body_highlights_inline_code() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "Run `cargo test` before merging.",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());
        let body = &lines[1];

        assert_eq!(body.spans[1].content, "Run ");
        assert_eq!(body.spans[2].content, "cargo test");
        assert_eq!(body.spans[2].style.fg, Some(crate::theme::amber()));
    }

    #[test]
    fn command_body_uses_command_style() {
        let entries = vec![TranscriptEntry::new(
            TranscriptKind::Command,
            "Bash",
            "uv run pytest",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[1].content, "uv run pytest");
        assert_eq!(lines[1].spans[1].style.fg, Some(crate::theme::accent()));
    }

    #[test]
    fn transcript_styles_bullets_and_diff_lines() {
        let entries = vec![TranscriptEntry::new(
            TranscriptKind::File,
            "Diff",
            "--- a/src/lib.rs\n+++ b/src/lib.rs\n-old\n+new\n- run_1 [completed]",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[1].style.fg, Some(crate::theme::mute()));
        assert_eq!(lines[2].spans[1].style.fg, Some(crate::theme::mute()));
        assert_eq!(lines[3].spans[1].style.fg, Some(crate::theme::red()));
        assert_eq!(lines[4].spans[1].style.fg, Some(crate::theme::sage()));
        assert_eq!(lines[5].spans[1].to_string(), "* ");
    }

    #[test]
    fn key_value_body_lines_style_label_and_value_separately() {
        let entries = vec![TranscriptEntry::new(
            TranscriptKind::Tool,
            "Bash",
            "Provider: provider_anthropic",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[1].content, "Provider: ");
        assert_eq!(lines[1].spans[1].style.fg, Some(crate::theme::accent()));
        assert_eq!(lines[1].spans[2].content, "provider_anthropic");
    }

    #[test]
    fn empty_body_still_renders_body_row() {
        let entries = vec![TranscriptEntry::system("Gateway", "")];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines.len(), 3);
        assert_eq!(lines[1].spans[0].content, "  ");
    }

    #[test]
    fn collapsed_tool_entries_show_first_line_and_hidden_count() {
        let entries = vec![TranscriptEntry::new(
            TranscriptKind::Tool,
            "Read",
            "Path: src/lib.rs\nSummary: opened file\nDetail: 200 lines",
        )];

        let lines = render_transcript_lines(
            &entries,
            &TranscriptRenderOptions {
                expand_details: false,
                search_query: None,
            },
        );
        let rendered = lines
            .into_iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("Path: src/lib.rs"));
        assert!(rendered.contains("... 2 detail lines hidden"));
        assert!(!rendered.contains("Summary: opened file"));
    }

    #[test]
    fn search_count_matches_title_and_body_case_insensitively() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "Run cargo test"),
            TranscriptEntry::new(TranscriptKind::Command, "Cargo", "cargo clippy"),
        ];

        assert_eq!(search_match_count(&entries, "cargo"), 3);
        assert_eq!(search_match_count(&entries, "missing"), 0);
    }

    #[test]
    fn windowed_rendering_bounds_large_transcripts_near_viewport() {
        let entries = (0..600)
            .map(|index| TranscriptEntry::assistant(&format!("Entry {index}"), "body"))
            .collect::<Vec<_>>();

        let full = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());
        let windowed = render_transcript_lines_window(
            &entries,
            &TranscriptRenderOptions::expanded(),
            transcript_scroll_offset(&entries, &TranscriptRenderOptions::expanded(), 0, 12),
            12,
        );
        let rendered = windowed
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(windowed.len() < full.len());
        assert!(rendered.contains("Entry 599"));
        assert!(!rendered.contains("Entry 0"));
    }
}
