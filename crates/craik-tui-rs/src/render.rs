use craik_tui_rs::GatewayAppState;
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

use crate::model_names::readable_model_label;
use crate::theme;

#[cfg(test)]
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

pub struct StatusLineMetrics<'a> {
    pub in_flight: bool,
    pub pending_approval: Option<&'a str>,
    pub approval_reviewed: bool,
    pub backend_connected: bool,
    pub queued_inputs: usize,
    pub active_overlay: Option<&'a str>,
    pub search_active: bool,
    pub details_collapsed: bool,
}

struct FooterHint {
    key: &'static str,
    label: String,
    urgent: bool,
}

#[cfg(test)]
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
        lines.push("  Actions: a approve / d deny / Esc defer".to_owned());
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

#[cfg(test)]
fn provider_health_label(provider_id: Option<&str>, backend: Option<&str>) -> &'static str {
    match (provider_id, backend) {
        (Some(_), Some(_)) => "ready",
        (Some(_), None) => "provider selected",
        (None, Some(_)) => "backend selected",
        (None, None) => "waiting for provider",
    }
}

pub fn status_line(state: &GatewayAppState, metrics: StatusLineMetrics<'_>) -> Line<'static> {
    let request_state = footer_state_label(
        state,
        metrics.in_flight,
        metrics.pending_approval.is_some(),
        metrics.backend_connected,
        metrics.queued_inputs,
        metrics.active_overlay.is_some(),
    );
    let model = compact_model_label(&model_label(state, "model not selected"));
    let mode =
        display_permission_mode(state.active_permission_mode.as_deref().unwrap_or("default"));
    let mut spans = vec![
        Span::styled(format!(" {mode} "), mode_pill_style(mode)),
        Span::raw(" "),
        Span::styled(model, theme::primary_style()),
    ];
    if let Some(effort) = effort_label(state) {
        spans.push(Span::styled(" · ", theme::mute_style()));
        spans.push(Span::styled(effort.to_owned(), effort_style(effort)));
    }
    spans.extend([
        Span::styled(" · ", theme::mute_style()),
        Span::styled(status_glyph(request_state), status_style(request_state)),
        Span::raw(" "),
        Span::styled(request_state, status_style(request_state)),
    ]);
    for hint in footer_hints(state, &metrics) {
        spans.push(Span::raw("   "));
        let key_style = if hint.urgent {
            Style::default()
                .fg(theme::amber())
                .add_modifier(Modifier::BOLD)
        } else {
            theme::accent_style()
        };
        let label_style = if hint.urgent {
            Style::default().fg(theme::amber())
        } else {
            theme::dim_style()
        };
        spans.push(Span::styled(hint.key, key_style));
        spans.push(Span::styled(format!(" {}", hint.label), label_style));
    }
    Line::from(spans)
}

fn footer_hints(state: &GatewayAppState, metrics: &StatusLineMetrics<'_>) -> Vec<FooterHint> {
    let mut hints = vec![FooterHint {
        key: "/",
        label: "commands".to_owned(),
        urgent: false,
    }];
    let mut middle = Vec::new();
    if let Some(overlay) = metrics.active_overlay {
        middle.push(FooterHint {
            key: "esc",
            label: "chat".to_owned(),
            urgent: false,
        });
        if overlay == "Approvals" {
            if metrics.pending_approval.is_some() {
                // Single-press keymap: `a` approves, `d` denies. A high-risk
                // approval that has been armed shows "confirm approve" so the
                // operator knows the next `a` commits the destructive action.
                middle.push(FooterHint {
                    key: "a",
                    label: if metrics.approval_reviewed {
                        "confirm approve".to_owned()
                    } else {
                        "approve".to_owned()
                    },
                    urgent: true,
                });
                middle.push(FooterHint {
                    key: "d",
                    label: "deny".to_owned(),
                    urgent: metrics.approval_reviewed,
                });
            } else {
                middle.push(FooterHint {
                    key: "a",
                    label: "none pending".to_owned(),
                    urgent: false,
                });
            }
        } else {
            middle.push(FooterHint {
                key: match overlay {
                    "Memory" => "⌃e",
                    "Evidence" => "⌃r",
                    "Runs" => "⌃e",
                    _ => "⌃m",
                },
                label: match overlay {
                    "Memory" => "evidence",
                    "Evidence" => "runs",
                    "Runs" => "evidence",
                    _ => "memory",
                }
                .to_owned(),
                urgent: false,
            });
        }
    } else if !metrics.backend_connected {
        middle.push(FooterHint {
            key: "⌃b",
            label: "reconnect".to_owned(),
            urgent: true,
        });
        middle.push(FooterHint {
            key: "⌃m",
            label: "memory".to_owned(),
            urgent: false,
        });
    } else if let Some(approval_id) = metrics.pending_approval {
        middle.push(FooterHint {
            key: "⌃a",
            label: format!("review {}", compact_label(approval_id, 14)),
            urgent: true,
        });
        middle.push(FooterHint {
            key: "⌃e",
            label: "evidence".to_owned(),
            urgent: false,
        });
    } else if metrics.queued_inputs > 0 {
        middle.push(FooterHint {
            key: "⌃b",
            label: format!("queued {}", metrics.queued_inputs),
            urgent: false,
        });
        middle.push(FooterHint {
            key: "⌃r",
            label: "runs".to_owned(),
            urgent: false,
        });
    } else {
        if !state.receipt_ids.is_empty() {
            middle.push(FooterHint {
                key: "⌃e",
                label: "evidence".to_owned(),
                urgent: false,
            });
        }
        if !state.run_ids.is_empty() {
            middle.push(FooterHint {
                key: "⌃r",
                label: "runs".to_owned(),
                urgent: false,
            });
        }
        middle.push(FooterHint {
            key: "⌃m",
            label: "memory".to_owned(),
            urgent: false,
        });
    }
    let middle_limit = if metrics.active_overlay == Some("Approvals") {
        3
    } else {
        2
    };
    for hint in middle.into_iter().take(middle_limit) {
        if !hints.iter().any(|existing| existing.key == hint.key) {
            hints.push(hint);
        }
    }
    for fallback in [
        FooterHint {
            key: "⌃r",
            label: "runs".to_owned(),
            urgent: false,
        },
        FooterHint {
            key: "⌃m",
            label: "memory".to_owned(),
            urgent: false,
        },
    ] {
        if hints.len() >= 3 {
            break;
        }
        if !hints.iter().any(|existing| existing.key == fallback.key) {
            hints.push(fallback);
        }
    }
    hints.push(FooterHint {
        key: "?",
        label: if metrics.search_active {
            "search active"
        } else if metrics.details_collapsed {
            "details collapsed"
        } else {
            "help"
        }
        .to_owned(),
        urgent: false,
    });
    hints
}

fn compact_label(value: &str, max_chars: usize) -> String {
    let char_count = value.chars().count();
    if char_count <= max_chars {
        return value.to_owned();
    }
    let keep = max_chars.saturating_sub(3);
    format!("{}...", value.chars().take(keep).collect::<String>())
}

fn compact_model_label(value: &str) -> String {
    let value = value
        .strip_prefix("Anthropic Claude ")
        .or_else(|| value.strip_prefix("anthropic/"))
        .or_else(|| value.strip_prefix("OpenAI "))
        .or_else(|| value.strip_prefix("openai/"))
        .unwrap_or(value);
    compact_label(value, 28)
}

fn effort_label(state: &GatewayAppState) -> Option<&str> {
    if let Some(effort) = state
        .active_reasoning_effort
        .as_deref()
        .filter(|effort| !effort.trim().is_empty())
    {
        return Some(effort);
    }
    let is_claude = state.active_provider_family.as_deref() == Some("anthropic")
        || state
            .active_model
            .as_deref()
            .is_some_and(|model| model.contains("claude") || model.starts_with("anthropic/"));
    is_claude.then_some("default")
}

fn display_permission_mode(mode: &str) -> &str {
    if mode == "default" { "ask" } else { mode }
}

fn model_label(state: &GatewayAppState, fallback: &str) -> String {
    if state.active_model.is_none() && state.active_model_display_name.is_none() {
        return fallback.to_owned();
    }
    readable_model_label(
        state.active_provider_family.as_deref(),
        state.active_model.as_deref(),
        state.active_model_display_name.as_deref(),
    )
}

#[cfg(test)]
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
    backend_connected: bool,
    queued_inputs: usize,
    has_active_overlay: bool,
) -> &'static str {
    if !backend_connected {
        "disconnected"
    } else if has_active_overlay {
        "overlay"
    } else if has_pending_approval {
        "waiting for approval"
    } else if queued_inputs > 0 {
        "queued"
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
        "disconnected" => theme::red(),
        "overlay" => theme::accent(),
        "waiting for approval" => theme::amber(),
        "thinking" | "working" => theme::amber(),
        "completed" | "ready" => theme::sage(),
        _ => theme::primary(),
    }
}

fn status_glyph(state: &str) -> &'static str {
    match state {
        "disconnected" => "×",
        "thinking" | "working" => "◐",
        _ => "●",
    }
}

fn status_style(state: &str) -> Style {
    Style::default()
        .fg(status_color(state))
        .add_modifier(Modifier::BOLD)
}

fn mode_pill_style(mode: &str) -> Style {
    let fg = if mode == "plan" {
        theme::amber()
    } else {
        theme::accent()
    };
    Style::default()
        .fg(fg)
        .bg(theme::surface())
        .add_modifier(Modifier::BOLD)
}

fn effort_style(effort: &str) -> Style {
    let color = match effort {
        "max" => theme::cyan(),
        "high" => theme::amber(),
        "low" => theme::dim(),
        _ => theme::mute(),
    };
    Style::default().fg(color)
}

#[cfg(test)]
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
    use super::{ActivityMetrics, StatusLineMetrics, render_activity_panel, status_line};
    use craik_tui_rs::GatewayAppState;

    fn status_metrics() -> StatusLineMetrics<'static> {
        StatusLineMetrics {
            in_flight: false,
            pending_approval: None,
            approval_reviewed: false,
            backend_connected: true,
            queued_inputs: 0,
            active_overlay: None,
            search_active: false,
            details_collapsed: false,
        }
    }

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
    fn status_line_humanizes_model_when_display_name_missing() {
        let state = GatewayAppState {
            active_model: Some("anthropic/claude-sonnet".to_owned()),
            ..GatewayAppState::default()
        };

        let rendered = status_line(
            &state,
            StatusLineMetrics {
                in_flight: true,
                ..status_metrics()
            },
        )
        .to_string();

        assert!(rendered.contains("Claude Sonnet"));
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
            status_line(
                &thinking,
                StatusLineMetrics {
                    in_flight: true,
                    ..status_metrics()
                },
            )
            .to_string()
            .contains("thinking")
        );
        assert!(
            status_line(
                &approval,
                StatusLineMetrics {
                    in_flight: true,
                    pending_approval: Some("approval_123"),
                    ..status_metrics()
                },
            )
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

        let rendered = status_line(&state, status_metrics()).to_string();

        assert!(rendered.contains("Opus 4.7 Extended"));
        assert!(!rendered.contains("Thinking Preview"));
    }

    #[test]
    fn status_line_uses_only_source_backed_reasoning_effort() {
        let inferred_only = GatewayAppState {
            active_model_display_name: Some("Anthropic Claude Opus 4.7 High".to_owned()),
            ..GatewayAppState::default()
        };
        let source_backed = GatewayAppState {
            active_model_display_name: Some("Anthropic Claude Opus 4.7".to_owned()),
            active_reasoning_effort: Some("high".to_owned()),
            ..GatewayAppState::default()
        };

        let inferred_rendered = status_line(&inferred_only, status_metrics()).to_string();
        let source_rendered = status_line(&source_backed, status_metrics()).to_string();

        assert!(!inferred_rendered.contains("effort:"));
        assert!(source_rendered.contains("high"));
    }

    #[test]
    fn status_line_exposes_default_effort_for_claude_models() {
        let state = GatewayAppState {
            active_provider_family: Some("anthropic".to_owned()),
            active_model: Some("anthropic/claude-opus-4-7".to_owned()),
            ..GatewayAppState::default()
        };

        let rendered = status_line(&state, status_metrics()).to_string();

        assert!(!rendered.contains("effort:"));
        assert!(rendered.contains("default"));
    }

    #[test]
    fn status_line_uses_source_backed_permission_mode() {
        let state = GatewayAppState {
            active_permission_mode: Some("auto".to_owned()),
            ..GatewayAppState::default()
        };

        let rendered = status_line(&state, status_metrics()).to_string();

        assert!(rendered.contains(" auto "));
        assert!(!rendered.contains(" ask "));
    }

    #[test]
    fn status_line_displays_default_permission_mode_as_ask() {
        let state = GatewayAppState {
            active_permission_mode: Some("default".to_owned()),
            ..GatewayAppState::default()
        };

        let rendered = status_line(&state, status_metrics()).to_string();

        assert!(rendered.contains(" ask "));
        assert!(!rendered.contains(" default "));
    }

    #[test]
    fn status_line_prioritizes_pending_approval_actions() {
        let state = GatewayAppState::default();

        let rendered = status_line(
            &state,
            StatusLineMetrics {
                in_flight: true,
                pending_approval: Some("approval_run_edit_123456789"),
                ..status_metrics()
            },
        )
        .to_string();

        assert!(rendered.contains("review"));
        assert!(rendered.contains("approval_ru"));
        assert!(rendered.contains("⌃a"));
        assert!(rendered.contains("? help"));
    }

    #[test]
    fn status_line_distinguishes_approval_review_from_decision() {
        let state = GatewayAppState::default();

        // Disarmed (low-risk, or high-risk not yet armed): single-press a/d.
        let unarmed = status_line(
            &state,
            StatusLineMetrics {
                active_overlay: Some("Approvals"),
                pending_approval: Some("approval_123"),
                approval_reviewed: false,
                ..status_metrics()
            },
        )
        .to_string();
        assert!(unarmed.contains("a approve"));
        assert!(unarmed.contains("d deny"));

        // Armed (a high-risk approval awaiting its explicit confirm press).
        let armed = status_line(
            &state,
            StatusLineMetrics {
                active_overlay: Some("Approvals"),
                pending_approval: Some("approval_123"),
                approval_reviewed: true,
                ..status_metrics()
            },
        )
        .to_string();
        assert!(armed.contains("a confirm approve"));
        assert!(armed.contains("d deny"));
    }

    #[test]
    fn status_line_surfaces_disconnected_reconnect_action() {
        let state = GatewayAppState::default();

        let rendered = status_line(
            &state,
            StatusLineMetrics {
                backend_connected: false,
                queued_inputs: 1,
                ..status_metrics()
            },
        )
        .to_string();

        assert!(rendered.contains("disconnected"));
        assert!(rendered.contains("⌃b"));
        assert!(rendered.contains("reconnect"));
    }

    #[test]
    fn status_line_shows_transcript_modes() {
        let state = GatewayAppState::default();

        let rendered = status_line(
            &state,
            StatusLineMetrics {
                search_active: true,
                details_collapsed: true,
                ..status_metrics()
            },
        )
        .to_string();

        assert!(rendered.contains("search active"));
        assert!(rendered.contains("⌃r runs"));
        assert!(rendered.contains("?"));
    }

    #[test]
    fn status_line_surfaces_active_overlay() {
        let state = GatewayAppState::default();

        let rendered = status_line(
            &state,
            StatusLineMetrics {
                active_overlay: Some("Evidence"),
                ..status_metrics()
            },
        )
        .to_string();

        assert!(rendered.contains("overlay"));
        assert!(rendered.contains("esc chat"));
        assert!(rendered.contains("⌃r runs"));
    }
}
