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
    pub selected_run_summary: Option<&'a str>,
    pub selected_run_detail: Option<&'a str>,
    pub backend_connected: bool,
}

pub fn render_activity_panel(state: &GatewayAppState, metrics: ActivityMetrics<'_>) -> String {
    let model = model_label(state, "not selected");
    let run_state = run_state_label(
        state,
        metrics.pending_approvals,
        metrics.queued_inputs,
        metrics.last_error,
    );
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
        "Evidence".to_owned(),
        format!("  Receipts: {}", state.receipt_ids.len()),
        format!("  Tools: {}", state.tool_events.len()),
        format!("  Files: {}", state.file_paths.len()),
        format!("  Commands: {}", state.commands.len()),
        format!("  Approvals seen: {}", state.approval_requests.len()),
        format!("  Slash commands: {}", metrics.slash_commands),
        "Gateway health".to_owned(),
        format!(
            "  Backend link: {}",
            if metrics.backend_connected {
                "connected"
            } else {
                "disconnected; Ctrl-B reconnect"
            }
        ),
        format!(
            "  Provider auth: {}",
            provider_health_label(
                state.active_provider_id.as_deref(),
                state.backend.as_deref()
            )
        ),
        format!(
            "  Model routing: {}",
            if state.active_model.is_some() || state.active_model_display_name.is_some() {
                "ready"
            } else {
                "model not selected"
            }
        ),
        "Run".to_owned(),
        format!("  State: {run_state}"),
        format!(
            "  Status: {}",
            state.run_status.as_deref().unwrap_or("idle")
        ),
        format!(
            "  Phase: {}",
            state.working_phase.as_deref().unwrap_or("none")
        ),
        format!("  Queued: {}", metrics.queued_inputs),
    ];
    if let Some(receipt_id) = state.receipt_ids.last() {
        lines.push(format!("  Latest receipt: {receipt_id}"));
    }
    if !state.run_ids.is_empty() {
        lines.push("Recent runs".to_owned());
        for run_id in state.run_ids.iter().rev().take(3) {
            lines.push(format!("  {run_id}"));
        }
        if let Some(summary) = metrics.selected_run_summary {
            lines.push(format!("  Selected: {summary}"));
        }
        if let Some(detail) = metrics.selected_run_detail {
            lines.push("  Selected detail".to_owned());
            lines.extend(detail.lines().take(5).map(|line| format!("    {line}")));
        }
        lines.push("  Navigate: Ctrl-J next / Ctrl-K previous".to_owned());
    }
    if metrics.pending_approvals > 0 {
        lines.extend([
            "Approval review".to_owned(),
            format!("  Queue: {} pending", metrics.pending_approvals),
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
            lines.push("  Context".to_owned());
            lines.extend(preview.lines().map(|line| format!("    {line}")));
        }
        lines.push("  Actions: Ctrl-A approve / Ctrl-X deny after review".to_owned());
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

pub fn render_provenance_panel(detail: &str) -> String {
    let mut lines = Vec::new();
    let mut section = "";
    for raw in detail.lines() {
        if raw.ends_with(':') && !raw.starts_with("- ") {
            section = raw.trim_end_matches(':');
            lines.push(raw.to_owned());
            continue;
        }
        if raw.starts_with("- ") {
            lines.push(format!("  {raw}"));
            continue;
        }
        if let Some((label, value)) = raw.split_once(':') {
            lines.push(format!("  {label}:{}", compact_panel_value(value)));
        } else if raw.trim().is_empty() {
            lines.push(String::new());
        } else if section.is_empty() {
            lines.push(raw.to_owned());
        } else {
            lines.push(format!("  {raw}"));
        }
    }
    if lines.is_empty() {
        lines.push("No provenance selected.".to_owned());
    }
    lines.join("\n")
}

fn provider_health_label(provider_id: Option<&str>, backend: Option<&str>) -> &'static str {
    match (provider_id, backend) {
        (Some(_), Some(_)) => "ready",
        (Some(_), None) => "provider selected",
        (None, Some(_)) => "backend selected",
        (None, None) => "waiting for provider",
    }
}

pub fn status_line(
    state: &GatewayAppState,
    in_flight: bool,
    pending_approval: Option<&str>,
    transcript_focused: bool,
    search_active: bool,
    details_collapsed: bool,
) -> Line<'static> {
    let request_state = footer_state_label(state, in_flight, pending_approval.is_some());
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
                .fg(status_color(request_state))
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
        Span::styled("  ?", Style::default().fg(Color::LightBlue)),
        Span::raw(" help"),
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
        Span::styled("  Ctrl-J/K", Style::default().fg(Color::LightBlue)),
        Span::raw(" runs"),
        Span::styled("  Ctrl-L", Style::default().fg(Color::LightBlue)),
        Span::raw(" filter"),
        Span::styled("  Ctrl-Y", Style::default().fg(Color::LightBlue)),
        Span::raw(" retry"),
        Span::styled("  Ctrl-B", Style::default().fg(Color::LightBlue)),
        Span::raw(" reconnect"),
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

fn compact_panel_value(value: &str) -> String {
    let trimmed = value.trim_start();
    if trimmed.is_empty() {
        String::new()
    } else {
        format!(" {trimmed}")
    }
}

fn model_label<'a>(state: &'a GatewayAppState, fallback: &'a str) -> &'a str {
    state
        .active_model_display_name
        .as_deref()
        .or(state.active_model.as_deref())
        .unwrap_or(fallback)
}

fn run_state_label(
    state: &GatewayAppState,
    pending_approvals: usize,
    queued_inputs: usize,
    last_error: Option<&str>,
) -> &'static str {
    if last_error.is_some() {
        return "error";
    }
    if pending_approvals > 0 {
        return "waiting for approval";
    }
    if queued_inputs > 0 {
        return "queued";
    }
    if matches!(state.working_phase.as_deref(), Some("thinking")) {
        return "thinking";
    }
    match state.run_status.as_deref() {
        Some("running") => "working",
        Some("completed") => "completed",
        Some("interrupt requested") => "interrupt requested",
        Some("failed") | Some("error") => "error",
        Some(_) => "working",
        None => "idle",
    }
}

fn footer_state_label(
    state: &GatewayAppState,
    in_flight: bool,
    has_pending_approval: bool,
) -> &'static str {
    if has_pending_approval {
        "waiting for approval"
    } else if matches!(state.working_phase.as_deref(), Some("thinking")) {
        "thinking"
    } else if in_flight || matches!(state.run_status.as_deref(), Some("running")) {
        "working"
    } else if matches!(state.run_status.as_deref(), Some("completed")) {
        "completed"
    } else {
        "ready"
    }
}

fn status_color(state: &str) -> Color {
    match state {
        "waiting for approval" => Color::LightRed,
        "thinking" => Color::LightYellow,
        "working" => Color::Yellow,
        "completed" | "ready" => Color::Green,
        _ => Color::White,
    }
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
            run_ids: vec![
                "run_1".to_owned(),
                "run_2".to_owned(),
                "run_3".to_owned(),
                "run_4".to_owned(),
            ],
            ..GatewayAppState::default()
        };

        let rendered = render_activity_panel(
            &state,
            ActivityMetrics {
                slash_commands: 12,
                queued_inputs: 2,
                last_error: None,
                pending_approvals: 1,
                latest_pending_approval: Some("approval_123"),
                selected_approval_summary: Some("1/1 pending - approval_123 -> src/lib.rs"),
                selected_approval_preview: Some("ID: approval_123\nTool: Edit\nTarget: src/lib.rs"),
                selected_run_summary: Some("4/4 run_4 [completed]"),
                selected_run_detail: Some(
                    "Run: run_4\nStatus: completed\nTools: 2 latest Bash\nReceipts: 1 latest receipt_1",
                ),
                backend_connected: true,
            },
        );

        assert!(rendered.contains("Session"));
        assert!(rendered.contains("  State: ready"));
        assert!(rendered.contains("  State: waiting for approval"));
        assert!(rendered.contains("  Model: Anthropic Claude Opus 4.7"));
        assert!(rendered.contains("  Provider: anthropic (provider_anthropic)"));
        assert!(rendered.contains("Recent runs"));
        assert!(rendered.contains("  run_4"));
        assert!(rendered.contains("  Selected: 4/4 run_4 [completed]"));
        assert!(rendered.contains("  Navigate: Ctrl-J next / Ctrl-K previous"));
        assert!(rendered.contains("  Latest receipt: receipt_1"));
        assert!(rendered.contains("Gateway health"));
        assert!(rendered.contains("  Backend link: connected"));
        assert!(rendered.contains("  Provider auth: provider selected"));
        assert!(rendered.contains("Evidence"));
        assert!(rendered.contains("  Receipts: 1"));
        assert!(rendered.contains("  Files: 1"));
        assert!(rendered.contains("  Commands: 1"));
        assert!(rendered.contains("  Slash commands: 12"));
        assert!(rendered.contains("  Queued: 2"));
        assert!(rendered.contains("Approval review"));
        assert!(rendered.contains("  Queue: 1 pending"));
        assert!(rendered.contains("  Selected: 1/1 pending - approval_123 -> src/lib.rs"));
        assert!(rendered.contains("  Context"));
        assert!(rendered.contains("    Tool: Edit"));
        assert!(rendered.contains("    Target: src/lib.rs"));
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
    fn status_line_surfaces_thinking_and_approval_states() {
        let thinking = GatewayAppState {
            working_phase: Some("thinking".to_owned()),
            ..GatewayAppState::default()
        };
        let approval = GatewayAppState {
            run_status: Some("running".to_owned()),
            ..GatewayAppState::default()
        };

        assert!(
            status_line(&thinking, true, None, false, false, false)
                .to_string()
                .contains("thinking")
        );
        assert!(
            status_line(&approval, true, Some("approval_123"), false, false, false)
                .to_string()
                .contains("waiting for approval")
        );
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
