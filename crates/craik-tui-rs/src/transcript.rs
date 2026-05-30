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

#[cfg(test)]
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
    pub content_width: Option<usize>,
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
            content_width: None,
        }
    }
}

#[cfg(test)]
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

#[cfg(test)]
pub fn transcript_line_count(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> u16 {
    rendered_entry_line_count(entries, options).min(u16::MAX as usize) as u16
}

pub fn render_transcript_lines(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> Vec<Line<'static>> {
    let entries = entries.iter().collect::<Vec<_>>();
    render_entries(&entries, options)
}

#[cfg(test)]
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
        let entry_line_count = rendered_single_entry_line_count(entry, options);
        let entry_end = cursor + entry_line_count;
        if entry_end >= start && cursor <= end {
            visible_entries.push(entry);
        }
        cursor = entry_end;
    }
    render_entries(&visible_entries, options)
}

#[cfg(test)]
pub fn transcript_render_window_start(scroll_offset: u16) -> u16 {
    scroll_offset.saturating_sub(TRANSCRIPT_RENDER_BUFFER_LINES.min(usize::from(u16::MAX)) as u16)
}

fn render_entries(
    entries: &[&TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    for entry in entries {
        if entry.kind == TranscriptKind::User && is_generic_user_title(&entry.title) {
            lines.extend(render_user_entry(entry, options));
            continue;
        }
        if matches!(entry.kind, TranscriptKind::Assistant)
            && lines.last().is_some_and(|line| !line.spans.is_empty())
        {
            lines.push(Line::default());
        }
        if should_render_entry_header(entry) {
            let (label, color) = transcript_label_style(&entry.kind);
            lines.push(highlight_search(
                vec![
                    Span::styled(header_marker(&entry.kind), Style::default().fg(color)),
                    Span::styled(format!("{label} "), label_style(&entry.kind, color)),
                    Span::styled(entry.title.clone(), title_style(&entry.kind)),
                ],
                options.search_query,
            ));
        }
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
        if entry_separator_lines(&entry.kind) > 0 {
            lines.push(Line::default());
        }
    }
    lines
}

fn render_user_entry(
    entry: &TranscriptEntry,
    options: &TranscriptRenderOptions<'_>,
) -> Vec<Line<'static>> {
    let width = options.content_width.unwrap_or(72).max(12);
    let background = theme::surface();
    let blank = Line::from(Span::styled(
        " ".repeat(width),
        Style::default().bg(background),
    ));
    let mut lines = vec![Line::default(), blank.clone()];
    let body_lines = entry_body_lines(entry, options.expand_details);
    if body_lines.is_empty() {
        lines.push(user_surface_line("", width, options.search_query));
    } else {
        lines.extend(
            body_lines
                .iter()
                .map(|line| user_surface_line(&line.text, width, options.search_query)),
        );
    }
    lines.push(blank);
    lines.push(Line::default());
    lines
}

fn user_surface_line(text: &str, width: usize, search_query: Option<&str>) -> Line<'static> {
    let available = width.saturating_sub(4);
    let clamped = if text.chars().count() > available {
        compact_display_text(text, available)
    } else {
        text.to_owned()
    };
    let clamped_width = clamped.chars().count();
    let left = 2.min(width);
    let right = width.saturating_sub(left).saturating_sub(clamped_width);
    highlight_search(
        vec![
            Span::styled(" ".repeat(left), Style::default().bg(theme::surface())),
            Span::styled(clamped, theme::primary_style().bg(theme::surface())),
            Span::styled(" ".repeat(right), Style::default().bg(theme::surface())),
        ],
        search_query,
    )
}

fn compact_display_text(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_owned();
    }
    let keep = max_chars.saturating_sub(3);
    format!("{}...", text.chars().take(keep).collect::<String>())
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

#[cfg(test)]
fn rendered_entry_line_count(
    entries: &[TranscriptEntry],
    options: &TranscriptRenderOptions<'_>,
) -> usize {
    entries
        .iter()
        .map(|entry| rendered_single_entry_line_count(entry, options))
        .sum()
}

#[cfg(test)]
fn rendered_single_entry_line_count(
    entry: &TranscriptEntry,
    options: &TranscriptRenderOptions<'_>,
) -> usize {
    usize::from(should_render_entry_header(entry))
        + if entry.kind == TranscriptKind::User && is_generic_user_title(&entry.title) {
            entry_body_lines(entry, options.expand_details).len().max(1) + 3
        } else {
            entry_body_lines(entry, options.expand_details).len().max(1)
        }
        + entry_separator_lines(&entry.kind)
}

fn entry_body_lines(entry: &TranscriptEntry, expand_details: bool) -> Vec<CachedBodyLine> {
    if expand_details || !is_collapsible(&entry.kind) || entry.cached_body.len() <= 1 {
        return entry.cached_body.clone();
    }
    if is_evidence_kind(&entry.kind)
        && let Some(line) = collapsed_evidence_line(entry)
    {
        return vec![CachedBodyLine::plain(line)];
    }
    if entry.kind == TranscriptKind::Approval
        && let Some(line) = collapsed_approval_line(entry)
    {
        return vec![CachedBodyLine::plain(line)];
    }
    let hidden = entry.cached_body.len().saturating_sub(1);
    vec![
        entry.cached_body[0].clone(),
        CachedBodyLine::plain(format!("... {hidden} detail lines hidden (Ctrl-E expand)")),
    ]
}

fn collapsed_approval_line(entry: &TranscriptEntry) -> Option<String> {
    let id = entry.body.lines().find_map(|line| {
        line.trim()
            .strip_prefix("ID: ")
            .or_else(|| line.trim().strip_prefix("Approval: "))
    });
    let message = entry
        .body
        .lines()
        .find_map(|line| line.trim().strip_prefix("Message: "))
        .or_else(|| {
            entry
                .body
                .lines()
                .find_map(|line| line.trim().strip_prefix("Tool: "))
        })
        .or_else(|| {
            entry
                .body
                .lines()
                .find_map(|line| line.trim().strip_prefix("Target: "))
        });
    match (id, message) {
        (Some(id), Some(message)) => Some(format!("ID: {id} · {message}")),
        (Some(id), None) => Some(format!("ID: {id}")),
        (None, Some(message)) => Some(message.to_owned()),
        (None, None) => None,
    }
}

fn collapsed_evidence_line(entry: &TranscriptEntry) -> Option<String> {
    let lines = entry
        .body
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>();
    match entry.kind {
        TranscriptKind::Command => lines
            .iter()
            .find_map(|line| line.strip_prefix("Command: "))
            .or_else(|| lines.iter().find_map(|line| line.strip_prefix("Detail: ")))
            .map(|value| format!("Command: {value}")),
        TranscriptKind::Tool => lines
            .iter()
            .find_map(|line| line.strip_prefix("Target: "))
            .or_else(|| lines.iter().find_map(|line| line.strip_prefix("Path: ")))
            .map(|value| format!("Target: {value}"))
            .or_else(|| {
                lines
                    .iter()
                    .find_map(|line| line.strip_prefix("Detail: "))
                    .map(str::to_owned)
            }),
        TranscriptKind::File => lines
            .iter()
            .find_map(|line| line.strip_prefix("Path: "))
            .map(|value| format!("Path: {value}")),
        TranscriptKind::Receipt => lines.first().map(|line| (*line).to_owned()),
        _ => None,
    }
}

fn is_collapsible(kind: &TranscriptKind) -> bool {
    matches!(
        kind,
        TranscriptKind::System
            | TranscriptKind::Progress
            | TranscriptKind::Tool
            | TranscriptKind::Command
            | TranscriptKind::File
            | TranscriptKind::Approval
            | TranscriptKind::Receipt
    )
}

fn should_render_entry_header(entry: &TranscriptEntry) -> bool {
    match entry.kind {
        TranscriptKind::Assistant => !is_generic_assistant_title(&entry.title),
        TranscriptKind::User => !is_generic_user_title(&entry.title),
        _ => true,
    }
}

fn is_generic_assistant_title(title: &str) -> bool {
    matches!(
        title.trim().to_ascii_lowercase().as_str(),
        "assistant" | "model"
    )
}

fn is_generic_user_title(title: &str) -> bool {
    matches!(title.trim().to_ascii_lowercase().as_str(), "you" | "user")
}

fn header_marker(kind: &TranscriptKind) -> &'static str {
    match kind {
        TranscriptKind::Tool
        | TranscriptKind::File
        | TranscriptKind::Command
        | TranscriptKind::Progress
        | TranscriptKind::Receipt
        | TranscriptKind::System => "· ",
        _ => "▌ ",
    }
}

fn transcript_label_style(kind: &TranscriptKind) -> (&'static str, Color) {
    match kind {
        TranscriptKind::System => ("craik", theme::mute()),
        TranscriptKind::User => ("you", theme::sage()),
        TranscriptKind::Assistant => ("assistant", theme::primary()),
        TranscriptKind::Progress => ("run", theme::amber()),
        TranscriptKind::Tool => ("tool", theme::mute()),
        TranscriptKind::File => ("file", theme::mute()),
        TranscriptKind::Command => ("cmd", theme::mute()),
        TranscriptKind::Approval => ("approval", theme::red()),
        TranscriptKind::Receipt => ("evidence", theme::mute()),
        TranscriptKind::Error => ("error", theme::red()),
    }
}

fn label_style(kind: &TranscriptKind, color: Color) -> Style {
    let base = Style::default().fg(color);
    if is_evidence_kind(kind) {
        base
    } else {
        base.add_modifier(Modifier::BOLD)
    }
}

fn entry_separator_lines(kind: &TranscriptKind) -> usize {
    if matches!(kind, TranscriptKind::User) {
        return 0;
    }
    if is_evidence_kind(kind) { 0 } else { 1 }
}

fn is_evidence_kind(kind: &TranscriptKind) -> bool {
    matches!(
        kind,
        TranscriptKind::System
            | TranscriptKind::Progress
            | TranscriptKind::Tool
            | TranscriptKind::File
            | TranscriptKind::Command
            | TranscriptKind::Receipt
    )
}

fn body_prefix(kind: &TranscriptKind) -> &'static str {
    match kind {
        TranscriptKind::User => "  ",
        TranscriptKind::Assistant => "  ",
        TranscriptKind::Approval | TranscriptKind::Error => "  ! ",
        TranscriptKind::System | TranscriptKind::Progress => "  · ",
        TranscriptKind::Receipt => "  ⌁ ",
        TranscriptKind::Tool | TranscriptKind::File | TranscriptKind::Command => "  · ",
    }
}

fn body_prefix_style(kind: &TranscriptKind) -> Style {
    match kind {
        TranscriptKind::User => Style::default().fg(theme::primary()).bg(theme::surface()),
        TranscriptKind::Assistant => theme::mute_style(),
        TranscriptKind::Approval | TranscriptKind::Error => Style::default()
            .fg(theme::red())
            .add_modifier(Modifier::BOLD),
        TranscriptKind::Progress => Style::default().fg(theme::amber()),
        _ => theme::dim_style(),
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
        let spans = body_prefix_spans(kind);
        return highlight_search(spans, search_query);
    };
    if let Some(diff) = diff_line_spans(kind, cached) {
        let mut spans =
            body_prefix_spans_with_style(kind, body_prefix_style(kind).bg(diff.background));
        spans.extend(diff.spans);
        return highlight_search(spans, search_query);
    }
    let mut spans = body_prefix_spans(kind);
    if let Some(markdown) = markdown_line_spans(&cached.text) {
        spans.extend(markdown);
    } else if matches!(kind, TranscriptKind::Assistant | TranscriptKind::System)
        && let Some(section) = plaintext_section_heading_spans(&cached.text)
    {
        spans.extend(section);
    } else if matches!(kind, TranscriptKind::Assistant | TranscriptKind::System)
        && let Some(lead) = leading_bold_label_spans(&cached.text, kind)
    {
        spans.extend(lead);
    } else if let Some(bullet) = cached
        .text
        .strip_prefix("- ")
        .or_else(|| cached.text.strip_prefix("* "))
    {
        spans.push(Span::styled("* ", Style::default().fg(label_color(kind))));
        if matches!(kind, TranscriptKind::Assistant | TranscriptKind::System)
            && let Some(lead) = leading_bold_label_spans(bullet, kind)
        {
            spans.extend(lead);
        } else {
            spans.extend(value_spans(kind, bullet));
        }
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

fn body_prefix_spans(kind: &TranscriptKind) -> Vec<Span<'static>> {
    body_prefix_spans_with_style(kind, body_prefix_style(kind))
}

fn body_prefix_spans_with_style(kind: &TranscriptKind, style: Style) -> Vec<Span<'static>> {
    let prefix = body_prefix(kind);
    if prefix.is_empty() {
        Vec::new()
    } else {
        vec![Span::styled(prefix, style)]
    }
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
            if should_pad_before_markdown_line(raw, &lines) {
                lines.push(CachedBodyLine::plain(String::new()));
            }
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
    if (matches!(kind, TranscriptKind::File) || cached.diff_context)
        && (text.starts_with("+++") || text.starts_with("---"))
    {
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
    if is_thematic_break(trimmed) {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled("─".repeat(28), theme::mute_style()),
        ]);
    }
    if let Some(heading) = trimmed.strip_prefix("### ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled(heading.to_owned(), theme::accent_style()),
        ]);
    }
    if let Some(heading) = trimmed.strip_prefix("## ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
            Span::styled(heading.to_owned(), theme::accent_style()),
        ]);
    }
    if let Some(heading) = trimmed.strip_prefix("# ") {
        return Some(vec![
            Span::styled(indent.to_owned(), theme::mute_style()),
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

fn should_pad_before_markdown_line(raw: &str, lines: &[CachedBodyLine]) -> bool {
    if lines.is_empty() || last_cached_line_is_blank(lines) {
        return false;
    }
    let trimmed = raw.trim_start();
    is_markdown_heading(raw)
        || is_thematic_break(trimmed)
        || plaintext_section_heading_spans(raw).is_some()
        || leading_bold_label_spans(raw, &TranscriptKind::Assistant).is_some()
        || ordered_list_marker(trimmed).is_some()
        || trimmed.starts_with("- ")
        || trimmed.starts_with("* ")
}

fn is_markdown_heading(text: &str) -> bool {
    let trimmed = text.trim_start();
    trimmed.starts_with("# ") || trimmed.starts_with("## ") || trimmed.starts_with("### ")
}

fn is_thematic_break(trimmed: &str) -> bool {
    matches!(trimmed, "---" | "----" | "***" | "___")
}

fn last_cached_line_is_blank(lines: &[CachedBodyLine]) -> bool {
    lines.last().is_some_and(|line| line.text.trim().is_empty())
}

fn ordered_list_marker(text: &str) -> Option<(&str, &str)> {
    let (marker, value) = text.split_once(' ')?;
    let number = marker.strip_suffix('.')?;
    (!number.is_empty() && number.chars().all(|character| character.is_ascii_digit()))
        .then_some((marker, value))
}

fn plaintext_section_heading_spans(text: &str) -> Option<Vec<Span<'static>>> {
    let trimmed = text.trim();
    if trimmed.is_empty()
        || trimmed.len() > 56
        || trimmed.contains("**")
        || trimmed.contains('`')
        || trimmed.starts_with("- ")
        || trimmed.starts_with("* ")
        || ordered_list_marker(trimmed).is_some()
    {
        return None;
    }
    let normalized = trimmed.trim_end_matches(':');
    if normalized.ends_with('.')
        || normalized.contains(',')
        || normalized
            .chars()
            .any(|character| matches!(character, '(' | ')' | '/' | '\\'))
    {
        return None;
    }
    let words = normalized.split_whitespace().collect::<Vec<_>>();
    if words.is_empty() || words.len() > 5 {
        return None;
    }
    let has_section_keyword = words.iter().any(|word| {
        matches!(
            word.to_ascii_lowercase().as_str(),
            "assessment"
                | "findings"
                | "recommendation"
                | "recommendations"
                | "review"
                | "summary"
                | "strengths"
                | "risks"
        )
    });
    let title_case = words.iter().all(|word| {
        word.chars()
            .next()
            .is_some_and(|character| character.is_ascii_uppercase())
    });
    let heading_like = has_section_keyword || title_case;
    heading_like.then(|| {
        vec![Span::styled(
            trimmed.to_owned(),
            theme::accent_style().add_modifier(Modifier::BOLD),
        )]
    })
}

fn leading_bold_label_spans(text: &str, kind: &TranscriptKind) -> Option<Vec<Span<'static>>> {
    let trimmed = text.trim_start();
    let indent = &text[..text.len().saturating_sub(trimmed.len())];
    let rest = trimmed.strip_prefix("**")?;
    let (label, value) = rest.split_once("**")?;
    let label = label.trim();
    let value = value.trim_start();
    if label.is_empty() || label.len() > 72 || value.is_empty() {
        return None;
    }
    let label_style = match kind {
        TranscriptKind::System => Style::default()
            .fg(theme::cyan())
            .add_modifier(Modifier::BOLD),
        _ => theme::accent_style().add_modifier(Modifier::BOLD),
    };
    let mut spans = vec![
        Span::styled(indent.to_owned(), theme::mute_style()),
        Span::styled(label.to_owned(), label_style),
    ];
    if !label.ends_with(['.', ':', '?', '!']) {
        spans.push(Span::styled(":".to_owned(), label_style));
    }
    spans.push(Span::styled(" ", theme::mute_style()));
    spans.extend(value_spans(kind, value));
    Some(spans)
}

fn split_key_value(text: &str) -> Option<(&str, &str)> {
    let (label, value) = text.split_once(':')?;
    let trimmed_label = label.trim().trim_matches('*');
    if trimmed_label.is_empty()
        || trimmed_label.len() > 24
        || !trimmed_label
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == ' ')
    {
        return None;
    }
    let trimmed_value = value
        .trim_start()
        .strip_prefix("**")
        .unwrap_or(value.trim_start());
    Some((trimmed_label, trimmed_value.trim_start()))
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
        TranscriptKind::User => {
            return highlight_inline_code(text, theme::primary_style().bg(theme::surface()));
        }
        TranscriptKind::Assistant => {
            return highlight_inline_code(text, theme::primary_style());
        }
        TranscriptKind::System | TranscriptKind::Progress | TranscriptKind::Tool => {
            return highlight_inline_code(text, theme::dim_style());
        }
    }
    spans
}

fn highlight_inline_code(text: &str, base_style: Style) -> Vec<Span<'static>> {
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
            push_inline_text_spans(&mut spans, part, base_style);
        }
    }
    if spans.is_empty() {
        spans.push(Span::styled(String::new(), base_style));
    }
    spans
}

fn push_inline_text_spans(spans: &mut Vec<Span<'static>>, text: &str, base_style: Style) {
    let mut remaining = text;
    while let Some(start) = remaining.find("**") {
        let (before, after_start) = remaining.split_at(start);
        if !before.is_empty() {
            spans.push(Span::styled(before.to_owned(), base_style));
        }
        let after_start = &after_start[2..];
        let Some(end) = after_start.find("**") else {
            spans.push(Span::styled(format!("**{after_start}"), base_style));
            return;
        };
        let (bold, after_end) = after_start.split_at(end);
        if !bold.is_empty() {
            spans.push(Span::styled(
                bold.to_owned(),
                base_style.add_modifier(Modifier::BOLD),
            ));
        }
        remaining = &after_end[2..];
    }
    if !remaining.is_empty() {
        spans.push(Span::styled(remaining.to_owned(), base_style));
    }
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
    use ratatui::style::Modifier;

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

        assert!(rendered.contains("craik Gateway"));
        assert!(rendered.contains("hello"));
        assert!(!rendered.contains("you You"));
        assert!(rendered.contains("tool Read"));
        assert!(rendered.contains("error Gateway"));
    }

    #[test]
    fn scroll_offset_accounts_for_multiline_entries() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "one\ntwo\nthree"),
            TranscriptEntry::progress("Run", "done"),
        ];

        assert_eq!(
            transcript_scroll_offset(&entries, &TranscriptRenderOptions::expanded(), 0, 2),
            4
        );
        assert_eq!(
            transcript_scroll_offset(&entries, &TranscriptRenderOptions::expanded(), 2, 2),
            2
        );
    }

    #[test]
    fn assistant_body_highlights_inline_code() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "Run `cargo test` before merging.",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());
        let body = &lines[0];

        assert_eq!(body.spans[0].content, "  ");
        assert_eq!(body.spans[1].content, "Run ");
        assert_eq!(body.spans[2].content, "cargo test");
        assert_eq!(body.spans[2].style.fg, Some(crate::theme::amber()));
    }

    #[test]
    fn custom_assistant_titles_still_render_header_context() {
        let entries = vec![TranscriptEntry::assistant("Review Summary", "Looks good.")];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[0].spans[1].content, "assistant ");
        assert_eq!(lines[0].spans[2].content, "Review Summary");
        assert_eq!(lines[1].spans[0].content, "  ");
        assert_eq!(lines[1].spans[1].content, "Looks good.");
    }

    #[test]
    fn assistant_body_highlights_fenced_code_blocks_from_cached_lines() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "```rust\nfn main() {\n    let value = 42;\n}\n```",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[1].spans[0].content, "  ");
        assert_eq!(lines[1].spans[1].content, "fn");
        assert_eq!(lines[1].spans[1].style.fg, Some(crate::theme::accent()));
        let let_span = lines[2]
            .spans
            .iter()
            .find(|span| span.content.as_ref() == "let")
            .expect("let keyword is highlighted");
        assert_eq!(let_span.style.fg, Some(crate::theme::accent()));
        let number_span = lines[2]
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
        let class_span = lines[1]
            .spans
            .iter()
            .find(|span| span.content.as_ref() == "class")
            .expect("python class keyword is tokenized");
        let true_span = lines[3]
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

        let heading = lines
            .iter()
            .find(|line| line.to_string().contains("Plan"))
            .expect("heading is rendered");
        let quote = lines
            .iter()
            .find(|line| line.to_string().contains("important context"))
            .expect("quote is rendered");
        let ordered = lines
            .iter()
            .find(|line| line.to_string().contains("First step"))
            .expect("ordered list is rendered");

        assert_eq!(heading.spans[0].content, "  ");
        assert_eq!(heading.spans[2].content, "Plan");
        assert_eq!(heading.spans[2].style.fg, Some(crate::theme::primary()));
        assert_eq!(quote.spans[2].content, "> ");
        assert_eq!(quote.spans[3].style.fg, Some(crate::theme::dim()));
        assert_eq!(ordered.spans[2].content, "1.");
        assert_eq!(ordered.spans[2].style.fg, Some(crate::theme::accent()));
    }

    #[test]
    fn markdown_sections_render_with_structure_not_raw_markup() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "Intro\n\n## Strengths\n\n---\n\n**Quality:** strong\n* fast checks",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("Strengths"));
        assert!(!rendered.contains("## Strengths"));
        assert!(!rendered.contains("---"));
        assert!(rendered.contains("Quality: strong"));
        assert!(rendered.contains("* fast checks"));
        assert!(
            lines
                .iter()
                .any(|line| line.spans.iter().any(|span| span.content.contains("─")))
        );
    }

    #[test]
    fn assistant_markdown_review_output_gets_reading_structure() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "TUI streaming review\n\n**Architecture.** The Rust/Ratatui TUI is a thin renderer over a JSON event stream.\n**Where streaming events get filtered today.** There are already two layers of suppression.\n\nFindings\n\n* **You're closer than you think.** The default already filters aggressively.\n* **The filter policy is implicit.** Low-value behavior is split across two languages.\n\nMy recommendation\n\nMake verbosity an **explicit, named level** rather than a boolean.",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("TUI streaming review"));
        assert!(rendered.contains("Architecture. The Rust/Ratatui TUI"));
        assert!(rendered.contains("Findings"));
        assert!(rendered.contains("My recommendation"));
        assert!(!rendered.contains("**Architecture.**"));
        assert!(!rendered.contains("**Where streaming events get filtered today.**"));
        assert!(lines.iter().any(|line| {
            line.to_string().contains("Architecture.")
                && line
                    .spans
                    .iter()
                    .any(|span| span.style.fg == Some(crate::theme::accent()))
        }));
        assert!(
            lines
                .windows(2)
                .any(|window| window[0].to_string().trim().is_empty()
                    && window[1].to_string().contains("Architecture."))
        );
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

        assert_eq!(lines[0].spans[0].content, "  ");
        assert_eq!(lines[0].spans[1].to_string(), "* ");
        assert_eq!(lines[0].spans[1].style.bg, None);
        assert_eq!(lines[1].spans[0].style.bg, None);
    }

    #[test]
    fn fenced_diff_blocks_use_background_tints() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "```diff\n-old\n+new\n context\n```",
        )];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(
            lines[1].spans[0].style.bg,
            Some(crate::theme::red_surface())
        );
        assert_eq!(
            lines[2].spans[0].style.bg,
            Some(crate::theme::sage_surface())
        );
        assert_eq!(lines[3].spans[0].style.bg, None);
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

        assert_eq!(lines.len(), 2);
        assert_eq!(lines[1].spans[0].content, "  · ");
    }

    #[test]
    fn user_model_and_craik_body_lanes_are_distinct() {
        let entries = vec![
            TranscriptEntry::user("You", "review this"),
            TranscriptEntry::assistant("Assistant", "Looks good."),
            TranscriptEntry::system("Gateway", "Receipt: receipt_1"),
        ];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines.len(), 9);
        assert!(lines[0].spans.is_empty());
        assert_eq!(lines[1].spans[0].content.chars().count(), 72);
        assert_eq!(lines[1].spans[0].style.bg, Some(crate::theme::surface()));
        assert!(lines[2].to_string().contains("review this"));
        assert!(lines[2].to_string().starts_with("  review this"));
        assert_eq!(
            lines[2]
                .spans
                .iter()
                .find(|span| span.content.contains("review this"))
                .expect("prompt text is styled")
                .style
                .bg,
            Some(crate::theme::surface())
        );
        assert!(
            !lines[2]
                .spans
                .iter()
                .find(|span| span.content.contains("review this"))
                .expect("prompt text is styled")
                .style
                .add_modifier
                .contains(Modifier::BOLD)
        );
        assert_eq!(lines[5].spans[0].content, "  ");
        assert_eq!(lines[5].spans[1].content, "Looks good.");
        assert_eq!(lines[8].spans[0].content, "  · ");
    }

    #[test]
    fn transcript_lane_styles_keep_model_primary_and_craik_subdued() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "Model response"),
            TranscriptEntry::new(TranscriptKind::Receipt, "Receipt", "ID: receipt_1"),
            TranscriptEntry::new(TranscriptKind::Approval, "Approval", "Target: src/lib.rs"),
        ];

        let lines = render_transcript_lines(&entries, &TranscriptRenderOptions::expanded());

        assert_eq!(lines[0].spans[0].content, "  ");
        assert_eq!(lines[0].spans[1].content, "Model response");
        assert_eq!(lines[0].spans[1].style.fg, Some(crate::theme::primary()));
        assert_eq!(lines[2].spans[1].content, "evidence ");
        assert_eq!(lines[2].spans[1].style.fg, Some(crate::theme::mute()));
        assert_eq!(lines[3].spans[0].content, "  ⌁ ");
        assert_eq!(lines[4].spans[1].content, "approval ");
        assert_eq!(lines[5].spans[0].content, "  ! ");
        assert_eq!(lines[5].spans[0].style.fg, Some(crate::theme::red()));
    }

    #[test]
    fn evidence_rows_are_denser_than_conversation_rows() {
        let conversation = vec![TranscriptEntry::assistant("Assistant", "Model response")];
        let evidence = vec![TranscriptEntry::new(
            TranscriptKind::Tool,
            "Read",
            "Target: README.md",
        )];

        let conversation_lines =
            render_transcript_lines(&conversation, &TranscriptRenderOptions::expanded());
        let evidence_lines =
            render_transcript_lines(&evidence, &TranscriptRenderOptions::expanded());

        assert_eq!(conversation_lines.len(), 2);
        assert_eq!(evidence_lines.len(), 2);
        assert_eq!(evidence_lines[0].spans[1].content, "tool ");
        assert_eq!(
            evidence_lines[0].spans[1].style.fg,
            Some(crate::theme::mute())
        );
        assert!(
            !evidence_lines[0].spans[1]
                .style
                .add_modifier
                .contains(Modifier::BOLD)
        );
        assert_eq!(evidence_lines[1].spans[0].content, "  · ");
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
                content_width: None,
            },
        );
        let rendered = lines
            .into_iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("Target: src/lib.rs"));
        assert!(!rendered.contains("... 2 detail lines hidden"));
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
