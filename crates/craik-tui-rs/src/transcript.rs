use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};
use std::sync::OnceLock;
use syntect::{
    easy::HighlightLines,
    highlighting::{FontStyle, Style as SyntectStyle, Theme, ThemeSet},
    parsing::{SyntaxReference, SyntaxSet},
};

use crate::theme;

const TRANSCRIPT_RENDER_BUFFER_LINES: usize = 1_000;

pub struct TranscriptEntry {
    pub kind: TranscriptKind,
    pub title: String,
    pub body: String,
    cached_body: Vec<CachedBodyLine>,
}

#[derive(Clone)]
struct CachedBodyLine {
    text: String,
    spans: Vec<Span<'static>>,
    diff_context: bool,
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
            cached_body: parse_cached_body(kind, body),
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

    pub fn update_body(&mut self, body: &str) {
        self.body = body.to_owned();
        self.cached_body = parse_cached_body(self.kind, body);
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
            lines.push(render_body_line(&entry.kind, None, options.search_query));
        } else {
            for body_line in body_lines {
                lines.push(render_body_line(
                    &entry.kind,
                    Some(body_line),
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

fn entry_body_lines(entry: &TranscriptEntry, expand_details: bool) -> Vec<CachedBodyLine> {
    if expand_details || !is_collapsible(&entry.kind) || entry.cached_body.len() <= 2 {
        return entry.cached_body.clone();
    }
    let hidden = entry.cached_body.len().saturating_sub(1);
    vec![
        entry.cached_body[0].clone(),
        CachedBodyLine::plain(format!("... {hidden} detail lines hidden (Ctrl-E expand)")),
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
        TranscriptKind::System => ("CRAIK", theme::mute()),
        TranscriptKind::User => ("YOU", theme::sage()),
        TranscriptKind::Assistant => ("MODEL", theme::primary()),
        TranscriptKind::Progress => ("RUN", theme::amber()),
        TranscriptKind::Tool => ("TOOL", theme::mute()),
        TranscriptKind::File => ("FILE", theme::mute()),
        TranscriptKind::Command => ("CMD", theme::mute()),
        TranscriptKind::Approval => ("APPROVE", theme::red()),
        TranscriptKind::Receipt => ("RECEIPT", theme::mute()),
        TranscriptKind::Error => ("ERROR", theme::red()),
    }
}

fn body_prefix(kind: &TranscriptKind) -> &'static str {
    match kind {
        TranscriptKind::User => "  ▌ ",
        TranscriptKind::Assistant => "    ",
        TranscriptKind::Approval | TranscriptKind::Error => "  ! ",
        _ => "  ┆ ",
    }
}

fn body_prefix_style(kind: &TranscriptKind) -> Style {
    match kind {
        TranscriptKind::User => Style::default().fg(theme::sage()),
        TranscriptKind::Assistant => theme::dim_style(),
        TranscriptKind::Approval | TranscriptKind::Error => Style::default()
            .fg(theme::red())
            .add_modifier(Modifier::BOLD),
        TranscriptKind::Progress => Style::default().fg(theme::amber()),
        _ => theme::mute_style(),
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
        TranscriptKind::System
        | TranscriptKind::Tool
        | TranscriptKind::File
        | TranscriptKind::Command
        | TranscriptKind::Receipt => theme::dim_style(),
    }
}

fn render_body_line(
    kind: &TranscriptKind,
    cached: Option<&CachedBodyLine>,
    search_query: Option<&str>,
) -> Line<'static> {
    let Some(cached) = cached else {
        let spans = vec![Span::styled(body_prefix(kind), body_prefix_style(kind))];
        return highlight_search(spans, search_query);
    };
    if let Some(diff) = diff_line_spans(kind, cached) {
        let mut spans = vec![Span::styled(
            body_prefix(kind),
            body_prefix_style(kind).bg(diff.background),
        )];
        spans.extend(diff.spans);
        return highlight_search(spans, search_query);
    }
    let mut spans = vec![Span::styled(body_prefix(kind), body_prefix_style(kind))];
    if let Some(markdown) = markdown_line_spans(&cached.text) {
        spans.extend(markdown);
    } else if let Some(bullet) = cached.text.strip_prefix("- ") {
        spans.push(Span::styled("* ", Style::default().fg(label_color(kind))));
        spans.extend(value_spans(kind, bullet));
    } else if !cached.spans.is_empty() {
        spans.extend(cached.spans.clone());
    } else if let Some((label, value)) = split_key_value(&cached.text) {
        spans.push(Span::styled(format!("{label}: "), key_label_style(kind)));
        spans.extend(value_spans(kind, value));
    } else {
        spans.extend(value_spans(kind, &cached.text));
    }
    highlight_search(spans, search_query)
}

fn key_label_style(kind: &TranscriptKind) -> Style {
    let color = match kind {
        TranscriptKind::User => theme::sage(),
        TranscriptKind::Assistant => theme::mute(),
        TranscriptKind::Approval | TranscriptKind::Error => theme::red(),
        TranscriptKind::Progress => theme::amber(),
        _ => theme::mute(),
    };
    Style::default().fg(color).add_modifier(Modifier::BOLD)
}

impl CachedBodyLine {
    fn plain(text: String) -> Self {
        Self {
            text,
            spans: Vec::new(),
            diff_context: false,
        }
    }

    fn styled(text: String, spans: Vec<Span<'static>>) -> Self {
        Self {
            text,
            spans,
            diff_context: false,
        }
    }

    fn diff(text: String, spans: Vec<Span<'static>>) -> Self {
        Self {
            text,
            spans,
            diff_context: true,
        }
    }
}

fn parse_cached_body(kind: TranscriptKind, body: &str) -> Vec<CachedBodyLine> {
    let mut lines = Vec::new();
    let mut code_highlighter: Option<CodeBlockHighlighter> = None;
    let mut code_block_is_diff = false;
    let body_is_diff = matches!(kind, TranscriptKind::File)
        && body.lines().any(|line| {
            line.starts_with("---") || line.starts_with("+++") || line.starts_with("@@")
        });
    for raw in body.lines() {
        if let Some(language) = raw.trim_start().strip_prefix("```") {
            let language = language.trim();
            if code_highlighter.is_some() {
                code_highlighter = None;
                code_block_is_diff = false;
            } else {
                code_block_is_diff = is_diff_language(language);
                code_highlighter = Some(CodeBlockHighlighter::new(language));
            };
            let fence_spans = vec![Span::styled(
                raw.to_owned(),
                theme::mute_style().add_modifier(Modifier::BOLD),
            )];
            lines.push(if code_block_is_diff {
                CachedBodyLine::diff(raw.to_owned(), fence_spans)
            } else {
                CachedBodyLine::styled(raw.to_owned(), fence_spans)
            });
            continue;
        }
        if let Some(highlighter) = code_highlighter.as_mut() {
            let spans = highlighter.highlight_line(raw);
            lines.push(if code_block_is_diff {
                CachedBodyLine::diff(raw.to_owned(), spans)
            } else {
                CachedBodyLine::styled(raw.to_owned(), spans)
            });
        } else if matches!(kind, TranscriptKind::Assistant | TranscriptKind::System) {
            lines.push(CachedBodyLine::styled(
                raw.to_owned(),
                highlight_typed_facts(raw),
            ));
        } else if body_is_diff {
            lines.push(CachedBodyLine::diff(raw.to_owned(), Vec::new()));
        } else {
            lines.push(CachedBodyLine::plain(raw.to_owned()));
        }
    }
    lines
}

fn is_diff_language(language: &str) -> bool {
    matches!(
        language.trim().to_ascii_lowercase().as_str(),
        "diff" | "patch" | "udiff"
    )
}

struct CodeBlockHighlighter {
    highlighter: HighlightLines<'static>,
}

impl CodeBlockHighlighter {
    fn new(language: &str) -> Self {
        let syntax = syntax_for_language(language);
        Self {
            highlighter: HighlightLines::new(syntax, syntax_theme()),
        }
    }

    fn highlight_line(&mut self, text: &str) -> Vec<Span<'static>> {
        if text.is_empty() {
            return vec![Span::raw(String::new())];
        }
        self.highlighter
            .highlight_line(text, syntax_set())
            .map(|ranges| {
                ranges
                    .into_iter()
                    .map(|(style, text)| Span::styled(text.to_owned(), mapped_syntax_style(style)))
                    .collect()
            })
            .unwrap_or_else(|_| vec![Span::styled(text.to_owned(), theme::primary_style())])
    }
}

fn syntax_set() -> &'static SyntaxSet {
    static SYNTAX_SET: OnceLock<SyntaxSet> = OnceLock::new();
    SYNTAX_SET.get_or_init(SyntaxSet::load_defaults_newlines)
}

fn syntax_theme() -> &'static Theme {
    static THEME_SET: OnceLock<ThemeSet> = OnceLock::new();
    let themes = THEME_SET.get_or_init(ThemeSet::load_defaults);
    themes
        .themes
        .get("base16-ocean.dark")
        .or_else(|| themes.themes.values().next())
        .expect("syntect ships with at least one default theme")
}

fn syntax_for_language(language: &str) -> &'static SyntaxReference {
    let syntaxes = syntax_set();
    let language = language.trim();
    syntaxes
        .find_syntax_by_token(language)
        .or_else(|| syntaxes.find_syntax_by_extension(language))
        .unwrap_or_else(|| syntaxes.find_syntax_plain_text())
}

fn mapped_syntax_style(style: SyntectStyle) -> Style {
    let mut ratatui_style = Style::default().fg(syntax_color(style));
    if style.font_style.contains(FontStyle::BOLD) {
        ratatui_style = ratatui_style.add_modifier(Modifier::BOLD);
    }
    if style.font_style.contains(FontStyle::ITALIC) {
        ratatui_style = ratatui_style.add_modifier(Modifier::ITALIC);
    }
    ratatui_style
}

fn syntax_color(style: SyntectStyle) -> Color {
    let color = style.foreground;
    let red = color.r;
    let green = color.g;
    let blue = color.b;
    if green > red.saturating_add(24) && green > blue.saturating_add(12) {
        theme::sage()
    } else if red > green.saturating_add(28) && red > blue.saturating_add(12) {
        theme::red()
    } else if blue > red.saturating_add(24) && blue > green.saturating_add(12) {
        theme::cyan()
    } else if red > 170 && green > 130 && blue < 130 {
        theme::amber()
    } else if red > 140 && blue > 140 {
        theme::accent()
    } else {
        theme::primary()
    }
}

fn highlight_typed_facts(text: &str) -> Vec<Span<'static>> {
    if let Some((label, value)) = split_key_value(text) {
        return vec![
            Span::styled(
                format!("{label}: "),
                theme::mute_style().add_modifier(Modifier::BOLD),
            ),
            Span::styled(value.to_owned(), Style::default().fg(theme::sage())),
        ];
    }
    Vec::new()
}

struct DiffLine {
    background: Color,
    spans: Vec<Span<'static>>,
}

fn diff_line_spans(kind: &TranscriptKind, cached: &CachedBodyLine) -> Option<DiffLine> {
    let text = cached.text.as_str();
    if text.starts_with("+++") || text.starts_with("---") {
        return Some(DiffLine {
            background: Color::Reset,
            spans: vec![Span::styled(
                text.to_owned(),
                theme::mute_style().add_modifier(Modifier::BOLD),
            )],
        });
    }
    let diff_context = cached.diff_context
        || matches!(
            kind,
            TranscriptKind::Tool | TranscriptKind::Command | TranscriptKind::Approval
        );
    if !diff_context {
        return None;
    }
    let (marker, value, foreground, background) = if let Some(value) = text.strip_prefix('+') {
        ("+", value, theme::sage(), theme::sage_surface())
    } else if let Some(value) = text.strip_prefix('-') {
        ("-", value, theme::red(), theme::red_surface())
    } else {
        return None;
    };
    let base_style = Style::default().fg(theme::primary()).bg(background);
    Some(DiffLine {
        background,
        spans: vec![
            Span::styled(
                marker.to_owned(),
                Style::default()
                    .fg(foreground)
                    .bg(background)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(value.to_owned(), base_style),
        ],
    })
}

fn markdown_line_spans(text: &str) -> Option<Vec<Span<'static>>> {
    let trimmed = text.trim_start();
    let indent = &text[..text.len().saturating_sub(trimmed.len())];
    if let Some(heading) = trimmed.strip_prefix("### ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled("### ", theme::mute_style().add_modifier(Modifier::BOLD)),
            Span::styled(heading.to_owned(), theme::accent_style()),
        ]);
    }
    if let Some(heading) = trimmed.strip_prefix("## ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled("## ", theme::mute_style().add_modifier(Modifier::BOLD)),
            Span::styled(heading.to_owned(), theme::accent_style()),
        ]);
    }
    if let Some(heading) = trimmed.strip_prefix("# ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled("# ", theme::mute_style().add_modifier(Modifier::BOLD)),
            Span::styled(
                heading.to_owned(),
                theme::primary_style().add_modifier(Modifier::BOLD),
            ),
        ]);
    }
    if let Some(quote) = trimmed.strip_prefix("> ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled("> ", Style::default().fg(theme::cyan())),
            Span::styled(quote.to_owned(), theme::dim_style()),
        ]);
    }
    let (marker, value) = ordered_list_marker(trimmed)?;
    Some(vec![
        Span::styled(indent.to_owned(), theme::mute_style()),
        Span::styled(marker.to_owned(), Style::default().fg(theme::accent())),
        Span::styled(" ", theme::mute_style()),
        Span::styled(value.to_owned(), theme::primary_style()),
    ])
}

fn ordered_list_marker(text: &str) -> Option<(&str, &str)> {
    let (marker, value) = text.split_once(' ')?;
    let number = marker.strip_suffix('.')?;
    (!number.is_empty() && number.chars().all(|character| character.is_ascii_digit()))
        .then_some((marker, value))
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
            TranscriptEntry::system("Gateway", "connected"),
            TranscriptEntry::user("You", "hello"),
            TranscriptEntry::new(TranscriptKind::Tool, "Read", "README.md"),
            TranscriptEntry::error("Gateway", "failed"),
        ];

        let rendered = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded())
            .into_iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("CRAIK Gateway"));
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
    fn assistant_body_highlights_fenced_code_blocks_from_cached_lines() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "```rust\nfn main() {\n    let value = 42;\n}\n```",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[2].spans[1].content, "fn");
        assert_eq!(lines[2].spans[1].style.fg, Some(crate::theme::accent()));
        let let_span = lines[3]
            .spans
            .iter()
            .find(|span| span.content.as_ref() == "let")
            .expect("let keyword is highlighted");
        assert_eq!(let_span.style.fg, Some(crate::theme::accent()));
        let number_span = lines[3]
            .spans
            .iter()
            .find(|span| span.content.as_ref() == "42")
            .expect("number literal is highlighted");
        assert_ne!(number_span.style.fg, Some(crate::theme::primary()));
    }

    #[test]
    fn fenced_python_uses_syntect_parser_not_keyword_scanner() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "```python\nclass Runner:\n    def run(self):\n        return {'ok': True}\n```",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());
        let class_span = lines[2]
            .spans
            .iter()
            .find(|span| span.content.as_ref() == "class")
            .expect("python class keyword is tokenized");
        let true_span = lines[4]
            .spans
            .iter()
            .find(|span| span.content.as_ref() == "True")
            .expect("python boolean literal is tokenized");

        assert_ne!(class_span.style.fg, Some(crate::theme::primary()));
        assert_ne!(true_span.style.fg, Some(crate::theme::primary()));
    }

    #[test]
    fn markdown_headings_quotes_and_ordered_lists_are_styled() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "# Plan\n> important context\n1. First step",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[2].content, "# ");
        assert_eq!(lines[1].spans[3].content, "Plan");
        assert_eq!(lines[1].spans[3].style.fg, Some(crate::theme::primary()));
        assert_eq!(lines[2].spans[2].content, "> ");
        assert_eq!(lines[2].spans[3].style.fg, Some(crate::theme::dim()));
        assert_eq!(lines[3].spans[2].content, "1.");
        assert_eq!(lines[3].spans[2].style.fg, Some(crate::theme::accent()));
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
        assert_eq!(
            lines[3].spans[1].style.bg,
            Some(crate::theme::red_surface())
        );
        assert_eq!(
            lines[3].spans[2].style.bg,
            Some(crate::theme::red_surface())
        );
        assert_eq!(lines[4].spans[1].style.fg, Some(crate::theme::sage()));
        assert_eq!(
            lines[4].spans[1].style.bg,
            Some(crate::theme::sage_surface())
        );
        assert_eq!(
            lines[4].spans[2].style.bg,
            Some(crate::theme::sage_surface())
        );
        assert_eq!(
            lines[5].spans[1].style.bg,
            Some(crate::theme::red_surface())
        );
    }

    #[test]
    fn markdown_bullets_are_not_tinted_as_diff_outside_diff_context() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "- keep markdown bullet\n+ not a diff addition",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[1].to_string(), "* ");
        assert_eq!(lines[1].spans[1].style.bg, None);
        assert_eq!(lines[2].spans[1].style.bg, None);
    }

    #[test]
    fn fenced_diff_blocks_use_background_tints() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "```diff\n-old\n+new\n context\n```",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(
            lines[2].spans[1].style.bg,
            Some(crate::theme::red_surface())
        );
        assert_eq!(
            lines[3].spans[1].style.bg,
            Some(crate::theme::sage_surface())
        );
        assert_eq!(lines[4].spans[1].style.bg, None);
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
        assert_eq!(lines[1].spans[1].style.fg, Some(crate::theme::mute()));
        assert_eq!(lines[1].spans[2].content, "provider_anthropic");
    }

    #[test]
    fn empty_body_still_renders_body_row() {
        let entries = vec![TranscriptEntry::system("Gateway", "")];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines.len(), 3);
        assert_eq!(lines[1].spans[0].content, "  ┆ ");
    }

    #[test]
    fn user_model_and_craik_body_lanes_are_distinct() {
        let entries = vec![
            TranscriptEntry::user("You", "review this"),
            TranscriptEntry::assistant("Assistant", "Looks good."),
            TranscriptEntry::system("Gateway", "Receipt: receipt_1"),
        ];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[0].content, "  ▌ ");
        assert_eq!(lines[4].spans[0].content, "    ");
        assert_eq!(lines[7].spans[0].content, "  ┆ ");
    }

    #[test]
    fn transcript_lane_styles_keep_model_primary_and_craik_subdued() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "Model response"),
            TranscriptEntry::new(TranscriptKind::Receipt, "Receipt", "ID: receipt_1"),
            TranscriptEntry::new(TranscriptKind::Approval, "Approval", "Target: src/lib.rs"),
        ];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[0].spans[1].content, "MODEL ");
        assert_eq!(lines[0].spans[1].style.fg, Some(crate::theme::primary()));
        assert_eq!(lines[3].spans[1].content, "RECEIPT ");
        assert_eq!(lines[3].spans[1].style.fg, Some(crate::theme::mute()));
        assert_eq!(lines[4].spans[0].content, "  ┆ ");
        assert_eq!(lines[6].spans[1].content, "APPROVE ");
        assert_eq!(lines[7].spans[0].content, "  ! ");
        assert_eq!(lines[7].spans[0].style.fg, Some(crate::theme::red()));
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
