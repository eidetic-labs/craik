use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

pub struct TranscriptEntry {
    pub kind: TranscriptKind,
    pub title: String,
    pub body: String,
}

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

pub fn transcript_scroll_offset(
    entries: &[TranscriptEntry],
    transcript_scroll: u16,
    visible_height: u16,
) -> u16 {
    let line_count = entries
        .iter()
        .map(|entry| entry.body.lines().count().max(1) as u16 + 2)
        .sum::<u16>();
    line_count
        .saturating_sub(visible_height)
        .saturating_sub(transcript_scroll)
}

pub fn render_transcript_lines(entries: &[TranscriptEntry]) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    for entry in entries {
        let (label, color) = transcript_label_style(&entry.kind);
        lines.push(Line::from(vec![
            Span::styled(
                format!("[{label}] "),
                Style::default()
                    .fg(color)
                    .add_modifier(Modifier::BOLD)
                    .add_modifier(Modifier::REVERSED),
            ),
            Span::styled(
                entry.title.clone(),
                Style::default().add_modifier(Modifier::BOLD),
            ),
        ]));
        let mut body_lines = entry.body.lines().peekable();
        if body_lines.peek().is_none() {
            lines.push(render_body_line(&entry.kind, ""));
        } else {
            for body_line in body_lines {
                lines.push(render_body_line(&entry.kind, body_line));
            }
        }
        lines.push(Line::default());
    }
    lines
}

fn transcript_label_style(kind: &TranscriptKind) -> (&'static str, Color) {
    match kind {
        TranscriptKind::System => ("SYSTEM", Color::Cyan),
        TranscriptKind::User => ("USER", Color::Green),
        TranscriptKind::Assistant => ("ASSIST", Color::White),
        TranscriptKind::Progress => ("RUN", Color::Yellow),
        TranscriptKind::Tool => ("TOOL", Color::Magenta),
        TranscriptKind::File => ("FILE", Color::Blue),
        TranscriptKind::Command => ("CMD", Color::LightMagenta),
        TranscriptKind::Approval => ("APPROVE", Color::Red),
        TranscriptKind::Receipt => ("RECEIPT", Color::LightCyan),
        TranscriptKind::Error => ("ERROR", Color::LightRed),
    }
}

fn render_body_line(kind: &TranscriptKind, text: &str) -> Line<'static> {
    let mut spans = vec![Span::styled("  ", Style::default().fg(Color::DarkGray))];
    match kind {
        TranscriptKind::Command => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(Color::LightMagenta),
        )),
        TranscriptKind::File => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(Color::LightBlue),
        )),
        TranscriptKind::Approval => spans.push(Span::styled(
            text.to_owned(),
            Style::default()
                .fg(Color::LightRed)
                .add_modifier(Modifier::BOLD),
        )),
        TranscriptKind::Receipt => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(Color::LightCyan),
        )),
        TranscriptKind::Error => spans.push(Span::styled(
            text.to_owned(),
            Style::default().fg(Color::LightRed),
        )),
        _ => spans.extend(highlight_inline_code(text)),
    }
    Line::from(spans)
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
                    .fg(Color::LightYellow)
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

#[cfg(test)]
mod tests {
    use super::{
        TranscriptEntry, TranscriptKind, render_transcript_lines, transcript_scroll_offset,
    };

    #[test]
    fn rendering_labels_entry_kinds() {
        let entries = vec![
            TranscriptEntry::user("You", "hello"),
            TranscriptEntry::new(TranscriptKind::Tool, "Read", "README.md"),
            TranscriptEntry::error("Gateway", "failed"),
        ];

        let rendered = render_transcript_lines(&entries)
            .into_iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("[USER] You"));
        assert!(rendered.contains("[TOOL] Read"));
        assert!(rendered.contains("[ERROR] Gateway"));
    }

    #[test]
    fn scroll_offset_accounts_for_multiline_entries() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "one\ntwo\nthree"),
            TranscriptEntry::progress("Run", "done"),
        ];

        assert_eq!(transcript_scroll_offset(&entries, 0, 2), 6);
        assert_eq!(transcript_scroll_offset(&entries, 2, 2), 4);
    }

    #[test]
    fn assistant_body_highlights_inline_code() {
        let entries = vec![TranscriptEntry::assistant(
            "Assistant",
            "Run `cargo test` before merging.",
        )];

        let lines = render_transcript_lines(&entries);
        let body = &lines[1];

        assert_eq!(body.spans[1].content, "Run ");
        assert_eq!(body.spans[2].content, "cargo test");
        assert_eq!(
            body.spans[2].style.fg,
            Some(ratatui::style::Color::LightYellow)
        );
    }

    #[test]
    fn command_body_uses_command_style() {
        let entries = vec![TranscriptEntry::new(
            TranscriptKind::Command,
            "Bash",
            "uv run pytest",
        )];

        let lines = render_transcript_lines(&entries);

        assert_eq!(lines[1].spans[1].content, "uv run pytest");
        assert_eq!(
            lines[1].spans[1].style.fg,
            Some(ratatui::style::Color::LightMagenta)
        );
    }

    #[test]
    fn empty_body_still_renders_body_row() {
        let entries = vec![TranscriptEntry::system("Gateway", "")];

        let lines = render_transcript_lines(&entries);

        assert_eq!(lines.len(), 3);
        assert_eq!(lines[1].spans[0].content, "  ");
    }
}
