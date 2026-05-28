use craik_tui_rs::GatewayAppState;
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

pub struct ActivityMetrics<'a> {
    pub slash_commands: usize,
    pub queued_inputs: usize,
    pub last_error: Option<&'a str>,
}

pub fn render_activity_panel(state: &GatewayAppState, metrics: ActivityMetrics<'_>) -> String {
    let model = model_label(state, "not selected");
    let mut lines = vec![
        format!(
            "Session: {}",
            if state.ready { "ready" } else { "starting" }
        ),
        format!(
            "Readiness: {}",
            state.readiness_state.as_deref().unwrap_or("unknown")
        ),
        format!("Model: {model}"),
        format!("Backend: {}", state.backend.as_deref().unwrap_or("auto")),
        format!("Run: {}", state.run_status.as_deref().unwrap_or("idle")),
        format!(
            "Phase: {}",
            state.working_phase.as_deref().unwrap_or("none")
        ),
        format!("Receipts: {}", state.receipt_ids.len()),
        format!("Tools: {}", state.tool_events.len()),
        format!("Files: {}", state.file_paths.len()),
        format!("Commands: {}", state.commands.len()),
        format!("Approvals: {}", state.approval_requests.len()),
        format!("Slash commands: {}", metrics.slash_commands),
        format!("Queued: {}", metrics.queued_inputs),
        "Ctrl-A approves latest · Ctrl-X denies latest".to_owned(),
    ];
    if let Some(error) = metrics.last_error {
        lines.push(format!("Last error: {error}"));
    }
    lines.join("\n")
}

pub fn status_line(state: &GatewayAppState, in_flight: bool) -> Line<'static> {
    let request_state = if in_flight { "working" } else { "ready" };
    let model = compact_label(model_label(state, "model not selected"), 42);
    Line::from(vec![
        Span::styled(
            "Craik",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" | ", Style::default().fg(Color::DarkGray)),
        Span::styled(model, Style::default().fg(Color::White)),
        Span::styled(" | ", Style::default().fg(Color::DarkGray)),
        Span::styled(
            request_state,
            Style::default()
                .fg(if in_flight {
                    Color::Yellow
                } else {
                    Color::Green
                })
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" | ", Style::default().fg(Color::DarkGray)),
        Span::styled("Enter", Style::default().fg(Color::LightGreen)),
        Span::raw(" send"),
        Span::styled("  Alt-Enter", Style::default().fg(Color::LightBlue)),
        Span::raw(" newline"),
        Span::styled("  PgUp/PgDn", Style::default().fg(Color::LightBlue)),
        Span::raw(" scroll"),
        Span::styled(
            if in_flight {
                "  Ctrl-C stop"
            } else {
                "  Ctrl-C exit"
            },
            Style::default().fg(Color::LightRed),
        ),
    ])
}

fn compact_label(value: &str, max_chars: usize) -> String {
    let char_count = value.chars().count();
    if char_count <= max_chars {
        return value.to_owned();
    }
    let keep = max_chars.saturating_sub(3);
    format!("{}...", value.chars().take(keep).collect::<String>())
}

fn model_label<'a>(state: &'a GatewayAppState, fallback: &'a str) -> &'a str {
    state
        .active_model_display_name
        .as_deref()
        .or(state.active_model.as_deref())
        .unwrap_or(fallback)
}

#[cfg(test)]
mod tests {
    use super::{ActivityMetrics, render_activity_panel, status_line};
    use craik_tui_rs::GatewayAppState;

    #[test]
    fn activity_panel_prefers_display_model_and_shows_counts() {
        let state = GatewayAppState {
            ready: true,
            active_model: Some("anthropic/claude-opus-4-7".to_owned()),
            active_model_display_name: Some("Anthropic Claude Opus 4.7".to_owned()),
            receipt_ids: vec!["receipt_1".to_owned()],
            file_paths: vec!["src/main.rs".to_owned()],
            commands: vec!["cargo test".to_owned()],
            ..GatewayAppState::default()
        };

        let rendered = render_activity_panel(
            &state,
            ActivityMetrics {
                slash_commands: 12,
                queued_inputs: 2,
                last_error: Some("gateway disconnected"),
            },
        );

        assert!(rendered.contains("Session: ready"));
        assert!(rendered.contains("Model: Anthropic Claude Opus 4.7"));
        assert!(rendered.contains("Receipts: 1"));
        assert!(rendered.contains("Files: 1"));
        assert!(rendered.contains("Commands: 1"));
        assert!(rendered.contains("Slash commands: 12"));
        assert!(rendered.contains("Queued: 2"));
        assert!(rendered.contains("Last error: gateway disconnected"));
    }

    #[test]
    fn status_line_uses_raw_model_when_display_name_missing() {
        let state = GatewayAppState {
            active_model: Some("anthropic/claude-sonnet".to_owned()),
            ..GatewayAppState::default()
        };

        let rendered = status_line(&state, true).to_string();

        assert!(rendered.contains("anthropic/claude-sonnet"));
        assert!(rendered.contains("working"));
    }

    #[test]
    fn status_line_compacts_long_model_names() {
        let state = GatewayAppState {
            active_model_display_name: Some(
                "Anthropic Claude Opus 4.7 Extended Thinking Preview".to_owned(),
            ),
            ..GatewayAppState::default()
        };

        let rendered = status_line(&state, false).to_string();

        assert!(rendered.contains("Anthropic Claude Opus 4.7 Extended Thin..."));
        assert!(!rendered.contains("Thinking Preview"));
    }
}
