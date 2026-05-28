use anyhow::{Context, bail};
use craik_tui_rs::{
    GatewayAppState, GatewayCommand, GatewayEvent, app_state_from_events,
    approval_command_sequence, encode_gateway_command, interrupt_command_sequence,
    model_command_sequence, parse_gateway_events, prompt_command_sequence, render_dashboard_text,
    render_replay_text, run_backend_commands, slash_command_sequence, status_command_sequence,
    summarize_gateway_events,
};
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{
    Terminal,
    backend::{CrosstermBackend, TestBackend},
    layout::{Constraint, Direction, Layout, Position, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
};
use std::{
    collections::VecDeque,
    env, fs,
    io::{self, BufRead, IsTerminal, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{
        Arc, Mutex,
        mpsc::{self, Receiver},
    },
    thread,
    time::Duration,
};

fn main() -> anyhow::Result<()> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args.is_empty() && io::stdin().is_terminal() {
        return run_interactive_app();
    }

    let rendered = match args.first().map(String::as_str) {
        Some("--status") => {
            let events = run_backend_commands(&status_command_sequence())?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--submit") => {
            let text = args
                .get(1)
                .context("--submit requires prompt text")?
                .to_owned();
            let events = run_backend_commands(&prompt_command_sequence(text))?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--slash") => {
            let text = args
                .get(1)
                .context("--slash requires slash command text")?
                .to_owned();
            let events = run_backend_commands(&slash_command_sequence(text))?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--model") => {
            let model = args
                .get(1)
                .context("--model requires provider/model")?
                .to_owned();
            let events = run_backend_commands(&model_command_sequence(model, None, None))?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--approve") => {
            let approval_id = args
                .get(1)
                .context("--approve requires approval id")?
                .to_owned();
            let reason = args
                .get(2)
                .cloned()
                .unwrap_or_else(|| "approved from Ratatui client".to_owned());
            let events = run_backend_commands(&approval_command_sequence(
                approval_id,
                "approved".to_owned(),
                "user:ratatui".to_owned(),
                reason,
            ))?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--deny") => {
            let approval_id = args
                .get(1)
                .context("--deny requires approval id")?
                .to_owned();
            let reason = args
                .get(2)
                .cloned()
                .unwrap_or_else(|| "denied from Ratatui client".to_owned());
            let events = run_backend_commands(&approval_command_sequence(
                approval_id,
                "denied".to_owned(),
                "user:ratatui".to_owned(),
                reason,
            ))?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--interrupt") => {
            let run_id = args
                .get(1)
                .context("--interrupt requires run id")?
                .to_owned();
            let reason = args
                .get(2)
                .cloned()
                .unwrap_or_else(|| "operator requested stop".to_owned());
            let events = run_backend_commands(&interrupt_command_sequence(run_id, reason))?;
            render_dashboard_text(&app_state_from_events(&events))
        }
        Some("--help") | Some("-h") => usage(),
        Some(path) => render_replay(path)?,
        None => {
            let input = io::read_to_string(io::stdin()).context("failed to read stdin")?;
            render_events(&input)?
        }
    };

    let backend = TestBackend::new(96, 12);
    let mut terminal = Terminal::new(backend)?;
    terminal.draw(|frame| {
        frame.render_widget(
            Paragraph::new(rendered.clone()).block(
                Block::default()
                    .title("Craik Gateway")
                    .borders(Borders::ALL),
            ),
            frame.area(),
        );
    })?;

    println!("{rendered}");
    Ok(())
}

struct InteractiveApp {
    state: GatewayAppState,
    input: String,
    input_cursor: usize,
    transcript: Vec<TranscriptEntry>,
    transcript_scroll: u16,
    backend: BackendSession,
    in_flight: bool,
    last_error: Option<String>,
    pending_approvals: Vec<String>,
    slash_catalog: Vec<SlashHint>,
    history: Vec<String>,
    history_index: Option<usize>,
    queued_inputs: VecDeque<String>,
}

enum WorkerMessage {
    Event(GatewayEvent),
    Error(String),
}

struct BackendSession {
    stdin: Option<Arc<Mutex<ChildStdin>>>,
    receiver: Receiver<WorkerMessage>,
    child: Option<Child>,
}

struct TranscriptEntry {
    kind: TranscriptKind,
    title: String,
    body: String,
}

enum TranscriptKind {
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

struct SlashHint {
    name: String,
    usage: String,
    summary: String,
}

impl InteractiveApp {
    fn new() -> anyhow::Result<Self> {
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
    fn for_test() -> Self {
        let (_stdin_sender, stdin_receiver) = mpsc::channel();
        Self {
            state: GatewayAppState::default(),
            input: String::new(),
            input_cursor: 0,
            transcript: Vec::new(),
            transcript_scroll: 0,
            backend: BackendSession::for_test(stdin_receiver),
            in_flight: false,
            last_error: None,
            pending_approvals: Vec::new(),
            slash_catalog: Vec::new(),
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
        }
    }

    fn submit_input(&mut self) {
        let text = self.input.trim().to_owned();
        if text.is_empty() {
            return;
        }
        if matches!(text.as_str(), "/stop" | "/interrupt") {
            self.input.clear();
            self.input_cursor = 0;
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
            self.input.clear();
            self.input_cursor = 0;
            return;
        }
        self.dispatch_text(text);
        self.input.clear();
        self.input_cursor = 0;
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

    fn drain_worker(&mut self) {
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
            }
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

    fn insert_char(&mut self, ch: char) {
        self.input.insert(self.input_cursor, ch);
        self.input_cursor += ch.len_utf8();
    }

    fn insert_newline(&mut self) {
        self.input.insert(self.input_cursor, '\n');
        self.input_cursor += 1;
    }

    fn backspace(&mut self) {
        if self.input_cursor == 0 {
            return;
        }
        if let Some((index, _)) = self.input[..self.input_cursor].char_indices().last() {
            self.input.replace_range(index..self.input_cursor, "");
            self.input_cursor = index;
        }
    }

    fn delete(&mut self) {
        if self.input_cursor >= self.input.len() {
            return;
        }
        if let Some(ch) = self.input[self.input_cursor..].chars().next() {
            let next = self.input_cursor + ch.len_utf8();
            self.input.replace_range(self.input_cursor..next, "");
        }
    }

    fn move_cursor_left(&mut self) {
        if self.input_cursor == 0 {
            return;
        }
        if let Some((index, _)) = self.input[..self.input_cursor].char_indices().last() {
            self.input_cursor = index;
        }
    }

    fn move_cursor_right(&mut self) {
        if self.input_cursor >= self.input.len() {
            return;
        }
        if let Some(ch) = self.input[self.input_cursor..].chars().next() {
            self.input_cursor += ch.len_utf8();
        }
    }

    fn move_cursor_home(&mut self) {
        let line_start = self.input[..self.input_cursor]
            .rfind('\n')
            .map(|index| index + 1)
            .unwrap_or(0);
        self.input_cursor = line_start;
    }

    fn move_cursor_end(&mut self) {
        let line_end = self.input[self.input_cursor..]
            .find('\n')
            .map(|index| self.input_cursor + index)
            .unwrap_or(self.input.len());
        self.input_cursor = line_end;
    }

    fn scroll_transcript_up(&mut self) {
        self.transcript_scroll = self.transcript_scroll.saturating_add(4);
    }

    fn scroll_transcript_down(&mut self) {
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

    fn request_interrupt(&mut self) {
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

    fn approve_latest(&mut self) {
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

    fn deny_latest(&mut self) {
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

    fn history_previous(&mut self) {
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

    fn history_next(&mut self) {
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

impl BackendSession {
    fn start() -> anyhow::Result<Self> {
        let mut child = Command::new("uv")
            .args(["run", "craik", "tui-backend", "--jsonl"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .context("failed to start `uv run craik tui-backend --jsonl`")?;
        let stdin = Arc::new(Mutex::new(
            child
                .stdin
                .take()
                .context("backend stdin was not captured")?,
        ));
        let stdout = child
            .stdout
            .take()
            .context("backend stdout was not captured")?;
        let stderr = child
            .stderr
            .take()
            .context("backend stderr was not captured")?;
        let (sender, receiver) = mpsc::channel();
        let event_sender = sender.clone();
        thread::spawn(move || {
            let reader = io::BufReader::new(stdout);
            for line in reader.lines() {
                match line {
                    Ok(line) if line.trim().is_empty() => {}
                    Ok(line) => match serde_json::from_str::<GatewayEvent>(&line) {
                        Ok(event) => {
                            let _ = event_sender.send(WorkerMessage::Event(event));
                        }
                        Err(error) => {
                            let _ = event_sender.send(WorkerMessage::Error(format!(
                                "failed to parse backend event: {error}: {line}"
                            )));
                        }
                    },
                    Err(error) => {
                        let _ = event_sender.send(WorkerMessage::Error(format!(
                            "backend read failed: {error}"
                        )));
                        break;
                    }
                }
            }
        });
        thread::spawn(move || {
            let reader = io::BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                if !line.trim().is_empty() {
                    let _ = sender.send(WorkerMessage::Error(line));
                }
            }
        });
        Ok(Self {
            stdin: Some(stdin),
            receiver,
            child: Some(child),
        })
    }

    #[cfg(test)]
    fn for_test(receiver: Receiver<WorkerMessage>) -> Self {
        Self {
            stdin: None,
            receiver,
            child: None,
        }
    }

    fn send(&self, command: &GatewayCommand) -> anyhow::Result<()> {
        let Some(stdin) = &self.stdin else {
            return Ok(());
        };
        let mut stdin = stdin
            .lock()
            .map_err(|_| anyhow::anyhow!("backend stdin lock poisoned"))?;
        stdin.write_all(encode_gateway_command(command)?.as_bytes())?;
        stdin.write_all(b"\n")?;
        stdin.flush()?;
        Ok(())
    }
}

impl Drop for BackendSession {
    fn drop(&mut self) {
        let _ = self.send(&GatewayCommand::SessionClose);
        if let Some(child) = &mut self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl TranscriptEntry {
    fn new(kind: TranscriptKind, title: &str, body: &str) -> Self {
        Self {
            kind,
            title: title.to_owned(),
            body: body.to_owned(),
        }
    }

    fn system(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::System, title, body)
    }

    fn user(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::User, title, body)
    }

    fn assistant(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::Assistant, title, body)
    }

    fn progress(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::Progress, title, body)
    }

    fn error(title: &str, body: &str) -> Self {
        Self::new(TranscriptKind::Error, title, body)
    }
}

fn run_interactive_app() -> anyhow::Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    let result = run_interactive_loop(&mut terminal);
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    result
}

fn run_interactive_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
) -> anyhow::Result<()> {
    let mut app = InteractiveApp::new()?;
    loop {
        app.drain_worker();
        terminal.draw(|frame| {
            let area = frame.area();
            let vertical = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Min(8),
                    Constraint::Length(4),
                    Constraint::Length(1),
                ])
                .split(area);
            let body = Layout::default()
                .direction(Direction::Horizontal)
                .constraints([Constraint::Percentage(68), Constraint::Percentage(32)])
                .split(vertical[0]);

            let transcript_height = body[0].height.saturating_sub(2);
            let transcript = Paragraph::new(render_transcript_lines(&app.transcript))
                .block(Block::default().title("Transcript").borders(Borders::ALL))
                .scroll((transcript_scroll_offset(&app, transcript_height), 0))
                .wrap(Wrap { trim: false });
            frame.render_widget(transcript, body[0]);

            let activity = Paragraph::new(render_activity_panel(&app))
                .block(Block::default().title("Activity").borders(Borders::ALL))
                .wrap(Wrap { trim: false });
            frame.render_widget(activity, body[1]);

            let input_block = Block::default()
                .title(Line::from(vec![Span::styled(
                    "Prompt",
                    Style::default().add_modifier(Modifier::BOLD),
                )]))
                .borders(Borders::ALL);
            let input_inner = input_block.inner(vertical[1]);
            let input = Paragraph::new(render_input_lines(&app))
                .block(input_block)
                .wrap(Wrap { trim: false });
            frame.render_widget(input, vertical[1]);
            frame.set_cursor_position(input_cursor_position(&app, input_inner));

            let footer = Paragraph::new(status_line(&app));
            frame.render_widget(footer, vertical[2]);
        })?;

        if event::poll(Duration::from_millis(80))?
            && let Event::Key(key) = event::read()?
        {
            if key.kind != KeyEventKind::Press {
                continue;
            }
            match key.code {
                KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if app.in_flight {
                        app.request_interrupt();
                    } else {
                        break;
                    }
                }
                KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => break,
                KeyCode::Char('a') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    app.approve_latest();
                }
                KeyCode::Char('x') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    app.deny_latest();
                }
                KeyCode::Enter if key.modifiers.contains(KeyModifiers::ALT) => app.insert_newline(),
                KeyCode::Enter => app.submit_input(),
                KeyCode::Backspace => {
                    app.backspace();
                }
                KeyCode::Delete => {
                    app.delete();
                }
                KeyCode::Esc => {
                    app.input.clear();
                    app.input_cursor = 0;
                }
                KeyCode::Left => {
                    app.move_cursor_left();
                }
                KeyCode::Right => {
                    app.move_cursor_right();
                }
                KeyCode::Home => {
                    app.move_cursor_home();
                }
                KeyCode::End => {
                    app.move_cursor_end();
                }
                KeyCode::PageUp => {
                    app.scroll_transcript_up();
                }
                KeyCode::PageDown => {
                    app.scroll_transcript_down();
                }
                KeyCode::Up => {
                    app.history_previous();
                }
                KeyCode::Down => {
                    app.history_next();
                }
                KeyCode::Char(ch) => {
                    if !key.modifiers.contains(KeyModifiers::CONTROL) {
                        app.insert_char(ch);
                    }
                }
                _ => {}
            }
        }
    }
    Ok(())
}

fn transcript_scroll_offset(app: &InteractiveApp, visible_height: u16) -> u16 {
    let line_count = app
        .transcript
        .iter()
        .map(|entry| entry.body.lines().count().max(1) as u16 + 1)
        .sum::<u16>();
    line_count
        .saturating_sub(visible_height)
        .saturating_sub(app.transcript_scroll)
}

fn render_transcript_lines(entries: &[TranscriptEntry]) -> Vec<Line<'static>> {
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

fn render_input_lines(app: &InteractiveApp) -> Vec<Line<'static>> {
    let mut lines = app
        .input
        .lines()
        .map(|line| Line::from(Span::raw(line.to_owned())))
        .collect::<Vec<_>>();
    if lines.is_empty() {
        lines.push(Line::from(Span::styled(
            "Type a prompt or /command",
            Style::default().fg(Color::DarkGray),
        )));
    }
    let suggestions = slash_suggestions(app);
    if !suggestions.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Suggestions ", Style::default().fg(Color::Cyan)),
            Span::raw(suggestions.join("  ")),
        ]));
    }
    lines
}

fn slash_suggestions(app: &InteractiveApp) -> Vec<String> {
    let input = app.input.trim_start();
    if !input.starts_with('/') {
        return Vec::new();
    }
    let prefix = input
        .trim_start_matches('/')
        .split_whitespace()
        .next()
        .unwrap_or("");
    app.slash_catalog
        .iter()
        .filter(|hint| hint.name.starts_with(prefix))
        .take(5)
        .map(|hint| format!("{} - {}", hint.usage, hint.summary))
        .collect()
}

fn input_cursor_position(app: &InteractiveApp, area: Rect) -> Position {
    let before_cursor = &app.input[..app.input_cursor.min(app.input.len())];
    let row = before_cursor.bytes().filter(|byte| *byte == b'\n').count() as u16;
    let col = before_cursor
        .rsplit('\n')
        .next()
        .unwrap_or_default()
        .chars()
        .count() as u16;
    let x = area.x.saturating_add(col.min(area.width.saturating_sub(1)));
    let y = area
        .y
        .saturating_add(row.min(area.height.saturating_sub(1)));
    Position::new(x, y)
}

fn slash_hints_from_event(event: &GatewayEvent) -> Vec<SlashHint> {
    event
        .data
        .get("commands")
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
        .filter_map(|value| {
            let object = value.as_object()?;
            Some(SlashHint {
                name: object.get("name")?.as_str()?.to_owned(),
                usage: object
                    .get("usage")
                    .and_then(|value| value.as_str())
                    .unwrap_or_default()
                    .to_owned(),
                summary: object
                    .get("summary")
                    .and_then(|value| value.as_str())
                    .unwrap_or_default()
                    .to_owned(),
            })
        })
        .collect()
}

fn is_request_terminal_event(event: &GatewayEvent) -> bool {
    matches!(
        event.event_type.as_str(),
        "session.status"
            | "slash.catalog"
            | "slash.completed"
            | "model.changed"
            | "approval.resolved"
            | "run.completed"
            | "run.interrupt.requested"
            | "error"
    )
}

fn summarize_slash_output(event: &GatewayEvent) -> Option<String> {
    let data = &event.data;
    if let Some(payload) = data.get("payload") {
        if let Some(items) = payload.as_array() {
            if items.is_empty() {
                return Some("No records.".to_owned());
            }
            let mut lines = vec![format!("{} records", items.len())];
            for item in items.iter().take(6) {
                if let Some(object) = item.as_object() {
                    let id = object
                        .get("id")
                        .and_then(|value| value.as_str())
                        .unwrap_or("record");
                    let status = object
                        .get("status")
                        .and_then(|value| value.as_str())
                        .unwrap_or("unknown");
                    let runner = object
                        .get("runner_id")
                        .and_then(|value| value.as_str())
                        .unwrap_or("runner unknown");
                    lines.push(format!("- {id} [{status}] via {runner}"));
                }
            }
            if items.len() > 6 {
                lines.push(format!("- and {} more", items.len() - 6));
            }
            return Some(lines.join("\n"));
        }
    }
    data.get("text")
        .and_then(|value| value.as_str())
        .map(str::to_owned)
}

fn render_activity_panel(app: &InteractiveApp) -> String {
    let model = app
        .state
        .active_model_display_name
        .as_ref()
        .or(app.state.active_model.as_ref())
        .map(String::as_str)
        .unwrap_or("not selected");
    let mut lines = vec![
        format!(
            "Session: {}",
            if app.state.ready { "ready" } else { "starting" }
        ),
        format!(
            "Readiness: {}",
            app.state.readiness_state.as_deref().unwrap_or("unknown")
        ),
        format!("Model: {model}"),
        format!(
            "Backend: {}",
            app.state.backend.as_deref().unwrap_or("auto")
        ),
        format!("Run: {}", app.state.run_status.as_deref().unwrap_or("idle")),
        format!(
            "Phase: {}",
            app.state.working_phase.as_deref().unwrap_or("none")
        ),
        format!("Receipts: {}", app.state.receipt_ids.len()),
        format!("Tools: {}", app.state.tool_events.len()),
        format!("Files: {}", app.state.file_paths.len()),
        format!("Commands: {}", app.state.commands.len()),
        format!("Approvals: {}", app.state.approval_requests.len()),
        format!("Slash commands: {}", app.slash_catalog.len()),
        format!("Queued: {}", app.queued_inputs.len()),
        "Ctrl-A approves latest · Ctrl-X denies latest".to_owned(),
    ];
    if let Some(error) = &app.last_error {
        lines.push(format!("Last error: {error}"));
    }
    lines.join("\n")
}

fn status_line(app: &InteractiveApp) -> Line<'static> {
    let state = if app.in_flight { "working" } else { "ready" };
    let model = app
        .state
        .active_model_display_name
        .as_ref()
        .or(app.state.active_model.as_ref())
        .cloned()
        .unwrap_or_else(|| "model not selected".to_owned());
    Line::from(vec![
        Span::styled(
            "Craik",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(format!(
            " · {model} · {state} · Enter sends · Alt-Enter newline · ↑/↓ history · PgUp/PgDn scroll · Ctrl-A approve · Ctrl-X deny · Ctrl-C exits"
        )),
    ])
}

fn render_replay(path: &str) -> anyhow::Result<String> {
    if path.starts_with('-') {
        bail!("unknown option: {path}");
    }
    let input = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    render_events(&input)
}

fn render_events(input: &str) -> anyhow::Result<String> {
    let events = parse_gateway_events(input)?;
    let summary = summarize_gateway_events(&events);
    Ok(render_replay_text(&summary))
}

fn usage() -> String {
    [
        "Craik Ratatui client",
        "",
        "Interactive:",
        "  craik-tui-rs",
        "",
        "Replay:",
        "  craik-tui-rs <events.jsonl>",
        "  cat events.jsonl | craik-tui-rs",
        "",
        "Live Gateway commands:",
        "  craik-tui-rs --status",
        "  craik-tui-rs --submit \"Review the plan\"",
        "  craik-tui-rs --slash \"/run list\"",
        "  craik-tui-rs --model anthropic/claude-opus-4-7",
        "  craik-tui-rs --approve approval_123 \"reviewed\"",
        "  craik-tui-rs --deny approval_123 \"too broad\"",
        "  craik-tui-rs --interrupt run_123 \"operator requested stop\"",
    ]
    .join("\n")
}

#[cfg(test)]
mod tests {
    use super::{
        InteractiveApp, SlashHint, TranscriptEntry, TranscriptKind, input_cursor_position,
        is_request_terminal_event, render_transcript_lines, slash_suggestions,
    };
    use craik_tui_rs::GatewayEvent;
    use ratatui::layout::Rect;
    use serde_json::json;

    #[test]
    fn transcript_rendering_labels_entry_kinds() {
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
    fn slash_suggestions_use_catalog_usage() {
        let mut app = InteractiveApp::for_test();
        app.input = "/r".to_owned();
        app.slash_catalog = vec![
            SlashHint {
                name: "run".to_owned(),
                usage: "/run <prompt>".to_owned(),
                summary: "Run an audited prompt.".to_owned(),
            },
            SlashHint {
                name: "status".to_owned(),
                usage: "/status".to_owned(),
                summary: "Show readiness.".to_owned(),
            },
        ];

        assert_eq!(
            slash_suggestions(&app),
            ["/run <prompt> - Run an audited prompt."]
        );
    }

    #[test]
    fn cursor_position_tracks_multiline_input() {
        let mut app = InteractiveApp::for_test();
        app.input = "abc\ndef".to_owned();
        app.input_cursor = app.input.len();

        let position = input_cursor_position(&app, Rect::new(10, 20, 40, 3));

        assert_eq!(position.x, 13);
        assert_eq!(position.y, 21);
    }

    #[test]
    fn terminal_event_detection_covers_request_boundaries() {
        let completed = GatewayEvent {
            event_type: "run.completed".to_owned(),
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({}),
        };
        let progress = GatewayEvent {
            event_type: "run.progress".to_owned(),
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({}),
        };

        assert!(is_request_terminal_event(&completed));
        assert!(!is_request_terminal_event(&progress));
    }
}
