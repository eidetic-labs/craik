use crate::{
    backend::{BackendSession, WorkerMessage},
    gateway_events::{is_request_terminal_event, slash_hints_from_event, summarize_slash_output},
    input::SlashHint,
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

pub(crate) struct InteractiveApp {
    pub(crate) state: GatewayAppState,
    pub(crate) input: String,
    pub(crate) input_cursor: usize,
    pub(crate) transcript: Vec<TranscriptEntry>,
    pub(crate) transcript_scroll: u16,
    backend: BackendSession,
    pub(crate) in_flight: bool,
    pub(crate) last_error: Option<String>,
    pending_approvals: Vec<String>,
    pub(crate) slash_catalog: Vec<SlashHint>,
    history: Vec<String>,
    history_index: Option<usize>,
    pub(crate) queued_inputs: VecDeque<String>,
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
            backend,
            in_flight: false,
            last_error: None,
            pending_approvals: Vec::new(),
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
        };
        app.send_commands([GatewayCommand::SessionStatus, GatewayCommand::SlashCatalog]);
        Ok(app)
    }

    #[cfg(test)]
    fn for_test_with_messages(messages: impl IntoIterator<Item = WorkerMessage>) -> Self {
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
            backend: BackendSession::for_test(receiver),
            in_flight: false,
            last_error: None,
            pending_approvals: Vec::new(),
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
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

    pub(crate) fn handle_key(&mut self, key: KeyEvent) -> LoopAction {
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
                self.approve_latest();
                LoopAction::Continue
            }
            KeyCode::Char('x') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.deny_latest();
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
                self.move_cursor_home();
                LoopAction::Continue
            }
            KeyCode::End => {
                self.move_cursor_end();
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

    fn record_event(&mut self, event: &GatewayEvent) {
        match event.event_type.as_str() {
            "session.ready" => {
                self.transcript
                    .push(TranscriptEntry::system("Gateway", "Session ready."));
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
                self.transcript
                    .push(TranscriptEntry::progress("Submitted", preview));
            }
            "model.selected" | "model.changed" => {
                let model = event
                    .data
                    .get("model")
                    .and_then(|value| value.as_str())
                    .unwrap_or("model selected");
                self.transcript
                    .push(TranscriptEntry::system("Model", model));
            }
            "run.started" => {
                let run_id = event.run_id.as_deref().unwrap_or("run");
                self.transcript
                    .push(TranscriptEntry::progress("Run started", run_id));
            }
            "run.progress" => {
                if let Some(message) = event.data.get("message").and_then(|value| value.as_str()) {
                    self.transcript
                        .push(TranscriptEntry::progress("Progress", message));
                    self.transcript_scroll = 0;
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
                    self.transcript
                        .push(TranscriptEntry::new(kind, tool, message));
                    self.transcript_scroll = 0;
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
                self.transcript
                    .push(TranscriptEntry::new(TranscriptKind::File, target, text));
                self.transcript_scroll = 0;
            }
            "approval.requested" => {
                let approval_id = event
                    .data
                    .get("approval_id")
                    .and_then(|value| value.as_str())
                    .unwrap_or_default();
                if !approval_id.is_empty()
                    && !self
                        .pending_approvals
                        .iter()
                        .any(|candidate| candidate == approval_id)
                {
                    self.pending_approvals.push(approval_id.to_owned());
                }
                let message = event
                    .data
                    .get("message")
                    .and_then(|value| value.as_str())
                    .unwrap_or("Approval requested.");
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::Approval,
                    "Approval requested",
                    message,
                ));
                self.transcript_scroll = 0;
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
                self.pending_approvals
                    .retain(|candidate| candidate != approval_id);
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::Approval,
                    "Approval resolved",
                    &format!("{approval_id}: {decision}"),
                ));
            }
            "receipt.created" => {
                if let Some(receipt_id) = event
                    .data
                    .get("receipt_id")
                    .and_then(|value| value.as_str())
                {
                    self.transcript.push(TranscriptEntry::new(
                        TranscriptKind::Receipt,
                        "Receipt",
                        receipt_id,
                    ));
                }
            }
            "run.output" => {
                if let Some(summary) = event.data.get("summary").and_then(|value| value.as_str()) {
                    self.transcript
                        .push(TranscriptEntry::assistant("Assistant", summary));
                    self.transcript_scroll = 0;
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
                    self.transcript_scroll = 0;
                }
            }
            "run.completed" => {
                let status = event
                    .data
                    .get("status")
                    .and_then(|value| value.as_str())
                    .unwrap_or("completed");
                self.transcript
                    .push(TranscriptEntry::progress("Run completed", status));
                if status == "completed" && self.state.outputs.is_empty() {
                    self.transcript.push(TranscriptEntry::system(
                        "No model output",
                        "The Gateway reported completion before any assistant output event arrived.",
                    ));
                }
                self.transcript_scroll = 0;
            }
            "slash.completed" => {
                let text = summarize_slash_output(event)
                    .unwrap_or_else(|| "Slash command completed.".to_owned());
                self.transcript
                    .push(TranscriptEntry::system("Slash command", &text));
                self.transcript_scroll = 0;
            }
            "error" => {
                if let Some(message) = event.data.get("message").and_then(|value| value.as_str()) {
                    self.transcript
                        .push(TranscriptEntry::error("Gateway error", message));
                    self.transcript_scroll = 0;
                }
            }
            _ => {}
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

    pub(crate) fn clear_input(&mut self) {
        self.input.clear();
        self.input_cursor = 0;
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

    pub(crate) fn approve_latest(&mut self) {
        let Some(approval_id) = self.pending_approvals.last().cloned() else {
            self.transcript.push(TranscriptEntry::system(
                "Approval",
                "No pending approval with an id is available.",
            ));
            return;
        };
        self.transcript.push(TranscriptEntry::new(
            TranscriptKind::Approval,
            "Approving",
            &approval_id,
        ));
        self.send_commands([GatewayCommand::ApprovalDecide {
            approval_id,
            decision: "approved".to_owned(),
            operator: "user:ratatui".to_owned(),
            reason: "approved from Ratatui client".to_owned(),
        }]);
    }

    pub(crate) fn deny_latest(&mut self) {
        let Some(approval_id) = self.pending_approvals.last().cloned() else {
            self.transcript.push(TranscriptEntry::system(
                "Approval",
                "No pending approval with an id is available.",
            ));
            return;
        };
        self.transcript.push(TranscriptEntry::new(
            TranscriptKind::Approval,
            "Denying",
            &approval_id,
        ));
        self.send_commands([GatewayCommand::ApprovalDecide {
            approval_id,
            decision: "denied".to_owned(),
            operator: "user:ratatui".to_owned(),
            reason: "denied from Ratatui client".to_owned(),
        }]);
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

#[cfg(test)]
mod tests {
    use super::{InteractiveApp, LoopAction};
    use crate::backend::WorkerMessage;
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
}
