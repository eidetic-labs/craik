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
        .map(|entry| entry.body.lines().count().max(1) as u16 + 1)
        .sum::<u16>();
    line_count
        .saturating_sub(visible_height)
        .saturating_sub(transcript_scroll)
}

pub fn render_transcript_lines(entries: &[TranscriptEntry]) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    for entry in entries {
        let (label, color) = transcript_style(&entry.kind);
        lines.push(Line::from(vec![
            Span::styled(
                format!("{label} "),
                Style::default().fg(color).add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                entry.title.clone(),
                Style::default().add_modifier(Modifier::BOLD),
            ),
        ]));
        for body_line in entry.body.lines() {
            lines.push(Line::from(Span::raw(format!("  {body_line}"))));
        }
    }
    lines
}

fn transcript_style(kind: &TranscriptKind) -> (&'static str, Color) {
    match kind {
        TranscriptKind::System => ("system", Color::Cyan),
        TranscriptKind::User => ("user", Color::Green),
        TranscriptKind::Assistant => ("assistant", Color::White),
        TranscriptKind::Progress => ("run", Color::Yellow),
        TranscriptKind::Tool => ("tool", Color::Magenta),
        TranscriptKind::File => ("file", Color::Blue),
        TranscriptKind::Command => ("cmd", Color::LightMagenta),
        TranscriptKind::Approval => ("approval", Color::Red),
        TranscriptKind::Receipt => ("receipt", Color::LightCyan),
        TranscriptKind::Error => ("error", Color::LightRed),
    }
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

        assert!(rendered.contains("user You"));
        assert!(rendered.contains("tool Read"));
        assert!(rendered.contains("error Gateway"));
    }

    #[test]
    fn scroll_offset_accounts_for_multiline_entries() {
        let entries = vec![
            TranscriptEntry::assistant("Assistant", "one\ntwo\nthree"),
            TranscriptEntry::progress("Run", "done"),
        ];

        assert_eq!(transcript_scroll_offset(&entries, 0, 2), 4);
        assert_eq!(transcript_scroll_offset(&entries, 2, 2), 2);
    }
}
