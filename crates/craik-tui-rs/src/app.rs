use crate::{
    backend::{BackendSession, WorkerMessage},
    gateway_events::{is_request_terminal_event, slash_hints_from_event, summarize_slash_output},
    input::{SlashHint, slash_completion},
    transcript::{TranscriptEntry, TranscriptKind},
};
use craik_tui_rs::{GatewayAppState, GatewayCommand, GatewayEvent, format_gateway_error_event};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use std::{collections::VecDeque, env, fs, path::PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum LoopAction {
    Continue,
    Exit,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RunFilter {
    All,
    Active,
    NeedsApproval,
    Failed,
    Completed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ActiveOverlay {
    Memory,
    Evidence,
    Runs,
    Approvals,
}

impl ActiveOverlay {
    pub(crate) fn title(self) -> &'static str {
        match self {
            Self::Memory => "Memory",
            Self::Evidence => "Evidence",
            Self::Runs => "Runs",
            Self::Approvals => "Approvals",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum TranscriptJump {
    Tool,
    Approval,
    Receipt,
    Error,
}

impl TranscriptJump {
    pub(crate) fn label(self) -> &'static str {
        match self {
            Self::Tool => "tool",
            Self::Approval => "approval",
            Self::Receipt => "receipt",
            Self::Error => "error",
        }
    }

    fn matches(self, kind: TranscriptKind) -> bool {
        match self {
            Self::Tool => matches!(
                kind,
                TranscriptKind::Tool | TranscriptKind::Command | TranscriptKind::File
            ),
            Self::Approval => kind == TranscriptKind::Approval,
            Self::Receipt => kind == TranscriptKind::Receipt,
            Self::Error => kind == TranscriptKind::Error,
        }
    }
}

impl RunFilter {
    pub(crate) fn label(self) -> &'static str {
        match self {
            Self::All => "all",
            Self::Active => "active",
            Self::NeedsApproval => "approval",
            Self::Failed => "failed",
            Self::Completed => "completed",
        }
    }

    fn next(self) -> Self {
        match self {
            Self::All => Self::Active,
            Self::Active => Self::NeedsApproval,
            Self::NeedsApproval => Self::Failed,
            Self::Failed => Self::Completed,
            Self::Completed => Self::All,
        }
    }

    fn matches(self, run: &RunRecord) -> bool {
        match self {
            Self::All => true,
            Self::Active => run.is_active(),
            Self::NeedsApproval => !run.approvals.is_empty() && !run.is_completed(),
            Self::Failed => run.is_failed(),
            Self::Completed => run.is_completed(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct PendingApproval {
    id: String,
    message: String,
    tool: Option<String>,
    target: Option<String>,
    reason: Option<String>,
    risk: Option<String>,
    command: Option<String>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct RunRecord {
    pub(crate) run_id: String,
    pub(crate) task_id: Option<String>,
    pub(crate) prompt: Option<String>,
    pub(crate) model: Option<String>,
    pub(crate) provider: Option<String>,
    pub(crate) status: Option<String>,
    pub(crate) receipts: Vec<String>,
    pub(crate) receipt_details: Vec<String>,
    pub(crate) tools: Vec<String>,
    pub(crate) files: Vec<String>,
    pub(crate) commands: Vec<String>,
    pub(crate) approvals: Vec<String>,
    pub(crate) outputs: Vec<String>,
    pub(crate) provenance: Vec<String>,
}

pub(crate) struct InteractiveApp {
    pub(crate) state: GatewayAppState,
    pub(crate) input: String,
    pub(crate) input_cursor: usize,
    pub(crate) transcript: Vec<TranscriptEntry>,
    pub(crate) transcript_scroll: u16,
    pub(crate) transcript_focused: bool,
    pub(crate) expand_transcript_details: bool,
    pub(crate) help_visible: bool,
    pub(crate) active_overlay: Option<ActiveOverlay>,
    pub(crate) search_active: bool,
    pub(crate) search_query: String,
    pub(crate) search_match_index: Option<usize>,
    pub(crate) transcript_jump: Option<TranscriptJump>,
    backend: BackendSession,
    pub(crate) in_flight: bool,
    pub(crate) last_error: Option<String>,
    pub(crate) backend_connected: bool,
    pending_approvals: Vec<PendingApproval>,
    selected_approval_index: Option<usize>,
    pub(crate) slash_catalog: Vec<SlashHint>,
    history: Vec<String>,
    history_index: Option<usize>,
    pub(crate) queued_inputs: VecDeque<String>,
    pub(crate) run_records: Vec<RunRecord>,
    pub(crate) selected_run_index: Option<usize>,
    pub(crate) run_filter: RunFilter,
    auto_select_latest_run: bool,
    last_submitted_text: Option<String>,
    last_prompt_preview: Option<String>,
}

impl InteractiveApp {
    pub(crate) fn new() -> anyhow::Result<Self> {
        let backend = BackendSession::start()?;
        let mut app = Self {
            state: GatewayAppState::default(),
            input: String::new(),
            input_cursor: 0,
            transcript: vec![
                TranscriptEntry::system("Craik Ratatui client", "Gateway session connected."),
                TranscriptEntry::system(
                    "Input",
                    "Type a prompt or slash command. Alt-Enter inserts a newline. Ctrl-C exits.",
                ),
            ],
            transcript_scroll: 0,
            transcript_focused: false,
            expand_transcript_details: true,
            help_visible: false,
            active_overlay: None,
            search_active: false,
            search_query: String::new(),
            search_match_index: None,
            transcript_jump: None,
            backend,
            in_flight: false,
            last_error: None,
            backend_connected: true,
            pending_approvals: Vec::new(),
            selected_approval_index: None,
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
            run_records: Vec::new(),
            selected_run_index: None,
            run_filter: RunFilter::All,
            auto_select_latest_run: true,
            last_submitted_text: None,
            last_prompt_preview: None,
        };
        app.send_commands([
            GatewayCommand::SessionStatus,
            GatewayCommand::SessionHistory,
            GatewayCommand::SlashCatalog,
        ]);
        Ok(app)
    }

    #[cfg(test)]
    pub(crate) fn for_test_with_messages(
        messages: impl IntoIterator<Item = WorkerMessage>,
    ) -> Self {
        let (sender, receiver) = std::sync::mpsc::channel();
        for message in messages {
            sender.send(message).expect("test worker message sends");
        }
        drop(sender);
        Self::for_test_with_receiver(receiver)
    }

    #[cfg(test)]
    fn for_test_with_receiver(receiver: std::sync::mpsc::Receiver<WorkerMessage>) -> Self {
        Self {
            state: GatewayAppState::default(),
            input: String::new(),
            input_cursor: 0,
            transcript: Vec::new(),
            transcript_scroll: 0,
            transcript_focused: false,
            expand_transcript_details: true,
            help_visible: false,
            active_overlay: None,
            search_active: false,
            search_query: String::new(),
            search_match_index: None,
            transcript_jump: None,
            backend: BackendSession::for_test(receiver),
            in_flight: false,
            last_error: None,
            backend_connected: true,
            pending_approvals: Vec::new(),
            selected_approval_index: None,
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
            run_records: Vec::new(),
            selected_run_index: None,
            run_filter: RunFilter::All,
            auto_select_latest_run: true,
            last_submitted_text: None,
            last_prompt_preview: None,
        }
    }

    pub(crate) fn submit_input(&mut self) {
        let text = self.input.trim().to_owned();
        if text.is_empty() {
            return;
        }
        if matches!(text.as_str(), "/stop" | "/interrupt") {
            self.clear_input();
            self.request_interrupt();
            return;
        }
        self.transcript.push(TranscriptEntry::user("You", &text));
        self.history.push(text.clone());
        self.history_index = None;
        self.last_submitted_text = Some(text.clone());
        self.auto_select_latest_run = true;
        if self.in_flight {
            self.queued_inputs.push_back(text);
            self.transcript.push(TranscriptEntry::progress(
                "Queued",
                "Input will run after the active request completes.",
            ));
            self.clear_input();
            return;
        }
        self.dispatch_text(text);
        self.clear_input();
        self.transcript_scroll = 0;
    }

    fn dispatch_text(&mut self, text: String) {
        if !self.backend_connected {
            self.queued_inputs.push_back(text);
            self.in_flight = false;
            self.state.working_phase = None;
            self.transcript.push(TranscriptEntry::progress(
                "Queued until reconnect",
                "Gateway is disconnected. Press Ctrl-B to reconnect; the queued prompt will run after the backend responds.",
            ));
            return;
        }
        let command = if text.starts_with('/') {
            GatewayCommand::SlashSubmit { text }
        } else {
            GatewayCommand::PromptSubmit { text }
        };
        self.send_commands([command]);
    }

    fn send_commands<const N: usize>(&mut self, commands: [GatewayCommand; N]) {
        self.in_flight = true;
        self.state.working_phase = Some("waiting".to_owned());
        for command in commands {
            if let Err(error) = self.backend.send(&command) {
                self.last_error = Some(error.to_string());
                self.transcript.push(TranscriptEntry::error(
                    "Gateway send failed",
                    &error.to_string(),
                ));
                self.in_flight = false;
                break;
            }
        }
    }

    pub(crate) fn shutdown(&mut self) {
        match self.backend.close() {
            Ok(()) => {
                self.backend_connected = false;
                self.in_flight = false;
                self.state.working_phase = None;
                self.transcript.push(TranscriptEntry::system(
                    "Session closing",
                    "Gateway session close requested.",
                ));
            }
            Err(error) => {
                self.last_error = Some(error.to_string());
                self.transcript.push(TranscriptEntry::error(
                    "Session close failed",
                    &error.to_string(),
                ));
            }
        }
    }

    pub(crate) fn drain_worker(&mut self) {
        while let Ok(message) = self.backend.receiver.try_recv() {
            match message {
                WorkerMessage::Event(event) => {
                    self.backend_connected = true;
                    let terminal_event = is_request_terminal_event(&event);
                    self.record_event(&event);
                    self.state.apply_event(&event);
                    if terminal_event {
                        self.in_flight = false;
                        if self.state.working_phase.as_deref() == Some("waiting") {
                            self.state.working_phase = None;
                        }
                        self.dispatch_next_queued();
                    }
                }
                WorkerMessage::Error(error) => {
                    self.last_error = Some(error.clone());
                    self.transcript
                        .push(TranscriptEntry::error("Gateway error", &error));
                    self.in_flight = false;
                    if self.state.working_phase.as_deref() == Some("waiting") {
                        self.state.working_phase = None;
                    }
                }
                WorkerMessage::Closed(message) => {
                    self.last_error = Some(message.clone());
                    self.transcript
                        .push(TranscriptEntry::error("Gateway disconnected", &message));
                    self.transcript.push(TranscriptEntry::system(
                        "Reconnect",
                        "Press Ctrl-B to restart the Gateway backend.",
                    ));
                    self.in_flight = false;
                    self.backend_connected = false;
                    self.state.working_phase = None;
                }
            }
        }
    }

    pub(crate) fn pending_approval_count(&self) -> usize {
        self.pending_approvals.len()
    }

    pub(crate) fn latest_pending_approval(&self) -> Option<&str> {
        self.selected_pending_approval()
            .map(|approval| approval.id.as_str())
    }

    pub(crate) fn selected_approval_summary(&self) -> Option<String> {
        let approval = self.selected_pending_approval()?;
        let position = self.selected_approval_index.unwrap_or_default() + 1;
        let total = self.pending_approvals.len();
        let subject = approval
            .target
            .as_deref()
            .or(approval.command.as_deref())
            .or(approval.tool.as_deref())
            .unwrap_or("target unavailable");
        Some(format!(
            "{position}/{total} pending - {} -> {subject}",
            approval.id
        ))
    }

    pub(crate) fn selected_approval_preview(&self) -> Option<String> {
        self.selected_pending_approval().map(|approval| {
            approval.preview_text(self.state.receipt_ids.last().map(String::as_str))
        })
    }

    pub(crate) fn selected_run_summary(&self) -> Option<String> {
        let run = self.selected_run()?;
        let visible = self.filtered_run_indexes();
        let position = visible
            .iter()
            .position(|index| Some(*index) == self.selected_run_index)
            .map(|index| index + 1)
            .unwrap_or_default();
        let total = visible.len();
        let status = run.status.as_deref().unwrap_or("active");
        Some(format!(
            "{position}/{total} {} [{status}] filter={}",
            run.run_id,
            self.run_filter.label()
        ))
    }

    pub(crate) fn selected_run_detail(&self) -> Option<String> {
        self.selected_run().map(RunRecord::detail_text)
    }

    pub(crate) fn selected_run_provenance(&self) -> String {
        if let Some(run) = self.selected_run() {
            return run.detail_text();
        }
        if self.run_records.is_empty() {
            "No runs or receipts loaded yet.\nSubmit a prompt or wait for session history."
                .to_owned()
        } else {
            format!(
                "No run matches the `{}` filter.\nPress Ctrl-L to cycle filters.",
                self.run_filter.label()
            )
        }
    }

    pub(crate) fn overlay_title(&self) -> Option<String> {
        let overlay = self.active_overlay?;
        Some(format!("{}  Esc returns to chat", overlay.title()))
    }

    pub(crate) fn overlay_text(&self) -> Option<String> {
        let overlay = self.active_overlay?;
        Some(match overlay {
            ActiveOverlay::Memory => self.memory_overlay_text(),
            ActiveOverlay::Evidence => self.evidence_overlay_text(),
            ActiveOverlay::Runs => self.runs_overlay_text(),
            ActiveOverlay::Approvals => self.approvals_overlay_text(),
        })
    }

    fn memory_overlay_text(&self) -> String {
        let mut lines = vec![
            "Session memory context".to_owned(),
            format!(
                "  Provider: {}",
                self.state
                    .active_provider_family
                    .as_deref()
                    .or(self.state.active_provider_id.as_deref())
                    .unwrap_or("not selected")
            ),
            format!(
                "  Model: {}",
                self.state
                    .active_model_display_name
                    .as_deref()
                    .or(self.state.active_model.as_deref())
                    .unwrap_or("not selected")
            ),
            format!("  Receipts available: {}", self.state.receipt_ids.len()),
            format!("  Runs available: {}", self.run_records.len()),
        ];
        if let Some(prompt) = self.last_prompt_preview.as_deref() {
            lines.push(format!("  Last prompt: {prompt}"));
        }
        lines.extend([
            String::new(),
            "Navigation".to_owned(),
            "  Ctrl-E evidence  Ctrl-R runs  Ctrl-A approvals  Esc chat".to_owned(),
        ]);
        lines.join("\n")
    }

    fn evidence_overlay_text(&self) -> String {
        let mut lines = vec![
            "Evidence".to_owned(),
            format!("  Receipts: {}", self.state.receipt_ids.len()),
            format!("  Tools: {}", self.state.tool_events.len()),
            format!("  Files: {}", self.state.file_paths.len()),
            format!("  Commands: {}", self.state.commands.len()),
            format!("  Approvals seen: {}", self.state.approval_requests.len()),
        ];
        append_recent(&mut lines, "Recent receipts", &self.state.receipt_ids);
        append_recent(&mut lines, "Recent files", &self.state.file_paths);
        append_recent(&mut lines, "Recent commands", &self.state.commands);
        lines.extend([
            String::new(),
            "Navigation".to_owned(),
            "  Ctrl-R runs  Ctrl-M memory  Ctrl-A approvals  Esc chat".to_owned(),
        ]);
        lines.join("\n")
    }

    fn runs_overlay_text(&self) -> String {
        let mut lines = vec![
            "Runs".to_owned(),
            format!("  Filter: {}", self.run_filter.label()),
            format!("  Total: {}", self.run_records.len()),
            format!("  Visible: {}", self.filtered_run_indexes().len()),
            "  Controls: Ctrl-J/K select  Ctrl-L filter  Ctrl-O export".to_owned(),
            String::new(),
        ];
        if let Some(summary) = self.selected_run_summary() {
            lines.push(format!("Selected: {summary}"));
        }
        lines.push(self.selected_run_provenance());
        lines.join("\n")
    }

    fn approvals_overlay_text(&self) -> String {
        let mut lines = vec![
            "Approval review".to_owned(),
            format!("  Pending: {}", self.pending_approvals.len()),
            "  Controls: Ctrl-N/P select  Ctrl-A approve  Ctrl-X deny".to_owned(),
            String::new(),
        ];
        if let Some(summary) = self.selected_approval_summary() {
            lines.push(format!("Selected: {summary}"));
        }
        if let Some(preview) = self.selected_approval_preview() {
            lines.push(preview);
        } else {
            lines.push("No pending approvals.".to_owned());
        }
        lines.join("\n")
    }

    pub(crate) fn prompt_context(&self) -> String {
        let mut lines = Vec::new();
        if !self.backend_connected {
            lines.push("Gateway disconnected. Press Ctrl-B to reconnect.".to_owned());
            if !self.queued_inputs.is_empty() {
                lines.push(format!(
                    "Queued for reconnect: {} prompt(s).",
                    self.queued_inputs.len()
                ));
            } else if self.last_submitted_text.is_some() {
                lines.push("Retry after reconnect: Ctrl-Y resubmits the last prompt.".to_owned());
            }
        }
        if self
            .state
            .readiness_state
            .as_deref()
            .is_some_and(|state| state != "ready")
        {
            lines.push(format!(
                "Readiness: {}",
                self.state.readiness_state.as_deref().unwrap_or("unknown")
            ));
        }
        if self.state.active_model.is_none() && self.state.active_model_display_name.is_none() {
            lines.push("Model: not selected".to_owned());
        }
        if self.state.active_provider_id.is_none() && self.state.active_provider_family.is_none() {
            lines.push("Provider: not selected".to_owned());
        }
        if self.in_flight {
            lines.push("Run: working; Ctrl-C requests stop.".to_owned());
        } else if self.last_submitted_text.is_some() {
            lines.push("Retry: Ctrl-Y resubmits the last prompt.".to_owned());
        }
        lines.join("\n")
    }

    fn selected_run(&self) -> Option<&RunRecord> {
        let index = self.selected_run_index?;
        self.run_records.get(index)
    }

    fn selected_pending_approval(&self) -> Option<&PendingApproval> {
        let index = self.selected_approval_index?;
        self.pending_approvals.get(index)
    }

    pub(crate) fn handle_key(&mut self, key: KeyEvent) -> LoopAction {
        if self.help_visible {
            return self.handle_help_key(key);
        }
        if self.search_active {
            return self.handle_search_key(key);
        }
        if self.active_overlay.is_some() {
            return self.handle_overlay_key(key);
        }
        match key.code {
            KeyCode::Char('?') => {
                self.help_visible = true;
                LoopAction::Continue
            }
            KeyCode::Char('/') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.help_visible = true;
                LoopAction::Continue
            }
            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                if self.in_flight {
                    self.request_interrupt();
                    LoopAction::Continue
                } else {
                    LoopAction::Exit
                }
            }
            KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => LoopAction::Exit,
            KeyCode::Char('b') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.restart_backend();
                LoopAction::Continue
            }
            KeyCode::Char('y') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.retry_last_prompt();
                LoopAction::Continue
            }
            KeyCode::Char('o') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.export_selected_run();
                LoopAction::Continue
            }
            KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.cycle_run_filter();
                LoopAction::Continue
            }
            KeyCode::Char('a') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Approvals);
                LoopAction::Continue
            }
            KeyCode::Char('x') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Approvals);
                LoopAction::Continue
            }
            KeyCode::Char('n') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_next_approval();
                LoopAction::Continue
            }
            KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_previous_approval();
                LoopAction::Continue
            }
            KeyCode::Char('f') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.search_active = true;
                LoopAction::Continue
            }
            KeyCode::Char('t') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_next_transcript_kind(TranscriptJump::Tool);
                LoopAction::Continue
            }
            KeyCode::Char('T') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_previous_transcript_kind(TranscriptJump::Tool);
                LoopAction::Continue
            }
            KeyCode::Char('g') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_next_transcript_kind(TranscriptJump::Approval);
                LoopAction::Continue
            }
            KeyCode::Char('G') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_previous_transcript_kind(TranscriptJump::Approval);
                LoopAction::Continue
            }
            KeyCode::Char('h') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_next_transcript_kind(TranscriptJump::Receipt);
                LoopAction::Continue
            }
            KeyCode::Char('H') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_previous_transcript_kind(TranscriptJump::Receipt);
                LoopAction::Continue
            }
            KeyCode::Char('z') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_next_transcript_kind(TranscriptJump::Error);
                LoopAction::Continue
            }
            KeyCode::Char('Z') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.jump_to_previous_transcript_kind(TranscriptJump::Error);
                LoopAction::Continue
            }
            KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Runs);
                LoopAction::Continue
            }
            KeyCode::Char('e') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Evidence);
                LoopAction::Continue
            }
            KeyCode::Char('m') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Memory);
                LoopAction::Continue
            }
            KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.delete_to_line_start();
                LoopAction::Continue
            }
            KeyCode::Char('k')
                if key.modifiers.contains(KeyModifiers::CONTROL) && !self.input.is_empty() =>
            {
                self.delete_to_line_end();
                LoopAction::Continue
            }
            KeyCode::Char('w') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.delete_previous_word();
                LoopAction::Continue
            }
            KeyCode::Char('j') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_next_run();
                LoopAction::Continue
            }
            KeyCode::Char('k') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_previous_run();
                LoopAction::Continue
            }
            KeyCode::Tab => {
                self.complete_slash_input();
                LoopAction::Continue
            }
            KeyCode::Enter if key.modifiers.contains(KeyModifiers::ALT) => {
                self.insert_newline();
                LoopAction::Continue
            }
            KeyCode::Enter => {
                self.submit_input();
                LoopAction::Continue
            }
            KeyCode::Backspace => {
                self.backspace();
                LoopAction::Continue
            }
            KeyCode::Delete => {
                self.delete();
                LoopAction::Continue
            }
            KeyCode::Esc => {
                self.clear_input();
                LoopAction::Continue
            }
            KeyCode::Left => {
                self.move_cursor_left();
                LoopAction::Continue
            }
            KeyCode::Right => {
                self.move_cursor_right();
                LoopAction::Continue
            }
            KeyCode::Home => {
                if key.modifiers.contains(KeyModifiers::CONTROL) {
                    self.scroll_transcript_top();
                } else {
                    self.move_cursor_home();
                }
                LoopAction::Continue
            }
            KeyCode::End => {
                if key.modifiers.contains(KeyModifiers::CONTROL) {
                    self.scroll_transcript_bottom();
                } else {
                    self.move_cursor_end();
                }
                LoopAction::Continue
            }
            KeyCode::PageUp => {
                self.scroll_transcript_up();
                LoopAction::Continue
            }
            KeyCode::PageDown => {
                self.scroll_transcript_down();
                LoopAction::Continue
            }
            KeyCode::Up => {
                if self.input_has_multiple_lines() && !self.cursor_is_on_first_line() {
                    self.move_cursor_up_line();
                } else {
                    self.history_previous();
                }
                LoopAction::Continue
            }
            KeyCode::Down => {
                if self.input_has_multiple_lines() && !self.cursor_is_on_last_line() {
                    self.move_cursor_down_line();
                } else {
                    self.history_next();
                }
                LoopAction::Continue
            }
            KeyCode::Char(ch) if !key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.insert_char(ch);
                LoopAction::Continue
            }
            _ => LoopAction::Continue,
        }
    }

    fn handle_overlay_key(&mut self, key: KeyEvent) -> LoopAction {
        match key.code {
            KeyCode::Esc => {
                self.active_overlay = None;
            }
            KeyCode::Char('m') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Memory);
            }
            KeyCode::Char('e') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Evidence);
            }
            KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.active_overlay = Some(ActiveOverlay::Runs);
            }
            KeyCode::Char('a') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                if self.active_overlay == Some(ActiveOverlay::Approvals) {
                    self.approve_selected();
                } else {
                    self.active_overlay = Some(ActiveOverlay::Approvals);
                }
            }
            KeyCode::Char('x')
                if key.modifiers.contains(KeyModifiers::CONTROL)
                    && self.active_overlay == Some(ActiveOverlay::Approvals) =>
            {
                self.deny_selected();
            }
            KeyCode::Char('n')
                if key.modifiers.contains(KeyModifiers::CONTROL)
                    && self.active_overlay == Some(ActiveOverlay::Approvals) =>
            {
                self.select_next_approval();
            }
            KeyCode::Char('p')
                if key.modifiers.contains(KeyModifiers::CONTROL)
                    && self.active_overlay == Some(ActiveOverlay::Approvals) =>
            {
                self.select_previous_approval();
            }
            KeyCode::Char('j') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_next_run();
            }
            KeyCode::Char('k') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_previous_run();
            }
            KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.cycle_run_filter();
            }
            KeyCode::Char('o') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.export_selected_run();
            }
            KeyCode::PageUp => {
                self.scroll_transcript_up();
            }
            KeyCode::PageDown => {
                self.scroll_transcript_down();
            }
            _ => {}
        }
        LoopAction::Continue
    }

    fn handle_help_key(&mut self, key: KeyEvent) -> LoopAction {
        match key.code {
            KeyCode::Esc | KeyCode::Enter | KeyCode::Char('?') => {
                self.help_visible = false;
            }
            _ => {}
        }
        LoopAction::Continue
    }

    pub(crate) fn help_text(&self) -> String {
        let mut lines = vec![
            "Craik Rust TUI Commands".to_owned(),
            "Prompt".to_owned(),
            "  Enter send prompt or slash command".to_owned(),
            "  Alt-Enter insert newline".to_owned(),
            "  Ctrl-Y retry last prompt".to_owned(),
            "  Ctrl-U delete to line start; Ctrl-K delete to line end; Ctrl-W delete word"
                .to_owned(),
            "Run and provenance".to_owned(),
            "  Ctrl-J / Ctrl-K select next or previous run".to_owned(),
            "  Ctrl-L cycle run filters: all, active, approval, failed, completed".to_owned(),
            "  Ctrl-C stop active run; Ctrl-B reconnect Gateway backend".to_owned(),
            "Overlays".to_owned(),
            "  Ctrl-M memory; Ctrl-E evidence; Ctrl-R runs; Ctrl-A approvals".to_owned(),
            "  Esc returns from an overlay to chat".to_owned(),
            "Transcript".to_owned(),
            "  Ctrl-F search; Ctrl-N / Ctrl-P navigate search results".to_owned(),
            "  Ctrl-T/G/H/Z jump to tool, approval, receipt, or error".to_owned(),
            "  Ctrl-Shift-T/G/H/Z jump backward by kind".to_owned(),
            "  PageUp / PageDown scroll transcript".to_owned(),
            "Approvals".to_owned(),
            "  Ctrl-A opens approval review; Ctrl-A approves from that overlay; Ctrl-X denies"
                .to_owned(),
            "  Ctrl-N / Ctrl-P select next or previous approval when approvals are pending"
                .to_owned(),
            "Help".to_owned(),
            "  ? or Ctrl-/ show this help; Esc closes help".to_owned(),
        ];
        if self.pending_approval_count() > 0 {
            lines.push("Current context: approval pending.".to_owned());
        } else if self.in_flight {
            lines.push("Current context: run is active.".to_owned());
        } else if !self.backend_connected {
            lines.push("Current context: Gateway disconnected.".to_owned());
        }
        lines.join("\n")
    }

    fn handle_search_key(&mut self, key: KeyEvent) -> LoopAction {
        match key.code {
            KeyCode::Esc => {
                self.search_active = false;
                self.search_match_index = None;
            }
            KeyCode::Enter => {
                self.search_active = false;
            }
            KeyCode::Backspace => {
                self.search_query.pop();
                self.search_match_index = None;
                self.next_search_match();
            }
            KeyCode::Char('f') if key.modifiers.contains(KeyModifiers::CONTROL) => {}
            KeyCode::Char('n') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.next_search_match();
            }
            KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.previous_search_match();
            }
            KeyCode::Char(ch) if !key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.search_query.push(ch);
                self.search_match_index = None;
                self.next_search_match();
            }
            _ => {}
        }
        LoopAction::Continue
    }

    pub(crate) fn record_event(&mut self, event: &GatewayEvent) {
        self.record_run_event(event);
        match event.event_type.as_str() {
            "session.ready" => {
                self.transcript.push(TranscriptEntry::system(
                    "Gateway",
                    &summarize_session_ready_event(event),
                ));
            }
            "session.status" => {
                let state = event
                    .data
                    .get("state")
                    .and_then(|value| value.as_str())
                    .unwrap_or("unknown");
                self.transcript
                    .push(TranscriptEntry::system("Readiness", state));
                if state != "ready" {
                    self.transcript.push(TranscriptEntry::system(
                        "Run blocked",
                        &blocked_run_guidance(event),
                    ));
                }
            }
            "session.history" => {
                let receipts = event
                    .data
                    .get("receipts")
                    .and_then(|value| value.as_array())
                    .map(Vec::len)
                    .unwrap_or_default();
                self.record_history_event(event);
                self.transcript.push(TranscriptEntry::system(
                    "Session history",
                    &format!("Loaded {receipts} persisted receipt records."),
                ));
            }
            "slash.catalog" => {
                self.slash_catalog = slash_hints_from_event(event);
            }
            "prompt.submitted" => {
                let preview = event
                    .data
                    .get("prompt_preview")
                    .and_then(|value| value.as_str())
                    .unwrap_or("prompt submitted");
                self.last_prompt_preview = Some(preview.to_owned());
                self.transcript
                    .push(TranscriptEntry::progress("Submitted", preview));
            }
            "model.selected" | "model.changed" => {
                self.transcript.push(TranscriptEntry::system(
                    "Model selected",
                    &summarize_model_event(event),
                ));
            }
            "run.started" => {
                let run_id = event.run_id.as_deref().unwrap_or("run");
                self.transcript.push(TranscriptEntry::progress(
                    &format!("Run {run_id} started"),
                    &summarize_run_event(event, run_id),
                ));
            }
            "run.progress" => {
                if let Some(message) = event.data.get("message").and_then(|value| value.as_str()) {
                    self.transcript
                        .push(TranscriptEntry::progress("Progress", message));
                    self.follow_tail_after_transcript_update();
                }
            }
            "tool.used" => {
                let tool = event
                    .data
                    .get("tool")
                    .and_then(|value| value.as_str())
                    .unwrap_or("tool");
                if let Some(message) = event.data.get("message").and_then(|value| value.as_str()) {
                    let kind = if tool == "Bash" {
                        TranscriptKind::Command
                    } else {
                        TranscriptKind::Tool
                    };
                    let text = summarize_tool_event(event, tool, message);
                    self.transcript
                        .push(TranscriptEntry::new(kind, tool, &text));
                    self.follow_tail_after_transcript_update();
                }
            }
            "run.working" => {
                let phase = event
                    .data
                    .get("phase")
                    .and_then(|value| value.as_str())
                    .unwrap_or("working");
                self.transcript.push(TranscriptEntry::progress(
                    "Run state",
                    &summarize_working_event(event, phase),
                ));
                self.follow_tail_after_transcript_update();
            }
            "file.changed" => {
                let target = event
                    .data
                    .get("target")
                    .and_then(|value| value.as_str())
                    .unwrap_or("file changed");
                let text = event
                    .data
                    .get("text")
                    .or_else(|| event.data.get("message"))
                    .and_then(|value| value.as_str())
                    .unwrap_or(target);
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::File,
                    target,
                    &format!("Path: {target}\nSummary: {text}"),
                ));
                self.follow_tail_after_transcript_update();
            }
            "approval.requested" => {
                let approval = PendingApproval::from_event(event);
                if !approval.id.is_empty()
                    && !self
                        .pending_approvals
                        .iter()
                        .any(|candidate| candidate.id == approval.id)
                {
                    self.pending_approvals.push(approval.clone());
                    self.selected_approval_index =
                        Some(self.pending_approvals.len().saturating_sub(1));
                }
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::Approval,
                    "Approval pending",
                    &approval.request_text(self.state.receipt_ids.last().map(String::as_str)),
                ));
                self.follow_tail_after_transcript_update();
            }
            "approval.resolved" => {
                let approval_id = event
                    .data
                    .get("approval_id")
                    .and_then(|value| value.as_str())
                    .unwrap_or("approval");
                let decision = event
                    .data
                    .get("decision")
                    .and_then(|value| value.as_str())
                    .unwrap_or("resolved");
                let operator = event
                    .data
                    .get("operator")
                    .and_then(|value| value.as_str())
                    .unwrap_or("operator unknown");
                self.pending_approvals
                    .retain(|candidate| candidate.id != approval_id);
                self.normalize_selected_approval();
                let title = if decision == "approved" {
                    "Approval approved"
                } else if decision == "denied" {
                    "Approval denied"
                } else {
                    "Approval resolved"
                };
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::Approval,
                    title,
                    &format!("ID: {approval_id}\nDecision: {decision}\nOperator: {operator}"),
                ));
                self.follow_tail_after_transcript_update();
            }
            "approval.denied" => {
                let approval_id = event
                    .data
                    .get("approval_id")
                    .and_then(|value| value.as_str())
                    .unwrap_or("approval");
                let message = event
                    .data
                    .get("message")
                    .and_then(|value| value.as_str())
                    .unwrap_or("Approval denied.");
                self.pending_approvals
                    .retain(|candidate| candidate.id != approval_id);
                self.normalize_selected_approval();
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::Approval,
                    "Approval denied",
                    &format!("ID: {approval_id}\nDecision: denied\nMessage: {message}"),
                ));
                self.follow_tail_after_transcript_update();
            }
            "receipt.created" => {
                if let Some(receipt_id) = event
                    .data
                    .get("receipt_id")
                    .and_then(|value| value.as_str())
                {
                    self.transcript.push(TranscriptEntry::new(
                        TranscriptKind::Receipt,
                        "Receipt created",
                        &summarize_receipt_event(event, receipt_id),
                    ));
                    self.follow_tail_after_transcript_update();
                }
            }
            "run.output" => {
                if let Some(summary) = event.data.get("summary").and_then(|value| value.as_str()) {
                    self.transcript
                        .push(TranscriptEntry::assistant("Assistant", summary));
                    self.follow_tail_after_transcript_update();
                }
            }
            "run.event" => {
                if let Some(text) = event
                    .data
                    .get("text")
                    .or_else(|| event.data.get("message"))
                    .and_then(|value| value.as_str())
                {
                    let kind = match event.data.get("kind").and_then(|value| value.as_str()) {
                        Some("tool_result") => TranscriptKind::Tool,
                        _ => TranscriptKind::Assistant,
                    };
                    self.transcript
                        .push(TranscriptEntry::new(kind, "Event", text));
                    self.follow_tail_after_transcript_update();
                }
            }
            "run.completed" => {
                let status = event
                    .data
                    .get("status")
                    .and_then(|value| value.as_str())
                    .unwrap_or("completed");
                self.transcript.push(TranscriptEntry::progress(
                    "Run completed",
                    &summarize_run_event(event, status),
                ));
                if status == "completed" && self.state.outputs.is_empty() {
                    self.transcript.push(TranscriptEntry::system(
                        "No model output",
                        "The Gateway reported completion before any assistant output event arrived.",
                    ));
                }
                self.follow_tail_after_transcript_update();
            }
            "slash.completed" => {
                let text = summarize_slash_output(event)
                    .unwrap_or_else(|| "Slash command completed.".to_owned());
                self.transcript
                    .push(TranscriptEntry::system("Slash command", &text));
                self.follow_tail_after_transcript_update();
            }
            "error" => {
                if let Some(message) = format_gateway_error_event(event) {
                    let title = if event.data.get("kind").and_then(|value| value.as_str())
                        == Some("contract_violation")
                    {
                        "Gateway contract violation"
                    } else {
                        "Gateway error"
                    };
                    self.transcript
                        .push(TranscriptEntry::error(title, &message));
                    self.follow_tail_after_transcript_update();
                }
            }
            _ => {}
        }
    }

    fn record_run_event(&mut self, event: &GatewayEvent) {
        let Some(run_id) = event.run_id.as_deref() else {
            return;
        };
        let index = self.ensure_run_record(run_id);
        if self.auto_select_latest_run || self.selected_run_index.is_none() {
            self.selected_run_index = Some(index);
        }
        let run = &mut self.run_records[index];
        if run.task_id.is_none() {
            run.task_id = event.task_id.clone();
        }
        if run.prompt.is_none() {
            run.prompt = self.last_prompt_preview.clone();
        }
        if run.model.is_none() {
            run.model = string_data(event, "model");
        }
        if run.provider.is_none() {
            run.provider =
                string_data(event, "provider_id").or_else(|| string_data(event, "provider_family"));
        }
        match event.event_type.as_str() {
            "run.started" => {
                run.status = Some("running".to_owned());
                push_unique_string(
                    &mut run.provenance,
                    format!(
                        "Run started: {}",
                        event.run_id.as_deref().unwrap_or(&run.run_id)
                    ),
                );
            }
            "run.working" => {
                if let Some(phase) = string_data(event, "phase") {
                    run.status = Some(phase.clone());
                    push_unique_string(&mut run.provenance, format!("Phase: {phase}"));
                }
                collect_event_provenance(event, run);
            }
            "run.completed" => {
                run.status = string_data(event, "status").or_else(|| Some("completed".to_owned()));
                if let Some(status) = &run.status {
                    push_unique_string(&mut run.provenance, format!("Run completed: {status}"));
                }
            }
            "tool.used" => {
                if let Some(tool) = string_data(event, "tool") {
                    push_unique_string(&mut run.tools, tool);
                }
                if let Some(command) = string_data(event, "command") {
                    push_unique_string(&mut run.commands, command);
                }
                if let Some(target) = string_data(event, "target") {
                    push_unique_string(&mut run.files, target);
                }
                collect_event_provenance(event, run);
            }
            "file.changed" => {
                if let Some(target) = string_data(event, "target") {
                    push_unique_string(&mut run.files, target);
                }
                collect_event_provenance(event, run);
            }
            "approval.requested" => {
                if let Some(message) = string_data(event, "message") {
                    push_unique_string(&mut run.approvals, message);
                }
                collect_event_provenance(event, run);
            }
            "approval.resolved" | "approval.denied" => {
                collect_event_provenance(event, run);
            }
            "receipt.created" => {
                if let Some(receipt_id) = string_data(event, "receipt_id") {
                    push_unique_string(&mut run.receipts, receipt_id);
                }
                collect_event_provenance(event, run);
            }
            "run.output" => {
                if let Some(summary) = string_data(event, "summary") {
                    run.outputs.push(summary);
                }
                collect_event_provenance(event, run);
            }
            "run.event" => {
                collect_event_provenance(event, run);
            }
            _ => {}
        }
    }

    fn record_history_event(&mut self, event: &GatewayEvent) {
        let Some(receipts) = event
            .data
            .get("receipts")
            .and_then(|value| value.as_array())
        else {
            return;
        };
        for receipt in receipts {
            let Some(receipt_id) = receipt.get("id").and_then(|value| value.as_str()) else {
                continue;
            };
            let task_id = receipt
                .get("task_id")
                .and_then(|value| value.as_str())
                .map(str::to_owned);
            let run_id = task_id.as_deref().unwrap_or("persisted-history");
            let index = self.ensure_run_record(run_id);
            let run = &mut self.run_records[index];
            if run.task_id.is_none() {
                run.task_id = task_id;
            }
            run.status.get_or_insert_with(|| "persisted".to_owned());
            push_unique_string(&mut run.receipts, receipt_id.to_owned());
            push_unique_string(&mut run.receipt_details, receipt_detail(receipt));
            collect_history_receipt_provenance(receipt, run);
            if let Some(summary) = receipt.get("summary").and_then(|value| value.as_str()) {
                run.outputs.push(summary.to_owned());
            }
        }
        self.normalize_selected_run();
    }

    fn ensure_run_record(&mut self, run_id: &str) -> usize {
        if let Some(index) = self
            .run_records
            .iter()
            .position(|candidate| candidate.run_id == run_id)
        {
            return index;
        }
        self.run_records.push(RunRecord {
            run_id: run_id.to_owned(),
            prompt: self.last_prompt_preview.clone(),
            ..RunRecord::default()
        });
        self.run_records.len() - 1
    }

    pub(crate) fn restart_backend(&mut self) {
        match BackendSession::start() {
            Ok(backend) => {
                self.backend = backend;
                self.backend_connected = true;
                self.last_error = None;
                self.in_flight = false;
                self.transcript.push(TranscriptEntry::system(
                    "Gateway reconnected",
                    "Backend restarted; refreshing readiness, history, and slash commands.",
                ));
                self.send_commands([
                    GatewayCommand::SessionStatus,
                    GatewayCommand::SessionHistory,
                    GatewayCommand::SlashCatalog,
                ]);
            }
            Err(error) => {
                let message = error.to_string();
                self.backend_connected = false;
                self.last_error = Some(message.clone());
                self.transcript
                    .push(TranscriptEntry::error("Gateway reconnect failed", &message));
            }
        }
    }

    pub(crate) fn insert_char(&mut self, ch: char) {
        self.input.insert(self.input_cursor, ch);
        self.input_cursor += ch.len_utf8();
    }

    pub(crate) fn insert_newline(&mut self) {
        self.input.insert(self.input_cursor, '\n');
        self.input_cursor += 1;
    }

    pub(crate) fn paste_text(&mut self, text: &str) {
        if text.is_empty() {
            return;
        }
        self.input.insert_str(self.input_cursor, text);
        self.input_cursor += text.len();
    }

    pub(crate) fn clear_input(&mut self) {
        self.input.clear();
        self.input_cursor = 0;
    }

    pub(crate) fn complete_slash_input(&mut self) {
        if self.input_cursor != self.input.len() {
            return;
        }
        if let Some(completion) = slash_completion(&self.input, &self.slash_catalog) {
            self.input = completion;
            self.input_cursor = self.input.len();
        }
    }

    pub(crate) fn backspace(&mut self) {
        if self.input_cursor == 0 {
            return;
        }
        if let Some((index, _)) = self.input[..self.input_cursor].char_indices().last() {
            self.input.replace_range(index..self.input_cursor, "");
            self.input_cursor = index;
        }
    }

    pub(crate) fn delete(&mut self) {
        if self.input_cursor >= self.input.len() {
            return;
        }
        if let Some(ch) = self.input[self.input_cursor..].chars().next() {
            let next = self.input_cursor + ch.len_utf8();
            self.input.replace_range(self.input_cursor..next, "");
        }
    }

    pub(crate) fn move_cursor_left(&mut self) {
        if self.input_cursor == 0 {
            return;
        }
        if let Some((index, _)) = self.input[..self.input_cursor].char_indices().last() {
            self.input_cursor = index;
        }
    }

    pub(crate) fn move_cursor_right(&mut self) {
        if self.input_cursor >= self.input.len() {
            return;
        }
        if let Some(ch) = self.input[self.input_cursor..].chars().next() {
            self.input_cursor += ch.len_utf8();
        }
    }

    pub(crate) fn move_cursor_home(&mut self) {
        let line_start = self.input[..self.input_cursor]
            .rfind('\n')
            .map(|index| index + 1)
            .unwrap_or(0);
        self.input_cursor = line_start;
    }

    pub(crate) fn move_cursor_end(&mut self) {
        let line_end = self.input[self.input_cursor..]
            .find('\n')
            .map(|index| self.input_cursor + index)
            .unwrap_or(self.input.len());
        self.input_cursor = line_end;
    }

    pub(crate) fn delete_to_line_start(&mut self) {
        let line_start = self.input[..self.input_cursor]
            .rfind('\n')
            .map(|index| index + 1)
            .unwrap_or(0);
        self.input.replace_range(line_start..self.input_cursor, "");
        self.input_cursor = line_start;
    }

    pub(crate) fn delete_to_line_end(&mut self) {
        let line_end = self.input[self.input_cursor..]
            .find('\n')
            .map(|index| self.input_cursor + index)
            .unwrap_or(self.input.len());
        self.input.replace_range(self.input_cursor..line_end, "");
    }

    pub(crate) fn delete_previous_word(&mut self) {
        if self.input_cursor == 0 {
            return;
        }
        let before = &self.input[..self.input_cursor];
        let trim_end = before
            .char_indices()
            .rev()
            .find(|(_, ch)| !ch.is_whitespace())
            .map(|(index, ch)| index + ch.len_utf8())
            .unwrap_or(0);
        let word_start = before[..trim_end]
            .char_indices()
            .rev()
            .find(|(_, ch)| ch.is_whitespace())
            .map(|(index, ch)| index + ch.len_utf8())
            .unwrap_or(0);
        self.input.replace_range(word_start..self.input_cursor, "");
        self.input_cursor = word_start;
    }

    pub(crate) fn input_line_count(&self) -> usize {
        self.input.lines().count().max(1)
    }

    pub(crate) fn input_char_count(&self) -> usize {
        self.input.chars().count()
    }

    pub(crate) fn input_cursor_line_col(&self) -> (usize, usize) {
        let before_cursor = &self.input[..self.input_cursor.min(self.input.len())];
        let line = before_cursor.bytes().filter(|byte| *byte == b'\n').count();
        let col = before_cursor
            .rsplit('\n')
            .next()
            .unwrap_or_default()
            .chars()
            .count();
        (line + 1, col + 1)
    }

    fn input_has_multiple_lines(&self) -> bool {
        self.input.contains('\n')
    }

    fn cursor_is_on_first_line(&self) -> bool {
        !self.input[..self.input_cursor.min(self.input.len())].contains('\n')
    }

    fn cursor_is_on_last_line(&self) -> bool {
        !self.input[self.input_cursor.min(self.input.len())..].contains('\n')
    }

    pub(crate) fn move_cursor_up_line(&mut self) {
        let (line_start, col) = current_line_start_and_col(&self.input, self.input_cursor);
        if line_start == 0 {
            return;
        }
        let previous_end = line_start.saturating_sub(1);
        let previous_start = self.input[..previous_end]
            .rfind('\n')
            .map(|index| index + 1)
            .unwrap_or(0);
        self.input_cursor = byte_index_for_char_col(&self.input, previous_start, previous_end, col);
    }

    pub(crate) fn move_cursor_down_line(&mut self) {
        let (line_start, col) = current_line_start_and_col(&self.input, self.input_cursor);
        let current_end = self.input[line_start..]
            .find('\n')
            .map(|index| line_start + index)
            .unwrap_or(self.input.len());
        if current_end >= self.input.len() {
            return;
        }
        let next_start = current_end + 1;
        let next_end = self.input[next_start..]
            .find('\n')
            .map(|index| next_start + index)
            .unwrap_or(self.input.len());
        self.input_cursor = byte_index_for_char_col(&self.input, next_start, next_end, col);
    }

    pub(crate) fn scroll_transcript_up(&mut self) {
        self.transcript_scroll = self.transcript_scroll.saturating_add(4);
    }

    pub(crate) fn scroll_transcript_down(&mut self) {
        self.transcript_scroll = self.transcript_scroll.saturating_sub(4);
    }

    pub(crate) fn scroll_transcript_top(&mut self) {
        self.transcript_scroll = u16::MAX;
    }

    pub(crate) fn scroll_transcript_bottom(&mut self) {
        self.transcript_scroll = 0;
    }

    fn follow_tail_after_transcript_update(&mut self) {
        if self.transcript_scroll == 0 {
            self.scroll_transcript_bottom();
        }
    }

    pub(crate) fn next_search_match(&mut self) {
        let matches = self.search_match_entry_indexes();
        if matches.is_empty() {
            self.search_match_index = None;
            return;
        }
        let next = self
            .search_match_index
            .map(|index| (index + 1) % matches.len())
            .unwrap_or(0);
        self.search_match_index = Some(next);
        self.transcript_scroll = line_count_after_entry_index(&self.transcript, matches[next]);
    }

    pub(crate) fn previous_search_match(&mut self) {
        let matches = self.search_match_entry_indexes();
        if matches.is_empty() {
            self.search_match_index = None;
            return;
        }
        let previous = self
            .search_match_index
            .map(|index| {
                if index == 0 {
                    matches.len() - 1
                } else {
                    index - 1
                }
            })
            .unwrap_or_else(|| matches.len() - 1);
        self.search_match_index = Some(previous);
        self.transcript_scroll = line_count_after_entry_index(&self.transcript, matches[previous]);
    }

    fn search_match_entry_indexes(&self) -> Vec<usize> {
        if self.search_query.trim().is_empty() {
            return Vec::new();
        }
        self.transcript
            .iter()
            .enumerate()
            .filter_map(|(index, entry)| {
                entry_matches_search(entry, &self.search_query).then_some(index)
            })
            .collect()
    }

    pub(crate) fn transcript_jump_summary(&self) -> Option<String> {
        let jump = self.transcript_jump?;
        let total = self
            .transcript
            .iter()
            .filter(|entry| jump.matches(entry.kind))
            .count();
        if total == 0 {
            return Some(format!("{}: none", jump.label()));
        }
        Some(format!("{}: {total} entries", jump.label()))
    }

    pub(crate) fn jump_to_next_transcript_kind(&mut self, jump: TranscriptJump) {
        self.jump_to_transcript_kind(jump, true);
    }

    pub(crate) fn jump_to_previous_transcript_kind(&mut self, jump: TranscriptJump) {
        self.jump_to_transcript_kind(jump, false);
    }

    fn jump_to_transcript_kind(&mut self, jump: TranscriptJump, forward: bool) {
        let matches = self
            .transcript
            .iter()
            .enumerate()
            .filter_map(|(index, entry)| jump.matches(entry.kind).then_some(index))
            .collect::<Vec<_>>();
        if matches.is_empty() {
            self.transcript_jump = Some(jump);
            self.transcript.push(TranscriptEntry::system(
                "Transcript jump",
                &format!("No {} entries are available.", jump.label()),
            ));
            return;
        }
        let current_line =
            transcript_entry_index_for_scroll(&self.transcript, self.transcript_scroll);
        let selected = if forward {
            matches
                .iter()
                .copied()
                .find(|index| *index > current_line)
                .unwrap_or(matches[0])
        } else {
            matches
                .iter()
                .rev()
                .copied()
                .find(|index| *index < current_line)
                .unwrap_or_else(|| *matches.last().expect("matches not empty"))
        };
        self.transcript_jump = Some(jump);
        self.transcript_scroll = line_count_after_entry_index(&self.transcript, selected);
    }

    fn dispatch_next_queued(&mut self) {
        if self.in_flight || !self.backend_connected {
            return;
        }
        if let Some(text) = self.queued_inputs.pop_front() {
            self.transcript
                .push(TranscriptEntry::progress("Dequeued", &text));
            self.dispatch_text(text);
        }
    }

    pub(crate) fn request_interrupt(&mut self) {
        let Some(run_id) = self.state.run_ids.last().cloned() else {
            self.transcript.push(TranscriptEntry::system(
                "Interrupt",
                "No active run id is available yet.",
            ));
            return;
        };
        self.transcript
            .push(TranscriptEntry::progress("Interrupt requested", &run_id));
        self.send_commands([GatewayCommand::RunInterrupt {
            run_id,
            reason: "operator requested stop".to_owned(),
        }]);
    }

    pub(crate) fn retry_last_prompt(&mut self) {
        let Some(text) = self.last_submitted_text.clone() else {
            self.transcript.push(TranscriptEntry::system(
                "Retry",
                "No submitted prompt is available to retry.",
            ));
            return;
        };
        if self.in_flight {
            self.queued_inputs.push_back(text);
            self.transcript.push(TranscriptEntry::progress(
                "Retry queued",
                "The last prompt will run after the active request completes.",
            ));
            return;
        }
        if !self.backend_connected {
            self.queued_inputs.push_back(text);
            self.transcript.push(TranscriptEntry::progress(
                "Retry queued",
                "Gateway is disconnected. Press Ctrl-B to reconnect; the retry will run after the backend responds.",
            ));
            return;
        }
        self.transcript.push(TranscriptEntry::user("Retry", &text));
        self.auto_select_latest_run = true;
        self.dispatch_text(text);
    }

    pub(crate) fn export_selected_run(&mut self) {
        let Some(run) = self.selected_run() else {
            self.transcript.push(TranscriptEntry::system(
                "Export",
                "No selected run is available to export.",
            ));
            return;
        };
        let markdown = run.export_markdown();
        match write_run_export(&run.run_id, &markdown) {
            Ok(path) => {
                self.transcript.push(TranscriptEntry::system(
                    "Export written",
                    &format!("Path: {}\n\n{}", path.display(), markdown),
                ));
            }
            Err(error) => {
                self.transcript.push(TranscriptEntry::error(
                    "Export failed",
                    &format!("{error}\n\n{markdown}"),
                ));
            }
        }
    }

    pub(crate) fn approve_selected(&mut self) {
        let Some(approval) = self.selected_pending_approval().cloned() else {
            self.transcript.push(TranscriptEntry::system(
                "Approval",
                "No pending approval with an id is available.",
            ));
            return;
        };
        self.transcript.push(TranscriptEntry::new(
            TranscriptKind::Approval,
            "Approving",
            &format!(
                "ID: {}\n{}",
                approval.id,
                approval.preview_text(self.state.receipt_ids.last().map(String::as_str))
            ),
        ));
        self.send_commands([GatewayCommand::ApprovalDecide {
            approval_id: approval.id,
            decision: "approved".to_owned(),
            operator: "user:ratatui".to_owned(),
            reason: "approved from Ratatui client".to_owned(),
        }]);
    }

    pub(crate) fn deny_selected(&mut self) {
        let Some(approval) = self.selected_pending_approval().cloned() else {
            self.transcript.push(TranscriptEntry::system(
                "Approval",
                "No pending approval with an id is available.",
            ));
            return;
        };
        self.transcript.push(TranscriptEntry::new(
            TranscriptKind::Approval,
            "Denying",
            &format!(
                "ID: {}\n{}",
                approval.id,
                approval.preview_text(self.state.receipt_ids.last().map(String::as_str))
            ),
        ));
        self.send_commands([GatewayCommand::ApprovalDecide {
            approval_id: approval.id,
            decision: "denied".to_owned(),
            operator: "user:ratatui".to_owned(),
            reason: "denied from Ratatui client".to_owned(),
        }]);
    }

    pub(crate) fn select_next_approval(&mut self) {
        if self.pending_approvals.is_empty() {
            self.selected_approval_index = None;
            return;
        }
        let next = self
            .selected_approval_index
            .map(|index| (index + 1) % self.pending_approvals.len())
            .unwrap_or(0);
        self.selected_approval_index = Some(next);
    }

    pub(crate) fn select_previous_approval(&mut self) {
        if self.pending_approvals.is_empty() {
            self.selected_approval_index = None;
            return;
        }
        let previous = self
            .selected_approval_index
            .map(|index| {
                if index == 0 {
                    self.pending_approvals.len() - 1
                } else {
                    index - 1
                }
            })
            .unwrap_or(0);
        self.selected_approval_index = Some(previous);
    }

    pub(crate) fn select_next_run(&mut self) {
        let visible = self.filtered_run_indexes();
        if visible.is_empty() {
            self.selected_run_index = None;
            return;
        }
        let position = self
            .selected_run_index
            .and_then(|selected| visible.iter().position(|index| *index == selected))
            .map(|index| (index + 1) % visible.len())
            .unwrap_or(0);
        self.selected_run_index = Some(visible[position]);
        self.auto_select_latest_run = false;
        self.transcript.push(TranscriptEntry::system(
            "Run selected",
            &self.selected_run_detail().unwrap_or_default(),
        ));
    }

    pub(crate) fn select_previous_run(&mut self) {
        let visible = self.filtered_run_indexes();
        if visible.is_empty() {
            self.selected_run_index = None;
            return;
        }
        let position = self
            .selected_run_index
            .and_then(|selected| visible.iter().position(|index| *index == selected))
            .map(|index| {
                if index == 0 {
                    visible.len() - 1
                } else {
                    index - 1
                }
            })
            .unwrap_or_else(|| visible.len() - 1);
        self.selected_run_index = Some(visible[position]);
        self.auto_select_latest_run = false;
        self.transcript.push(TranscriptEntry::system(
            "Run selected",
            &self.selected_run_detail().unwrap_or_default(),
        ));
    }

    pub(crate) fn cycle_run_filter(&mut self) {
        self.run_filter = self.run_filter.next();
        self.normalize_selected_run();
        self.transcript.push(TranscriptEntry::system(
            "Run filter",
            &format!(
                "Showing {} run records. Press Ctrl-L to cycle filters.",
                self.run_filter.label()
            ),
        ));
    }

    fn filtered_run_indexes(&self) -> Vec<usize> {
        self.run_records
            .iter()
            .enumerate()
            .filter_map(|(index, run)| self.run_filter.matches(run).then_some(index))
            .collect()
    }

    fn normalize_selected_run(&mut self) {
        let visible = self.filtered_run_indexes();
        if visible.is_empty() {
            self.selected_run_index = None;
            return;
        }
        if self
            .selected_run_index
            .is_some_and(|selected| visible.contains(&selected))
        {
            return;
        }
        self.selected_run_index = visible.last().copied();
    }

    fn normalize_selected_approval(&mut self) {
        if self.pending_approvals.is_empty() {
            self.selected_approval_index = None;
            return;
        }
        let index = self
            .selected_approval_index
            .unwrap_or_default()
            .min(self.pending_approvals.len() - 1);
        self.selected_approval_index = Some(index);
    }

    pub(crate) fn history_previous(&mut self) {
        if self.history.is_empty() {
            return;
        }
        let index = self
            .history_index
            .map(|index| index.saturating_sub(1))
            .unwrap_or_else(|| self.history.len().saturating_sub(1));
        self.history_index = Some(index);
        self.input = self.history[index].clone();
        self.input_cursor = self.input.len();
    }

    pub(crate) fn history_next(&mut self) {
        let Some(index) = self.history_index else {
            return;
        };
        if index + 1 >= self.history.len() {
            self.history_index = None;
            self.input.clear();
        } else {
            let next = index + 1;
            self.history_index = Some(next);
            self.input = self.history[next].clone();
        }
        self.input_cursor = self.input.len();
    }
}

impl PendingApproval {
    fn from_event(event: &GatewayEvent) -> Self {
        Self {
            id: string_data(event, "approval_id").unwrap_or_default(),
            message: string_data(event, "message")
                .unwrap_or_else(|| "Approval requested.".to_owned()),
            tool: string_data(event, "tool"),
            target: string_data(event, "target"),
            reason: string_data(event, "reason"),
            risk: string_data(event, "risk").or_else(|| string_data(event, "risk_text")),
            command: string_data(event, "command"),
        }
    }

    fn request_text(&self, latest_receipt: Option<&str>) -> String {
        format!(
            "{}\nActions: Ctrl-A approve / Ctrl-X deny / Ctrl-N Ctrl-P select",
            self.preview_text(latest_receipt)
        )
    }

    fn preview_text(&self, latest_receipt: Option<&str>) -> String {
        let mut lines = vec![
            "Review required".to_owned(),
            "State: pending".to_owned(),
            format!(
                "ID: {}",
                if self.id.is_empty() {
                    "unknown"
                } else {
                    self.id.as_str()
                }
            ),
            format!("Request: {}", self.message),
        ];
        push_optional_line(&mut lines, "Tool", self.tool.as_deref());
        push_optional_line(&mut lines, "Target", self.target.as_deref());
        push_optional_line(&mut lines, "Command", self.command.as_deref());
        push_optional_line(&mut lines, "Reason", self.reason.as_deref());
        push_optional_line(&mut lines, "Risk", self.risk.as_deref());
        if self.risk.as_deref().is_some_and(is_high_risk_text) {
            lines.push(
                "Confirmation: high-risk approval; review target and receipt before deciding"
                    .to_owned(),
            );
        }
        push_optional_line(&mut lines, "Latest receipt", latest_receipt);
        lines.join("\n")
    }
}

impl RunRecord {
    fn is_active(&self) -> bool {
        matches!(
            self.status.as_deref(),
            None | Some("running") | Some("thinking") | Some("working") | Some("queued")
        )
    }

    fn is_completed(&self) -> bool {
        matches!(
            self.status.as_deref(),
            Some("completed") | Some("passed") | Some("persisted")
        )
    }

    fn is_failed(&self) -> bool {
        matches!(
            self.status.as_deref(),
            Some("failed") | Some("error") | Some("denied") | Some("blocked")
        )
    }

    fn detail_text(&self) -> String {
        let mut lines = vec![
            format!("Run: {}", self.run_id),
            format!("Status: {}", self.status.as_deref().unwrap_or("active")),
        ];
        push_optional_line(&mut lines, "Task", self.task_id.as_deref());
        push_optional_line(&mut lines, "Prompt", self.prompt.as_deref());
        push_optional_line(&mut lines, "Provider", self.provider.as_deref());
        push_optional_line(&mut lines, "Model", self.model.as_deref());
        push_count_line(&mut lines, "Tools", &self.tools);
        push_count_line(&mut lines, "Files", &self.files);
        push_count_line(&mut lines, "Commands", &self.commands);
        push_count_line(&mut lines, "Approvals", &self.approvals);
        push_count_line(&mut lines, "Receipts", &self.receipts);
        push_detail_section(&mut lines, "Receipt detail", &self.receipt_details);
        push_detail_section(&mut lines, "Provenance", &self.provenance);
        push_detail_section(&mut lines, "Tools", &self.tools);
        push_detail_section(&mut lines, "Files", &self.files);
        push_detail_section(&mut lines, "Commands", &self.commands);
        push_detail_section(&mut lines, "Approvals", &self.approvals);
        if let Some(output) = self.outputs.last() {
            lines.push(format!("Latest output: {}", compact_text(output, 96)));
        }
        push_detail_section(&mut lines, "Outputs", &self.outputs);
        lines.join("\n")
    }

    fn export_markdown(&self) -> String {
        let mut lines = vec![
            format!("# Craik Run Handoff: {}", self.run_id),
            String::new(),
            format!("- Status: {}", self.status.as_deref().unwrap_or("active")),
        ];
        push_optional_bullet(&mut lines, "Task", self.task_id.as_deref());
        push_optional_bullet(&mut lines, "Provider", self.provider.as_deref());
        push_optional_bullet(&mut lines, "Model", self.model.as_deref());
        push_optional_bullet(&mut lines, "Prompt", self.prompt.as_deref());
        lines.push(String::new());
        push_markdown_section(&mut lines, "Receipts", &self.receipts);
        push_markdown_section(&mut lines, "Receipt Detail", &self.receipt_details);
        push_markdown_section(&mut lines, "Tools", &self.tools);
        push_markdown_section(&mut lines, "Commands", &self.commands);
        push_markdown_section(&mut lines, "Files", &self.files);
        push_markdown_section(&mut lines, "Approvals", &self.approvals);
        push_markdown_section(&mut lines, "Provenance", &self.provenance);
        push_markdown_section(&mut lines, "Outputs", &self.outputs);
        lines.join("\n")
    }
}

fn summarize_model_event(event: &GatewayEvent) -> String {
    let mut lines = Vec::new();
    push_optional_data_line(&mut lines, event, "Display", "display_name");
    push_optional_data_line(&mut lines, event, "Model", "model");
    push_optional_data_line(&mut lines, event, "Provider", "provider_id");
    push_optional_data_line(&mut lines, event, "Family", "provider_family");
    push_optional_data_line(&mut lines, event, "Backend", "backend");
    if let Some(live_enabled) = event
        .data
        .get("live_enabled")
        .and_then(|value| value.as_bool())
    {
        lines.push(format!("Live: {live_enabled}"));
    }
    if let Some(profile) = event
        .data
        .get("profile")
        .and_then(|value| value.as_object())
        && let Some(profile_name) = profile.get("name").and_then(|value| value.as_str())
    {
        lines.push(format!("Profile: {profile_name}"));
    }
    if lines.is_empty() {
        lines.push("Model: selected".to_owned());
    }
    lines.join("\n")
}

fn summarize_session_ready_event(event: &GatewayEvent) -> String {
    let mut lines = vec!["Session ready.".to_owned()];
    push_optional_data_line(&mut lines, event, "Transport", "transport");
    push_optional_data_line(&mut lines, event, "Protocol", "protocol");
    push_optional_data_line(&mut lines, event, "Version", "protocol_version");
    lines.join("\n")
}

fn blocked_run_guidance(event: &GatewayEvent) -> String {
    let mut lines = vec!["The Gateway is not ready to start a model run.".to_owned()];
    push_optional_data_line(&mut lines, event, "State", "state");
    if let Some(missing) = event.data.get("missing").and_then(|value| value.as_array()) {
        let values = missing
            .iter()
            .filter_map(|value| value.as_str())
            .collect::<Vec<_>>();
        if !values.is_empty() {
            lines.push(format!("Missing: {}", values.join(", ")));
        }
    }
    if let Some(next_actions) = event
        .data
        .get("next_actions")
        .and_then(|value| value.as_array())
    {
        for action in next_actions
            .iter()
            .filter_map(|value| value.as_str())
            .take(3)
        {
            lines.push(format!("Next: {action}"));
        }
    }
    if lines.len() == 1 {
        lines.push("Run `/status` or check provider authentication.".to_owned());
    }
    lines.join("\n")
}

fn summarize_run_event(event: &GatewayEvent, fallback: &str) -> String {
    let mut lines = Vec::new();
    if let Some(run_id) = event.run_id.as_deref() {
        lines.push(format!("Run: {run_id}"));
    }
    if let Some(task_id) = event.task_id.as_deref() {
        lines.push(format!("Task: {task_id}"));
    }
    push_optional_data_line(&mut lines, event, "Status", "status");
    push_optional_data_line(&mut lines, event, "Provider", "provider_id");
    push_optional_data_line(&mut lines, event, "Family", "provider_family");
    push_optional_data_line(&mut lines, event, "Model", "model");
    if lines.is_empty() {
        lines.push(format!("Detail: {fallback}"));
    }
    lines.join("\n")
}

fn summarize_working_event(event: &GatewayEvent, phase: &str) -> String {
    let mut lines = vec![format!("Phase: {phase}")];
    push_optional_data_line(&mut lines, event, "Backend", "backend");
    push_optional_data_line(&mut lines, event, "Provider", "provider_id");
    push_optional_data_line(&mut lines, event, "Model", "model");
    push_optional_data_line(&mut lines, event, "Detail", "message");
    lines.join("\n")
}

fn summarize_tool_event(event: &GatewayEvent, tool: &str, fallback_message: &str) -> String {
    let mut lines = Vec::new();
    lines.push(format!("Tool: {tool}"));
    push_optional_data_line(&mut lines, event, "Provider", "provider_id");
    push_optional_data_line(&mut lines, event, "Family", "provider_family");
    push_optional_data_line(&mut lines, event, "Model", "model");
    push_optional_data_line(&mut lines, event, "Response", "response_id");
    if let Some(command) = event.data.get("command").and_then(|value| value.as_str()) {
        lines.push(format!("Command: {command}"));
    }
    if let Some(target) = event.data.get("target").and_then(|value| value.as_str()) {
        lines.push(format!("Target: {target}"));
    }
    lines.push(format!("Detail: {fallback_message}"));
    lines.join("\n")
}

fn summarize_receipt_event(event: &GatewayEvent, receipt_id: &str) -> String {
    let mut lines = vec![format!("Receipt: {receipt_id}")];
    if let Some(run_id) = event.run_id.as_deref() {
        lines.push(format!("Run: {run_id}"));
    }
    if let Some(task_id) = event.task_id.as_deref() {
        lines.push(format!("Task: {task_id}"));
    }
    push_optional_data_line(&mut lines, event, "Provider", "provider_id");
    push_optional_data_line(&mut lines, event, "Family", "provider_family");
    lines.join("\n")
}

fn string_data(event: &GatewayEvent, key: &str) -> Option<String> {
    event
        .data
        .get(key)
        .and_then(|value| value.as_str())
        .filter(|value| !value.trim().is_empty())
        .map(str::to_owned)
}

fn push_optional_line(lines: &mut Vec<String>, label: &str, value: Option<&str>) {
    if let Some(value) = value {
        lines.push(format!("{label}: {value}"));
    }
}

fn push_optional_bullet(lines: &mut Vec<String>, label: &str, value: Option<&str>) {
    if let Some(value) = value {
        lines.push(format!("- {label}: {value}"));
    }
}

fn append_recent(lines: &mut Vec<String>, title: &str, values: &[String]) {
    if values.is_empty() {
        return;
    }
    lines.push(String::new());
    lines.push(title.to_owned());
    lines.extend(
        values
            .iter()
            .rev()
            .take(5)
            .map(|value| format!("  {value}")),
    );
}

fn push_markdown_section(lines: &mut Vec<String>, title: &str, values: &[String]) {
    lines.push(format!("## {title}"));
    if values.is_empty() {
        lines.push("- None".to_owned());
    } else {
        lines.extend(values.iter().map(|value| format!("- {value}")));
    }
    lines.push(String::new());
}

fn write_run_export(run_id: &str, markdown: &str) -> std::io::Result<PathBuf> {
    let home = env::var_os("CRAIK_HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(|home| PathBuf::from(home).join(".craik")))
        .unwrap_or_else(|| PathBuf::from(".craik"));
    let dir = home.join("state").join("exports");
    fs::create_dir_all(&dir)?;
    let path = dir.join(format!("{}.md", export_file_stem(run_id)));
    fs::write(&path, markdown)?;
    Ok(path)
}

fn export_file_stem(run_id: &str) -> String {
    let stem = run_id
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>();
    if stem.is_empty() {
        "run".to_owned()
    } else {
        stem
    }
}

fn push_count_line(lines: &mut Vec<String>, label: &str, values: &[String]) {
    let suffix = values
        .last()
        .map(|value| format!(" latest {}", compact_text(value, 48)))
        .unwrap_or_default();
    lines.push(format!("{label}: {}{suffix}", values.len()));
}

fn push_detail_section(lines: &mut Vec<String>, label: &str, values: &[String]) {
    if values.is_empty() {
        return;
    }
    lines.push(format!("{label}:"));
    for value in values.iter().take(8) {
        lines.push(format!("- {value}"));
    }
    if values.len() > 8 {
        lines.push(format!("- ... {} more", values.len() - 8));
    }
}

fn push_unique_string(values: &mut Vec<String>, value: String) {
    if !values.iter().any(|candidate| candidate == &value) {
        values.push(value);
    }
}

fn compact_text(value: &str, max_chars: usize) -> String {
    let char_count = value.chars().count();
    if char_count <= max_chars {
        return value.to_owned();
    }
    let keep = max_chars.saturating_sub(3);
    format!("{}...", value.chars().take(keep).collect::<String>())
}

fn collect_event_provenance(event: &GatewayEvent, run: &mut RunRecord) {
    match event.event_type.as_str() {
        "run.working" => {
            if let Some(message) = string_data(event, "message") {
                push_unique_string(&mut run.provenance, format!("Working: {message}"));
            }
        }
        "tool.used" => {
            if let Some(tool) = string_data(event, "tool") {
                push_unique_string(&mut run.provenance, format!("Tool used: {tool}"));
            }
        }
        "file.changed" => {
            if let Some(target) = string_data(event, "target") {
                push_unique_string(&mut run.provenance, format!("File changed: {target}"));
            }
        }
        "approval.requested" => {
            if let Some(approval_id) = string_data(event, "approval_id") {
                push_unique_string(
                    &mut run.provenance,
                    format!("Approval requested: {approval_id}"),
                );
            }
        }
        "approval.resolved" => {
            let approval_id =
                string_data(event, "approval_id").unwrap_or_else(|| "approval".to_owned());
            let decision = string_data(event, "decision").unwrap_or_else(|| "resolved".to_owned());
            push_unique_string(
                &mut run.provenance,
                format!("Approval resolved: {approval_id} {decision}"),
            );
        }
        "approval.denied" => {
            let approval_id =
                string_data(event, "approval_id").unwrap_or_else(|| "approval".to_owned());
            push_unique_string(
                &mut run.provenance,
                format!("Approval denied: {approval_id}"),
            );
        }
        "receipt.created" => {
            if let Some(receipt_id) = string_data(event, "receipt_id") {
                push_unique_string(
                    &mut run.provenance,
                    format!("Receipt created: {receipt_id}"),
                );
            }
        }
        "run.output" => {
            if let Some(summary) = string_data(event, "summary") {
                push_unique_string(
                    &mut run.provenance,
                    format!("Output: {}", compact_text(&summary, 120)),
                );
            }
        }
        "run.event" => {
            if let Some(text) = string_data(event, "text").or_else(|| string_data(event, "message"))
            {
                push_unique_string(
                    &mut run.provenance,
                    format!("Event: {}", compact_text(&text, 120)),
                );
            }
        }
        _ => {}
    }
    collect_string_list_from_data(event, run, "files", EvidenceTarget::Files);
    collect_string_list_from_data(event, run, "commands", EvidenceTarget::Commands);
    collect_string_list_from_data(event, run, "receipts", EvidenceTarget::Receipts);
}

enum EvidenceTarget {
    Files,
    Commands,
    Receipts,
}

fn collect_string_list_from_data(
    event: &GatewayEvent,
    run: &mut RunRecord,
    field: &str,
    target: EvidenceTarget,
) {
    let Some(values) = event.data.get(field).and_then(|value| value.as_array()) else {
        return;
    };
    for value in values.iter().filter_map(|value| value.as_str()) {
        match target {
            EvidenceTarget::Files => push_unique_string(&mut run.files, value.to_owned()),
            EvidenceTarget::Commands => push_unique_string(&mut run.commands, value.to_owned()),
            EvidenceTarget::Receipts => push_unique_string(&mut run.receipts, value.to_owned()),
        }
    }
}

fn receipt_detail(receipt: &serde_json::Value) -> String {
    let mut parts = Vec::new();
    if let Some(id) = receipt.get("id").and_then(|value| value.as_str()) {
        parts.push(format!("id={id}"));
    }
    if let Some(capability) = receipt.get("capability").and_then(|value| value.as_str()) {
        parts.push(format!("capability={capability}"));
    }
    if let Some(target) = receipt.get("target").and_then(|value| value.as_str()) {
        parts.push(format!("target={target}"));
    }
    if let Some(status) = receipt.get("status").and_then(|value| value.as_str()) {
        parts.push(format!("status={status}"));
    }
    if let Some(summary) = receipt.get("summary").and_then(|value| value.as_str()) {
        parts.push(format!("summary={}", compact_text(summary, 96)));
    }
    parts.join(" | ")
}

fn collect_history_receipt_provenance(receipt: &serde_json::Value, run: &mut RunRecord) {
    for field in [
        "tools",
        "files",
        "commands",
        "approvals",
        "outputs",
        "evidence_ids",
        "handoff_ids",
    ] {
        if let Some(values) = receipt.get(field).and_then(|value| value.as_array()) {
            for value in values.iter().filter_map(|value| value.as_str()) {
                match field {
                    "tools" => push_unique_string(&mut run.tools, value.to_owned()),
                    "files" => push_unique_string(&mut run.files, value.to_owned()),
                    "commands" => push_unique_string(&mut run.commands, value.to_owned()),
                    "approvals" => push_unique_string(&mut run.approvals, value.to_owned()),
                    "outputs" => run.outputs.push(value.to_owned()),
                    "evidence_ids" | "handoff_ids" => {
                        push_unique_string(&mut run.provenance, format!("{field}: {value}"));
                    }
                    _ => {}
                }
            }
        }
    }
    if let Some(reason) = receipt.get("reason").and_then(|value| value.as_str()) {
        push_unique_string(&mut run.provenance, format!("Reason: {reason}"));
    }
    if let Some(created_at) = receipt.get("created_at").and_then(|value| value.as_str()) {
        push_unique_string(&mut run.provenance, format!("Receipt time: {created_at}"));
    }
}

fn current_line_start_and_col(input: &str, cursor: usize) -> (usize, usize) {
    let cursor = cursor.min(input.len());
    let line_start = input[..cursor]
        .rfind('\n')
        .map(|index| index + 1)
        .unwrap_or(0);
    let col = input[line_start..cursor].chars().count();
    (line_start, col)
}

fn byte_index_for_char_col(input: &str, start: usize, end: usize, col: usize) -> usize {
    input[start..end]
        .char_indices()
        .nth(col)
        .map(|(index, _)| start + index)
        .unwrap_or(end)
}

fn is_high_risk_text(value: &str) -> bool {
    let lower = value.to_lowercase();
    ["write", "delete", "secret", "credential", "network", "exec"]
        .iter()
        .any(|needle| lower.contains(needle))
}

fn push_optional_data_line(lines: &mut Vec<String>, event: &GatewayEvent, label: &str, key: &str) {
    if let Some(value) = string_data(event, key) {
        lines.push(format!("{label}: {value}"));
    }
}

fn entry_matches_search(entry: &TranscriptEntry, query: &str) -> bool {
    let query = query.to_lowercase();
    !query.trim().is_empty()
        && (entry.title.to_lowercase().contains(&query)
            || entry.body.to_lowercase().contains(&query))
}

fn line_count_after_entry_index(entries: &[TranscriptEntry], target_index: usize) -> u16 {
    let mut count = 0usize;
    for (index, entry) in entries.iter().enumerate() {
        if index <= target_index {
            continue;
        }
        count += entry.body.lines().count().max(1) + 2;
    }
    count.min(u16::MAX as usize) as u16
}

fn transcript_entry_index_for_scroll(entries: &[TranscriptEntry], scroll: u16) -> usize {
    let mut remaining = scroll as usize;
    for (index, entry) in entries.iter().rev().enumerate() {
        let lines = entry.body.lines().count().max(1) + 2;
        if remaining <= lines {
            return entries.len().saturating_sub(index + 1);
        }
        remaining = remaining.saturating_sub(lines);
    }
    0
}

#[cfg(test)]
mod tests {
    use super::{ActiveOverlay, InteractiveApp, LoopAction, RunRecord, export_file_stem};
    use crate::backend::{WorkerMessage, format_backend_closed};
    use crate::input::SlashHint;
    use craik_tui_rs::GatewayEvent;
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
    use serde_json::json;
    use std::collections::VecDeque;

    #[test]
    fn backend_close_unblocks_working_state() {
        let close_message = format_backend_closed();
        let mut app =
            InteractiveApp::for_test_with_messages([WorkerMessage::Closed(close_message.clone())]);
        app.in_flight = true;
        app.state.working_phase = Some("waiting".to_owned());

        app.drain_worker();

        assert!(!app.in_flight);
        assert!(!app.backend_connected);
        assert_eq!(app.state.working_phase, None);
        assert_eq!(app.last_error.as_deref(), Some(close_message.as_str()));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Gateway disconnected")
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Reconnect")
        );
    }

    #[test]
    fn status_not_ready_surfaces_blocked_run_guidance() {
        let status = GatewayEvent {
            event_type: "session.status".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "state": "unconfigured",
                "missing": ["provider credentials"],
                "next_actions": ["run craik auth login anthropic"]
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&status);

        let entry = app
            .transcript
            .iter()
            .find(|entry| entry.title == "Run blocked")
            .expect("blocked guidance entry");
        assert!(entry.body.contains("Missing: provider credentials"));
        assert!(entry.body.contains("Next: run craik auth login anthropic"));
    }

    #[test]
    fn session_history_loads_persisted_receipts_into_run_records() {
        let history = GatewayEvent {
            event_type: "session.history".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "receipts": [
                    {
                        "id": "receipt_history_1",
                        "task_id": "task_history_1",
                        "capability": "shell.execute",
                        "target": "cargo test",
                        "status": "completed",
                        "summary": "Persisted receipt",
                        "reason": "verify the TUI",
                        "commands": ["cargo test"],
                        "files": ["crates/craik-tui-rs/src/app.rs"],
                        "approvals": ["approval_history_1"],
                        "evidence_ids": ["evidence_history_1"]
                    }
                ]
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&history);

        assert_eq!(app.run_records.len(), 1);
        assert_eq!(
            app.selected_run_summary().as_deref(),
            Some("1/1 task_history_1 [persisted] filter=all")
        );
        assert!(
            app.selected_run_detail()
                .expect("run detail")
                .contains("Receipts: 1 latest receipt_history_1")
        );
        let detail = app.selected_run_detail().expect("run detail");
        assert!(detail.contains("Receipt detail:"));
        assert!(detail.contains("capability=shell.execute"));
        assert!(detail.contains("Commands:"));
        assert!(detail.contains("- cargo test"));
        assert!(detail.contains("Files:"));
        assert!(detail.contains("- crates/craik-tui-rs/src/app.rs"));
        assert!(detail.contains("Approvals:"));
        assert!(detail.contains("- approval_history_1"));
        assert!(detail.contains("evidence_ids: evidence_history_1"));
    }

    #[test]
    fn completed_run_without_output_is_visible() {
        let completed = GatewayEvent {
            event_type: "run.completed".to_owned(),
            created_at: None,
            run_id: Some("run_empty".to_owned()),
            task_id: None,
            data: json!({"status": "completed"}),
        };
        let mut app = InteractiveApp::for_test_with_messages([WorkerMessage::Event(completed)]);
        app.in_flight = true;

        app.drain_worker();

        assert!(!app.in_flight);
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "No model output")
        );
    }

    #[test]
    fn prompt_submission_stream_lifecycle_reaches_completed_state() {
        let events = [
            event(
                "prompt.submitted",
                None,
                Some("task_review"),
                json!({"source": "jsonl", "prompt_preview": "Review the implementation plan"}),
            ),
            event(
                "model.selected",
                None,
                Some("task_review"),
                json!({
                    "provider_id": "provider_anthropic",
                    "provider_family": "anthropic",
                    "model": "claude-opus-4-7",
                    "profile": {
                        "display_name": "Anthropic Claude Opus 4.7",
                        "backend": "claude-code"
                    }
                }),
            ),
            event(
                "run.working",
                None,
                Some("task_review"),
                json!({"backend": "claude-code", "phase": "thinking", "message": "Planning changes"}),
            ),
            event(
                "run.started",
                Some("run_review"),
                Some("task_review"),
                json!({"backend": "claude-code", "provider_id": "provider_anthropic", "model": "claude-opus-4-7"}),
            ),
            event(
                "tool.used",
                Some("run_review"),
                Some("task_review"),
                json!({"tool": "Bash", "command": "cargo test", "message": "Running Rust tests"}),
            ),
            event(
                "approval.requested",
                Some("run_review"),
                Some("task_review"),
                json!({
                    "approval_id": "approval_edit_plan",
                    "message": "Edit crates/craik-tui-rs/src/app.rs?",
                    "tool": "Edit",
                    "target": "crates/craik-tui-rs/src/app.rs",
                    "reason": "apply lifecycle polish"
                }),
            ),
            event(
                "approval.resolved",
                Some("run_review"),
                Some("task_review"),
                json!({
                    "approval_id": "approval_edit_plan",
                    "decision": "approved",
                    "operator": "user:ratatui"
                }),
            ),
            event(
                "file.changed",
                Some("run_review"),
                Some("task_review"),
                json!({
                    "target": "crates/craik-tui-rs/src/app.rs",
                    "message": "Updated lifecycle handling"
                }),
            ),
            event(
                "run.output",
                Some("run_review"),
                Some("task_review"),
                json!({"summary": "Reviewed the plan and hardened the TUI lifecycle."}),
            ),
            event(
                "receipt.created",
                Some("run_review"),
                Some("task_review"),
                json!({"receipt_id": "receipt_run_review_lifecycle"}),
            ),
            event(
                "run.completed",
                Some("run_review"),
                Some("task_review"),
                json!({"status": "completed", "backend": "claude-code"}),
            ),
        ];
        let messages = events.into_iter().map(WorkerMessage::Event);
        let mut app = InteractiveApp::for_test_with_messages(messages);
        app.input = "Review the implementation plan".to_owned();
        app.input_cursor = app.input.len();

        app.submit_input();

        assert!(app.in_flight);
        assert_eq!(app.state.working_phase.as_deref(), Some("waiting"));
        assert!(app.input.is_empty());

        app.drain_worker();

        assert!(!app.in_flight);
        assert_eq!(app.state.working_phase, None);
        assert_eq!(app.state.run_status.as_deref(), Some("completed"));
        assert_eq!(app.state.active_model.as_deref(), Some("claude-opus-4-7"));
        assert_eq!(
            app.state.active_model_display_name.as_deref(),
            Some("Anthropic Claude Opus 4.7")
        );
        assert_eq!(app.state.outputs.len(), 1);
        assert_eq!(app.pending_approval_count(), 0);
        assert_eq!(app.run_records.len(), 1);

        let detail = app.selected_run_detail().expect("run detail");
        assert!(detail.contains("Status: completed"));
        assert!(detail.contains("Provider: provider_anthropic"));
        assert!(detail.contains("Model: claude-opus-4-7"));
        assert!(detail.contains("Tools: 1 latest Bash"));
        assert!(detail.contains("Commands: 1 latest cargo test"));
        assert!(detail.contains("Files: 1 latest crates/craik-tui-rs/src/app.rs"));
        assert!(detail.contains("Approvals: 1 latest Edit crates/craik-tui-rs/src/app.rs?"));
        assert!(detail.contains("Receipts: 1 latest receipt_run_review_lifecycle"));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Run state" && entry.body.contains("thinking"))
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approval approved")
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Run completed")
        );
        assert!(
            app.transcript
                .iter()
                .all(|entry| entry.title != "No model output")
        );
    }

    #[test]
    fn backend_error_unblocks_waiting_prompt_state() {
        let mut app = InteractiveApp::for_test_with_messages([WorkerMessage::Error(
            "backend event contract violation".to_owned(),
        )]);
        app.in_flight = true;
        app.state.working_phase = Some("waiting".to_owned());

        app.drain_worker();

        assert!(!app.in_flight);
        assert_eq!(app.state.working_phase, None);
        assert_eq!(
            app.last_error.as_deref(),
            Some("backend event contract violation")
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Gateway error")
        );
    }

    #[test]
    fn structured_contract_error_event_gets_actionable_title() {
        let mut app =
            InteractiveApp::for_test_with_messages([WorkerMessage::Event(GatewayEvent {
                event_type: "error".to_owned(),
                created_at: None,
                run_id: Some("run_contract".to_owned()),
                task_id: Some("task_contract".to_owned()),
                data: json!({
                    "kind": "contract_violation",
                    "message": "Gateway backend emitted invalid event `run.completed`.",
                    "issues": ["run_id is required"],
                    "backend": "provider",
                    "provider_id": "provider_anthropic",
                    "recovery": "Update the backend emitter before retrying."
                }),
            })]);

        app.drain_worker();

        let entry = app
            .transcript
            .iter()
            .find(|entry| entry.title == "Gateway contract violation")
            .expect("structured contract error is visible");
        assert!(entry.body.contains("run run_contract"));
        assert!(entry.body.contains("- run_id is required"));
        assert!(entry.body.contains("Recovery: Update the backend emitter"));
    }

    #[test]
    fn approval_request_tracks_pending_state_and_actions() {
        let receipt = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({"receipt_id": "receipt_before_approval"}),
        };
        let approval = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_edit_123",
                "message": "Edit src/lib.rs?",
                "tool": "Edit",
                "target": "src/lib.rs",
                "reason": "normalize event mapping",
                "risk": "writes source files"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.state.apply_event(&receipt);
        app.record_event(&receipt);
        app.record_event(&approval);

        assert_eq!(app.pending_approval_count(), 1);
        assert_eq!(app.latest_pending_approval(), Some("approval_edit_123"));
        assert_eq!(
            app.selected_approval_summary().as_deref(),
            Some("1/1 pending - approval_edit_123 -> src/lib.rs")
        );
        assert!(
            app.selected_approval_preview()
                .expect("approval preview")
                .contains("Risk: writes source files")
        );
        assert!(
            app.selected_approval_preview()
                .expect("approval preview")
                .contains("Latest receipt: receipt_before_approval")
        );
        let entry = app.transcript.last().expect("approval transcript entry");
        assert_eq!(entry.title, "Approval pending");
        assert!(entry.body.contains("Review required"));
        assert!(entry.body.contains("State: pending"));
        assert!(entry.body.contains("ID: approval_edit_123"));
        assert!(entry.body.contains("Request: Edit src/lib.rs?"));
        assert!(entry.body.contains("Tool: Edit"));
        assert!(entry.body.contains("Target: src/lib.rs"));
        assert!(entry.body.contains("Reason: normalize event mapping"));
        assert!(entry.body.contains("Confirmation: high-risk approval"));
        assert!(
            entry
                .body
                .contains("Latest receipt: receipt_before_approval")
        );
        assert!(entry.body.contains("Ctrl-A approve / Ctrl-X deny"));
    }

    #[test]
    fn run_records_collect_evidence_and_can_be_navigated() {
        let first = GatewayEvent {
            event_type: "run.started".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({"model": "claude-sonnet", "provider_id": "provider_anthropic"}),
        };
        let tool = GatewayEvent {
            event_type: "tool.used".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({"tool": "Bash", "command": "cargo test", "message": "ran tests"}),
        };
        let receipt = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({"receipt_id": "receipt_run_1"}),
        };
        let second = GatewayEvent {
            event_type: "run.started".to_owned(),
            created_at: None,
            run_id: Some("run_2".to_owned()),
            task_id: Some("task_2".to_owned()),
            data: json!({"model": "gpt-5.4", "provider_id": "provider_openai"}),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&first);
        app.record_event(&tool);
        app.record_event(&receipt);
        app.record_event(&second);

        assert_eq!(app.run_records.len(), 2);
        assert_eq!(
            app.selected_run_summary().as_deref(),
            Some("2/2 run_2 [running] filter=all")
        );

        app.select_previous_run();

        assert_eq!(
            app.selected_run_summary().as_deref(),
            Some("1/2 run_1 [running] filter=all")
        );
        let detail = app.selected_run_detail().expect("run detail");
        assert!(detail.contains("Provider: provider_anthropic"));
        assert!(detail.contains("Tools: 1 latest Bash"));
        assert!(detail.contains("Commands: 1 latest cargo test"));
        assert!(detail.contains("Receipts: 1 latest receipt_run_1"));
    }

    #[test]
    fn run_filter_preserves_manual_selection_while_new_events_arrive() {
        let first = GatewayEvent {
            event_type: "run.completed".to_owned(),
            created_at: None,
            run_id: Some("run_done".to_owned()),
            task_id: None,
            data: json!({"status": "completed"}),
        };
        let second = GatewayEvent {
            event_type: "run.started".to_owned(),
            created_at: None,
            run_id: Some("run_active".to_owned()),
            task_id: None,
            data: json!({}),
        };
        let third = GatewayEvent {
            event_type: "run.started".to_owned(),
            created_at: None,
            run_id: Some("run_new".to_owned()),
            task_id: None,
            data: json!({}),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&first);
        app.record_event(&second);
        app.select_previous_run();
        app.record_event(&third);

        assert!(
            app.selected_run_summary()
                .expect("selected run")
                .contains("run_done")
        );

        app.cycle_run_filter();

        assert_eq!(app.run_filter, super::RunFilter::Active);
        assert!(
            app.selected_run_summary()
                .expect("selected run")
                .contains("filter=active")
        );
        assert!(
            app.selected_run_summary()
                .expect("selected run")
                .contains("run_new")
        );
    }

    #[test]
    fn retry_last_prompt_queues_or_dispatches_last_submission() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.input = "Review the plan".to_owned();
        app.input_cursor = app.input.len();

        app.submit_input();
        app.in_flight = true;
        app.retry_last_prompt();

        assert_eq!(
            app.queued_inputs,
            VecDeque::from(["Review the plan".to_owned()])
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Retry queued")
        );
    }

    #[test]
    fn disconnected_prompt_is_queued_for_reconnect() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.backend_connected = false;
        app.input = "Review recovery UX".to_owned();
        app.input_cursor = app.input.len();

        app.submit_input();

        assert!(!app.in_flight);
        assert_eq!(
            app.queued_inputs,
            VecDeque::from(["Review recovery UX".to_owned()])
        );
        assert_eq!(
            app.last_submitted_text.as_deref(),
            Some("Review recovery UX")
        );
        assert!(
            app.prompt_context()
                .contains("Queued for reconnect: 1 prompt(s).")
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Queued until reconnect")
        );
    }

    #[test]
    fn disconnected_retry_is_queued_without_sending() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.backend_connected = false;
        app.last_submitted_text = Some("Retry recovery UX".to_owned());

        app.retry_last_prompt();

        assert!(!app.in_flight);
        assert_eq!(
            app.queued_inputs,
            VecDeque::from(["Retry recovery UX".to_owned()])
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Retry queued")
        );
    }

    #[test]
    fn queued_prompt_waits_until_backend_reconnects() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.backend_connected = false;
        app.queued_inputs
            .push_back("Run after reconnect".to_owned());

        app.dispatch_next_queued();
        assert_eq!(app.queued_inputs.len(), 1);
        assert!(!app.in_flight);

        app.backend_connected = true;
        app.dispatch_next_queued();

        assert!(app.queued_inputs.is_empty());
        assert!(app.in_flight);
        assert!(app.transcript.iter().any(|entry| entry.title == "Dequeued"));
    }

    #[test]
    fn live_events_stream_into_run_provenance_detail() {
        let started = GatewayEvent {
            event_type: "run.started".to_owned(),
            created_at: None,
            run_id: Some("run_live".to_owned()),
            task_id: Some("task_live".to_owned()),
            data: json!({"model": "claude-opus", "provider_id": "provider_anthropic"}),
        };
        let working = GatewayEvent {
            event_type: "run.working".to_owned(),
            created_at: None,
            run_id: Some("run_live".to_owned()),
            task_id: Some("task_live".to_owned()),
            data: json!({
                "backend": "provider",
                "phase": "thinking",
                "message": "Planning edits"
            }),
        };
        let tool = GatewayEvent {
            event_type: "tool.used".to_owned(),
            created_at: None,
            run_id: Some("run_live".to_owned()),
            task_id: Some("task_live".to_owned()),
            data: json!({
                "tool": "Bash",
                "command": "cargo test",
                "files": ["crates/craik-tui-rs/src/app.rs"],
                "message": "Tests passed"
            }),
        };
        let output = GatewayEvent {
            event_type: "run.output".to_owned(),
            created_at: None,
            run_id: Some("run_live".to_owned()),
            task_id: Some("task_live".to_owned()),
            data: json!({"summary": "Implemented provenance detail."}),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        for event in [&started, &working, &tool, &output] {
            app.record_event(event);
        }

        let detail = app.selected_run_detail().expect("run detail");
        assert!(detail.contains("Status: thinking"));
        assert!(detail.contains("Provenance:"));
        assert!(detail.contains("- Phase: thinking"));
        assert!(detail.contains("- Working: Planning edits"));
        assert!(detail.contains("- Tool used: Bash"));
        assert!(detail.contains("Commands:"));
        assert!(detail.contains("- cargo test"));
        assert!(detail.contains("Files:"));
        assert!(detail.contains("- crates/craik-tui-rs/src/app.rs"));
        assert!(detail.contains("Outputs:"));
        assert!(detail.contains("- Implemented provenance detail."));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Run state" && entry.body.contains("thinking"))
        );
    }

    #[test]
    fn multiple_approvals_can_be_selected_and_decided() {
        let first = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_edit_1",
                "message": "Edit first file?",
                "tool": "Edit",
                "target": "src/first.rs"
            }),
        };
        let second = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_bash_2",
                "message": "Run tests?",
                "tool": "Bash",
                "command": "cargo test"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&first);
        app.record_event(&second);

        assert_eq!(app.pending_approval_count(), 2);
        assert_eq!(app.latest_pending_approval(), Some("approval_bash_2"));
        assert_eq!(
            app.selected_approval_summary().as_deref(),
            Some("2/2 pending - approval_bash_2 -> cargo test")
        );

        app.select_previous_approval();

        assert_eq!(app.latest_pending_approval(), Some("approval_edit_1"));
        assert_eq!(
            app.selected_approval_summary().as_deref(),
            Some("1/2 pending - approval_edit_1 -> src/first.rs")
        );

        app.deny_selected();

        let entry = app.transcript.last().expect("decision transcript entry");
        assert_eq!(entry.title, "Denying");
        assert!(entry.body.contains("ID: approval_edit_1"));
        assert!(entry.body.contains("Target: src/first.rs"));
    }

    #[test]
    fn approval_resolution_removes_selected_item_and_keeps_next_pending_selected() {
        let first = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_one",
                "message": "Edit one?",
                "tool": "Edit",
                "target": "one.rs"
            }),
        };
        let second = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_two",
                "message": "Edit two?",
                "tool": "Edit",
                "target": "two.rs"
            }),
        };
        let resolved = GatewayEvent {
            event_type: "approval.resolved".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_two",
                "decision": "approved",
                "operator": "user:ratatui"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&first);
        app.record_event(&second);
        app.record_event(&resolved);

        assert_eq!(app.pending_approval_count(), 1);
        assert_eq!(app.latest_pending_approval(), Some("approval_one"));
        assert_eq!(
            app.selected_approval_summary().as_deref(),
            Some("1/1 pending - approval_one -> one.rs")
        );
    }

    #[test]
    fn approval_resolution_clears_pending_state_and_shows_decision() {
        let requested = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_cmd_456",
                "message": "Run cargo test?"
            }),
        };
        let resolved = GatewayEvent {
            event_type: "approval.resolved".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_cmd_456",
                "decision": "approved",
                "operator": "user:ratatui"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&requested);
        app.record_event(&resolved);

        assert_eq!(app.pending_approval_count(), 0);
        assert_eq!(app.latest_pending_approval(), None);
        let entry = app.transcript.last().expect("approval transcript entry");
        assert_eq!(entry.title, "Approval approved");
        assert!(entry.body.contains("ID: approval_cmd_456"));
        assert!(entry.body.contains("Decision: approved"));
        assert!(entry.body.contains("Operator: user:ratatui"));
    }

    #[test]
    fn tool_events_surface_command_target_and_detail() {
        let event = GatewayEvent {
            event_type: "tool.used".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "tool": "Bash",
                "provider_id": "provider_anthropic",
                "provider_family": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "response_id": "response_123",
                "command": "cargo test",
                "target": "crates/craik-tui-rs",
                "message": "Command completed successfully."
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&event);

        let entry = app.transcript.last().expect("tool transcript entry");
        assert_eq!(entry.title, "Bash");
        assert!(entry.body.contains("Tool: Bash"));
        assert!(entry.body.contains("Provider: provider_anthropic"));
        assert!(entry.body.contains("Family: anthropic"));
        assert!(entry.body.contains("Model: claude-sonnet-4-20250514"));
        assert!(entry.body.contains("Response: response_123"));
        assert!(entry.body.contains("Command: cargo test"));
        assert!(entry.body.contains("Target: crates/craik-tui-rs"));
        assert!(
            entry
                .body
                .contains("Detail: Command completed successfully.")
        );
    }

    #[test]
    fn model_and_receipt_events_surface_provider_context() {
        let model = GatewayEvent {
            event_type: "model.selected".to_owned(),
            created_at: None,
            run_id: None,
            task_id: Some("task_1".to_owned()),
            data: json!({
                "display_name": "Anthropic Claude Opus 4.7",
                "model": "claude-opus-4-7",
                "provider_id": "provider_anthropic",
                "provider_family": "anthropic",
                "live_enabled": true
            }),
        };
        let receipt = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({
                "receipt_id": "receipt_run_1_provider",
                "provider_id": "provider_anthropic",
                "provider_family": "anthropic"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&model);
        app.record_event(&receipt);

        let model_entry = app
            .transcript
            .iter()
            .find(|entry| entry.title == "Model selected")
            .expect("model transcript entry");
        assert!(
            model_entry
                .body
                .contains("Display: Anthropic Claude Opus 4.7")
        );
        assert!(model_entry.body.contains("Provider: provider_anthropic"));
        assert!(model_entry.body.contains("Family: anthropic"));
        assert!(model_entry.body.contains("Live: true"));

        let receipt_entry = app.transcript.last().expect("receipt transcript entry");
        assert_eq!(receipt_entry.title, "Receipt created");
        assert!(
            receipt_entry
                .body
                .contains("Receipt: receipt_run_1_provider")
        );
        assert!(receipt_entry.body.contains("Run: run_1"));
        assert!(receipt_entry.body.contains("Task: task_1"));
        assert!(receipt_entry.body.contains("Provider: provider_anthropic"));
    }

    #[test]
    fn session_ready_surfaces_protocol_context() {
        let ready = GatewayEvent {
            event_type: "session.ready".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "transport": "jsonl.stdio",
                "protocol": "craik.tui.gateway",
                "protocol_version": "1"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&ready);

        let entry = app.transcript.last().expect("ready transcript entry");
        assert_eq!(entry.title, "Gateway");
        assert!(entry.body.contains("Transport: jsonl.stdio"));
        assert!(entry.body.contains("Protocol: craik.tui.gateway"));
        assert!(entry.body.contains("Version: 1"));
    }

    #[test]
    fn ctrl_c_exits_when_idle() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        let action = app.handle_key(KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL));

        assert_eq!(action, LoopAction::Exit);
    }

    #[test]
    fn ctrl_c_interrupts_when_request_is_in_flight() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.in_flight = true;

        let action = app.handle_key(KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL));

        assert_eq!(action, LoopAction::Continue);
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Interrupt")
        );
    }

    #[test]
    fn escape_clears_input() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.input = "hello".to_owned();
        app.input_cursor = app.input.len();

        let action = app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));

        assert_eq!(action, LoopAction::Continue);
        assert!(app.input.is_empty());
        assert_eq!(app.input_cursor, 0);
    }

    #[test]
    fn prompt_editor_supports_paste_and_line_editing_controls() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.paste_text("first line\nsecond line");
        assert_eq!(app.input_line_count(), 2);
        assert_eq!(app.input_cursor_line_col(), (2, 12));

        app.handle_key(KeyEvent::new(KeyCode::Char('u'), KeyModifiers::CONTROL));
        assert_eq!(app.input, "first line\n");
        assert_eq!(app.input_cursor_line_col(), (2, 1));

        app.paste_text("second line");

        app.handle_key(KeyEvent::new(KeyCode::Up, KeyModifiers::NONE));
        assert_eq!(app.input_cursor_line_col(), (1, 11));

        app.input = "alpha beta".to_owned();
        app.input_cursor = app.input.len();
        app.handle_key(KeyEvent::new(KeyCode::Char('w'), KeyModifiers::CONTROL));

        assert_eq!(app.input, "alpha ");
        assert_eq!(app.input_cursor, 6);

        app.input = "alpha beta".to_owned();
        app.input_cursor = 6;
        app.handle_key(KeyEvent::new(KeyCode::Char('k'), KeyModifiers::CONTROL));

        assert_eq!(app.input, "alpha ");
        assert_eq!(app.input_cursor, 6);
    }

    #[test]
    fn ctrl_f_enters_search_mode_and_escape_exits_it() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.handle_key(KeyEvent::new(KeyCode::Char('f'), KeyModifiers::CONTROL));
        assert!(app.search_active);
        app.handle_key(KeyEvent::new(KeyCode::Char('r'), KeyModifiers::NONE));
        app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));

        assert!(!app.search_active);
        assert_eq!(app.search_query, "r");
    }

    #[test]
    fn help_overlay_toggles_and_lists_contextual_actions() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.handle_key(KeyEvent::new(KeyCode::Char('?'), KeyModifiers::NONE));

        assert!(app.help_visible);
        let help = app.help_text();
        assert!(help.contains("Craik Rust TUI Commands"));
        assert!(help.contains("Ctrl-Y retry last prompt"));
        assert!(help.contains("Ctrl-T/G/H/Z jump"));

        app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));

        assert!(!app.help_visible);
    }

    #[test]
    fn overlay_keys_open_and_escape_returns_to_chat() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.handle_key(KeyEvent::new(KeyCode::Char('m'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Memory));
        assert!(
            app.overlay_text()
                .expect("memory overlay")
                .contains("Session memory")
        );

        app.handle_key(KeyEvent::new(KeyCode::Char('e'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Evidence));
        assert!(
            app.overlay_text()
                .expect("evidence overlay")
                .contains("Evidence")
        );

        app.handle_key(KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Runs));
        assert!(app.overlay_text().expect("runs overlay").contains("Runs"));

        app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
        assert_eq!(app.active_overlay, None);
    }

    #[test]
    fn approval_overlay_requires_review_before_approval_key_decides() {
        let event = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_edit_1",
                "message": "Edit src/lib.rs?",
                "tool": "Edit",
                "target": "src/lib.rs"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&event);

        app.handle_key(KeyEvent::new(KeyCode::Char('x'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
        assert!(!app.transcript.iter().any(|entry| entry.title == "Denying"));
        app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
        assert_eq!(app.active_overlay, None);

        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving")
        );
        assert!(
            app.overlay_text()
                .expect("approval overlay")
                .contains("approval_edit_1")
        );

        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::CONTROL));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approving")
        );
    }

    #[test]
    fn tab_completes_visible_slash_command() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.slash_catalog = vec![SlashHint::new(
            "run",
            "/run <prompt>",
            "Run an audited prompt.",
            "Run",
        )];
        app.input = "/r".to_owned();
        app.input_cursor = app.input.len();

        app.handle_key(KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));

        assert_eq!(app.input, "/run ");
        assert_eq!(app.input_cursor, app.input.len());
    }

    #[test]
    fn search_navigation_tracks_current_match() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.transcript = vec![
            crate::transcript::TranscriptEntry::system("First", "alpha"),
            crate::transcript::TranscriptEntry::assistant("Second", "beta"),
            crate::transcript::TranscriptEntry::progress("Third", "alpha"),
        ];
        app.search_query = "alpha".to_owned();

        app.next_search_match();
        assert_eq!(app.search_match_index, Some(0));
        let first_scroll = app.transcript_scroll;

        app.next_search_match();
        assert_eq!(app.search_match_index, Some(1));
        assert!(app.transcript_scroll < first_scroll);

        app.previous_search_match();
        assert_eq!(app.search_match_index, Some(0));
        assert_eq!(app.transcript_scroll, first_scroll);
    }

    #[test]
    fn transcript_jump_moves_to_evidence_entries() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.transcript = vec![
            crate::transcript::TranscriptEntry::assistant("Answer", "done"),
            crate::transcript::TranscriptEntry::new(
                crate::transcript::TranscriptKind::Tool,
                "Read",
                "Path: README.md",
            ),
            crate::transcript::TranscriptEntry::new(
                crate::transcript::TranscriptKind::Approval,
                "Approval pending",
                "ID: approval_1",
            ),
            crate::transcript::TranscriptEntry::new(
                crate::transcript::TranscriptKind::Receipt,
                "Receipt created",
                "Receipt: receipt_1",
            ),
        ];

        app.jump_to_next_transcript_kind(super::TranscriptJump::Approval);

        assert_eq!(app.transcript_jump, Some(super::TranscriptJump::Approval));
        assert_eq!(
            app.transcript_jump_summary().as_deref(),
            Some("approval: 1 entries")
        );
        assert!(app.transcript_scroll > 0);
    }

    #[test]
    fn selected_run_export_formats_handoff_markdown() {
        let run = RunRecord {
            run_id: "run/unsafe id".to_owned(),
            task_id: Some("task_1".to_owned()),
            prompt: Some("Review the implementation plan".to_owned()),
            model: Some("claude-opus-4-7".to_owned()),
            provider: Some("anthropic".to_owned()),
            status: Some("completed".to_owned()),
            receipts: vec!["receipt_1".to_owned()],
            receipt_details: vec!["capability=shell.execute status=completed".to_owned()],
            tools: vec!["Bash".to_owned()],
            files: vec!["crates/craik-tui-rs/src/app.rs".to_owned()],
            commands: vec!["cargo test".to_owned()],
            approvals: vec!["approval_1 approved".to_owned()],
            outputs: vec!["Implementation plan reviewed.".to_owned()],
            provenance: vec!["Tool used: Bash".to_owned()],
        };

        let markdown = run.export_markdown();

        assert!(markdown.contains("# Craik Run Handoff: run/unsafe id"));
        assert!(markdown.contains("- Status: completed"));
        assert!(markdown.contains("- Task: task_1"));
        assert!(markdown.contains("- Provider: anthropic"));
        assert!(markdown.contains("- Model: claude-opus-4-7"));
        assert!(markdown.contains("## Receipts"));
        assert!(markdown.contains("- receipt_1"));
        assert!(markdown.contains("## Commands"));
        assert!(markdown.contains("- cargo test"));
        assert!(markdown.contains("## Files"));
        assert!(markdown.contains("- crates/craik-tui-rs/src/app.rs"));
        assert!(markdown.contains("## Provenance"));
        assert_eq!(export_file_stem("run/unsafe id"), "run_unsafe_id");
        assert_eq!(export_file_stem(""), "run");
    }

    #[test]
    fn export_without_selected_run_is_visible() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.export_selected_run();

        let entry = app.transcript.last().expect("export transcript entry");
        assert_eq!(entry.title, "Export");
        assert!(entry.body.contains("No selected run"));
    }

    #[test]
    fn shutdown_surfaces_session_close_status() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.backend_connected = true;
        app.in_flight = true;
        app.state.working_phase = Some("waiting".to_owned());

        app.shutdown();

        assert!(!app.backend_connected);
        assert!(!app.in_flight);
        assert_eq!(app.state.working_phase, None);
        let entry = app.transcript.last().expect("shutdown transcript entry");
        assert_eq!(entry.title, "Session closing");
        assert!(entry.body.contains("Gateway session close requested"));
    }

    #[test]
    fn ctrl_r_opens_runs_overlay() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.handle_key(KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL));

        assert_eq!(app.active_overlay, Some(ActiveOverlay::Runs));
    }

    #[test]
    fn incoming_transcript_events_do_not_reset_scrolled_back_view() {
        let event = GatewayEvent {
            event_type: "run.progress".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({"message": "still working"}),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.transcript_scroll = 12;

        app.record_event(&event);

        assert_eq!(app.transcript_scroll, 12);
    }

    fn event(
        event_type: &str,
        run_id: Option<&str>,
        task_id: Option<&str>,
        data: serde_json::Value,
    ) -> GatewayEvent {
        GatewayEvent {
            event_type: event_type.to_owned(),
            created_at: None,
            run_id: run_id.map(str::to_owned),
            task_id: task_id.map(str::to_owned),
            data,
        }
    }
}
