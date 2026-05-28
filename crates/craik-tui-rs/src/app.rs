use crate::{
    backend::{BackendSession, WorkerMessage},
    gateway_events::{is_request_terminal_event, slash_hints_from_event, summarize_slash_output},
    input::{SlashHint, slash_completion},
    transcript::{TranscriptEntry, TranscriptKind},
};
use craik_tui_rs::{GatewayAppState, GatewayCommand, GatewayEvent};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use std::collections::VecDeque;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum LoopAction {
    Continue,
    Exit,
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
    pub(crate) tools: Vec<String>,
    pub(crate) files: Vec<String>,
    pub(crate) commands: Vec<String>,
    pub(crate) approvals: Vec<String>,
    pub(crate) outputs: Vec<String>,
}

pub(crate) struct InteractiveApp {
    pub(crate) state: GatewayAppState,
    pub(crate) input: String,
    pub(crate) input_cursor: usize,
    pub(crate) transcript: Vec<TranscriptEntry>,
    pub(crate) transcript_scroll: u16,
    pub(crate) transcript_focused: bool,
    pub(crate) expand_transcript_details: bool,
    pub(crate) search_active: bool,
    pub(crate) search_query: String,
    pub(crate) search_match_index: Option<usize>,
    backend: BackendSession,
    pub(crate) in_flight: bool,
    pub(crate) last_error: Option<String>,
    pending_approvals: Vec<PendingApproval>,
    selected_approval_index: Option<usize>,
    pub(crate) slash_catalog: Vec<SlashHint>,
    history: Vec<String>,
    history_index: Option<usize>,
    pub(crate) queued_inputs: VecDeque<String>,
    pub(crate) run_records: Vec<RunRecord>,
    pub(crate) selected_run_index: Option<usize>,
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
            search_active: false,
            search_query: String::new(),
            search_match_index: None,
            backend,
            in_flight: false,
            last_error: None,
            pending_approvals: Vec::new(),
            selected_approval_index: None,
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
            run_records: Vec::new(),
            selected_run_index: None,
            last_prompt_preview: None,
        };
        app.send_commands([GatewayCommand::SessionStatus, GatewayCommand::SlashCatalog]);
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
            search_active: false,
            search_query: String::new(),
            search_match_index: None,
            backend: BackendSession::for_test(receiver),
            in_flight: false,
            last_error: None,
            pending_approvals: Vec::new(),
            selected_approval_index: None,
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
            run_records: Vec::new(),
            selected_run_index: None,
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

    pub(crate) fn drain_worker(&mut self) {
        while let Ok(message) = self.backend.receiver.try_recv() {
            match message {
                WorkerMessage::Event(event) => {
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
                }
                WorkerMessage::Closed(message) => {
                    self.last_error = Some(message.clone());
                    self.transcript
                        .push(TranscriptEntry::error("Gateway disconnected", &message));
                    self.in_flight = false;
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
        let position = self.selected_run_index.unwrap_or_default() + 1;
        let total = self.run_records.len();
        let status = run.status.as_deref().unwrap_or("active");
        Some(format!("{position}/{total} {} [{status}]", run.run_id))
    }

    pub(crate) fn selected_run_detail(&self) -> Option<String> {
        self.selected_run().map(RunRecord::detail_text)
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
        if self.search_active {
            return self.handle_search_key(key);
        }
        match key.code {
            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                if self.in_flight {
                    self.request_interrupt();
                    LoopAction::Continue
                } else {
                    LoopAction::Exit
                }
            }
            KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => LoopAction::Exit,
            KeyCode::Char('a') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.approve_selected();
                LoopAction::Continue
            }
            KeyCode::Char('x') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.deny_selected();
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
            KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.transcript_focused = !self.transcript_focused;
                LoopAction::Continue
            }
            KeyCode::Char('e') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.expand_transcript_details = !self.expand_transcript_details;
                self.transcript_scroll = 0;
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
                self.history_previous();
                LoopAction::Continue
            }
            KeyCode::Down => {
                self.history_next();
                LoopAction::Continue
            }
            KeyCode::Char(ch) if !key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.insert_char(ch);
                LoopAction::Continue
            }
            _ => LoopAction::Continue,
        }
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
                if let Some(message) = event.data.get("message").and_then(|value| value.as_str()) {
                    self.transcript
                        .push(TranscriptEntry::error("Gateway error", message));
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
        self.selected_run_index = Some(index);
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
            }
            "run.completed" => {
                run.status = string_data(event, "status").or_else(|| Some("completed".to_owned()));
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
            }
            "file.changed" => {
                if let Some(target) = string_data(event, "target") {
                    push_unique_string(&mut run.files, target);
                }
            }
            "approval.requested" => {
                if let Some(message) = string_data(event, "message") {
                    push_unique_string(&mut run.approvals, message);
                }
            }
            "receipt.created" => {
                if let Some(receipt_id) = string_data(event, "receipt_id") {
                    push_unique_string(&mut run.receipts, receipt_id);
                }
            }
            "run.output" => {
                if let Some(summary) = string_data(event, "summary") {
                    run.outputs.push(summary);
                }
            }
            _ => {}
        }
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

    pub(crate) fn insert_char(&mut self, ch: char) {
        self.input.insert(self.input_cursor, ch);
        self.input_cursor += ch.len_utf8();
    }

    pub(crate) fn insert_newline(&mut self) {
        self.input.insert(self.input_cursor, '\n');
        self.input_cursor += 1;
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

    fn dispatch_next_queued(&mut self) {
        if self.in_flight {
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
        if self.run_records.is_empty() {
            self.selected_run_index = None;
            return;
        }
        let next = self
            .selected_run_index
            .map(|index| (index + 1) % self.run_records.len())
            .unwrap_or(0);
        self.selected_run_index = Some(next);
        self.transcript.push(TranscriptEntry::system(
            "Run selected",
            &self.selected_run_detail().unwrap_or_default(),
        ));
    }

    pub(crate) fn select_previous_run(&mut self) {
        if self.run_records.is_empty() {
            self.selected_run_index = None;
            return;
        }
        let previous = self
            .selected_run_index
            .map(|index| {
                if index == 0 {
                    self.run_records.len() - 1
                } else {
                    index - 1
                }
            })
            .unwrap_or_else(|| self.run_records.len() - 1);
        self.selected_run_index = Some(previous);
        self.transcript.push(TranscriptEntry::system(
            "Run selected",
            &self.selected_run_detail().unwrap_or_default(),
        ));
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
        if let Some(output) = self.outputs.last() {
            lines.push(format!("Latest output: {}", compact_text(output, 96)));
        }
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

fn push_count_line(lines: &mut Vec<String>, label: &str, values: &[String]) {
    let suffix = values
        .last()
        .map(|value| format!(" latest {}", compact_text(value, 48)))
        .unwrap_or_default();
    lines.push(format!("{label}: {}{suffix}", values.len()));
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

#[cfg(test)]
mod tests {
    use super::{InteractiveApp, LoopAction};
    use crate::backend::WorkerMessage;
    use crate::input::SlashHint;
    use craik_tui_rs::GatewayEvent;
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
    use serde_json::json;

    #[test]
    fn backend_close_unblocks_working_state() {
        let mut app = InteractiveApp::for_test_with_messages([WorkerMessage::Closed(
            "Gateway output stream closed.".to_owned(),
        )]);
        app.in_flight = true;
        app.state.working_phase = Some("waiting".to_owned());

        app.drain_worker();

        assert!(!app.in_flight);
        assert_eq!(app.state.working_phase, None);
        assert_eq!(
            app.last_error.as_deref(),
            Some("Gateway output stream closed.")
        );
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Gateway disconnected")
        );
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
            Some("2/2 run_2 [running]")
        );

        app.select_previous_run();

        assert_eq!(
            app.selected_run_summary().as_deref(),
            Some("1/2 run_1 [running]")
        );
        let detail = app.selected_run_detail().expect("run detail");
        assert!(detail.contains("Provider: provider_anthropic"));
        assert!(detail.contains("Tools: 1 latest Bash"));
        assert!(detail.contains("Commands: 1 latest cargo test"));
        assert!(detail.contains("Receipts: 1 latest receipt_run_1"));
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
    fn tab_completes_visible_slash_command() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.slash_catalog = vec![SlashHint {
            name: "run".to_owned(),
            usage: "/run <prompt>".to_owned(),
            summary: "Run an audited prompt.".to_owned(),
            category: "Run".to_owned(),
        }];
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
    fn ctrl_r_toggles_transcript_focus() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.handle_key(KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL));

        assert!(app.transcript_focused);
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
}
