use craik_tui_rs::GatewayAppState;
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

pub struct ActivityMetrics<'a> {
    pub slash_commands: usize,
    pub queued_inputs: usize,
    pub last_error: Option<&'a str>,
    pub pending_approvals: usize,
    pub latest_pending_approval: Option<&'a str>,
    pub selected_approval_summary: Option<&'a str>,
    pub selected_approval_preview: Option<&'a str>,
}

pub fn render_activity_panel(state: &GatewayAppState, metrics: ActivityMetrics<'_>) -> String {
    let model = model_label(state, "not selected");
    let mut lines = vec![
        "Session".to_owned(),
        format!(
            "  State: {}",
            if state.ready { "ready" } else { "starting" }
        ),
        format!(
            "  Readiness: {}",
            state.readiness_state.as_deref().unwrap_or("unknown")
        ),
        format!("  Model: {model}"),
        format!(
            "  Provider: {}",
            provider_label(
                state.active_provider_id.as_deref(),
                state.active_provider_family.as_deref()
            )
        ),
        format!("  Backend: {}", state.backend.as_deref().unwrap_or("auto")),
        "Run".to_owned(),
        format!(
            "  Status: {}",
            state.run_status.as_deref().unwrap_or("idle")
        ),
        format!(
            "  Phase: {}",
            state.working_phase.as_deref().unwrap_or("none")
        ),
        format!("  Queued: {}", metrics.queued_inputs),
        "Evidence".to_owned(),
        format!("  Receipts: {}", state.receipt_ids.len()),
        format!("  Tools: {}", state.tool_events.len()),
        format!("  Files: {}", state.file_paths.len()),
        format!("  Commands: {}", state.commands.len()),
        format!("  Approvals seen: {}", state.approval_requests.len()),
        format!("  Slash commands: {}", metrics.slash_commands),
    ];
    if metrics.pending_approvals > 0 {
        lines.extend([
            "Approvals pending".to_owned(),
            format!("  Pending: {}", metrics.pending_approvals),
        ]);
        if let Some(summary) = metrics.selected_approval_summary {
            lines.push(format!("  Selected: {summary}"));
        } else {
            lines.push(format!(
                "  Selected: {}",
                metrics
                    .latest_pending_approval
                    .unwrap_or("approval id unavailable")
            ));
        }
        if let Some(preview) = metrics.selected_approval_preview {
            lines.push("  Preview".to_owned());
            lines.extend(preview.lines().map(|line| format!("    {line}")));
        }
        lines.push("  Actions: Ctrl-A approve / Ctrl-X deny".to_owned());
        if metrics.pending_approvals > 1 {
            lines.push("  Select: Ctrl-N next / Ctrl-P previous".to_owned());
        }
    } else {
        lines.push("Approvals: none pending".to_owned());
    }
    if let Some(error) = metrics.last_error {
        lines.push(format!("Last error: {error}"));
    }
    lines.join("\n")
}

pub fn status_line(
    state: &GatewayAppState,
    in_flight: bool,
    pending_approval: Option<&str>,
    transcript_focused: bool,
    search_active: bool,
    details_collapsed: bool,
) -> Line<'static> {
    let request_state = if in_flight { "working" } else { "ready" };
    let model = compact_label(model_label(state, "model not selected"), 42);
    let approval_label = pending_approval.map(|approval_id| compact_label(approval_id, 24));
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
        Span::styled("  Ctrl-F", Style::default().fg(Color::LightBlue)),
        Span::raw(if search_active {
            " search active"
        } else {
            " search"
        }),
        Span::styled("  Ctrl-R", Style::default().fg(Color::LightBlue)),
        Span::raw(if transcript_focused {
            " split"
        } else {
            " focus"
        }),
        Span::styled("  Ctrl-E", Style::default().fg(Color::LightBlue)),
        Span::raw(if details_collapsed {
            " expand"
        } else {
            " collapse"
        }),
        if pending_approval.is_some() {
            Span::raw("")
        } else {
            Span::styled("  Alt-Enter", Style::default().fg(Color::LightBlue))
        },
        if pending_approval.is_some() {
            Span::raw("")
        } else {
            Span::raw(" newline")
        },
        if let Some(approval_id) = approval_label {
            Span::styled(
                format!("  Approval {approval_id}"),
                Style::default()
                    .fg(Color::LightRed)
                    .add_modifier(Modifier::BOLD),
            )
        } else {
            Span::styled("  PgUp/PgDn", Style::default().fg(Color::LightBlue))
        },
        if pending_approval.is_some() {
            Span::styled(
                "  Ctrl-A approve  Ctrl-X deny  Ctrl-N/P select",
                Style::default()
                    .fg(Color::LightRed)
                    .add_modifier(Modifier::BOLD),
            )
        } else {
            Span::raw(" scroll")
        },
        Span::styled(
            if pending_approval.is_some() {
                "  Esc keeps editing"
            } else if in_flight {
                "  Ctrl-C stop"
            } else {
                "  Ctrl-C exit"
            },
            Style::default().fg(if pending_approval.is_some() {
                Color::DarkGray
            } else {
                Color::LightRed
            }),
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

fn provider_label(provider_id: Option<&str>, provider_family: Option<&str>) -> String {
    match (provider_id, provider_family) {
        (Some(id), Some(family)) if id != family => format!("{family} ({id})"),
        (Some(id), _) => id.to_owned(),
        (_, Some(family)) => family.to_owned(),
        _ => "not selected".to_owned(),
    }
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
            active_provider_id: Some("provider_anthropic".to_owned()),
            active_provider_family: Some("anthropic".to_owned()),
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
                pending_approvals: 1,
                latest_pending_approval: Some("approval_123"),
                selected_approval_summary: Some("1/1 approval_123 -> src/lib.rs"),
                selected_approval_preview: Some("ID: approval_123\nTool: Edit\nTarget: src/lib.rs"),
            },
        );

        assert!(rendered.contains("Session"));
        assert!(rendered.contains("  State: ready"));
        assert!(rendered.contains("  Model: Anthropic Claude Opus 4.7"));
        assert!(rendered.contains("  Provider: anthropic (provider_anthropic)"));
        assert!(rendered.contains("Evidence"));
        assert!(rendered.contains("  Receipts: 1"));
        assert!(rendered.contains("  Files: 1"));
        assert!(rendered.contains("  Commands: 1"));
        assert!(rendered.contains("  Slash commands: 12"));
        assert!(rendered.contains("  Queued: 2"));
        assert!(rendered.contains("Approvals pending"));
        assert!(rendered.contains("  Selected: 1/1 approval_123 -> src/lib.rs"));
        assert!(rendered.contains("    Tool: Edit"));
        assert!(rendered.contains("    Target: src/lib.rs"));
        assert!(rendered.contains("Last error: gateway disconnected"));
    }

    #[test]
    fn status_line_uses_raw_model_when_display_name_missing() {
        let state = GatewayAppState {
            active_model: Some("anthropic/claude-sonnet".to_owned()),
            ..GatewayAppState::default()
        };

        let rendered = status_line(&state, true, None, false, false, false).to_string();

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

        let rendered = status_line(&state, false, None, false, false, false).to_string();

        assert!(rendered.contains("Anthropic Claude Opus 4.7 Extended Thin..."));
        assert!(!rendered.contains("Thinking Preview"));
    }

    #[test]
    fn status_line_prioritizes_pending_approval_actions() {
        let state = GatewayAppState::default();

        let rendered = status_line(
            &state,
            true,
            Some("approval_run_edit_123456789"),
            false,
            false,
            false,
        )
        .to_string();

        assert!(rendered.contains("Approval approval_run_edit_123..."));
        assert!(rendered.contains("Ctrl-A approve"));
        assert!(rendered.contains("Ctrl-X deny"));
    }

    #[test]
    fn status_line_shows_transcript_modes() {
        let state = GatewayAppState::default();

        let rendered = status_line(&state, false, None, true, true, true).to_string();

        assert!(rendered.contains("Ctrl-F search active"));
        assert!(rendered.contains("Ctrl-R split"));
        assert!(rendered.contains("Ctrl-E expand"));
    }
}
