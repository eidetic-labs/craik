use crate::{
    backend::{BackendSession, WorkerMessage},
    gateway_events::{is_request_terminal_event, slash_hints_from_event, summarize_slash_output},
    input::{SlashHint, slash_completion_at, slash_suggestion_count},
    transcript::{TranscriptEntry, TranscriptKind},
};
use craik_tui_rs::{GatewayAppState, GatewayCommand, GatewayEvent, format_gateway_error_event};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use serde_json::Value;
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

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct OverlayItem {
    pub(crate) title: String,
    pub(crate) summary: String,
    pub(crate) detail: String,
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

    pub(crate) fn footer_hint(self) -> &'static str {
        match self {
            Self::Memory => "Type filter  Up/Down select  Ctrl-E evidence  Esc chat",
            Self::Evidence => "Type filter  Up/Down select  Ctrl-R runs  Esc chat",
            Self::Runs => "Type filter  Up/Down select  Ctrl-L filter  Ctrl-O export  Esc chat",
            Self::Approvals => "Ctrl-N/P select  a approve  d deny  Esc defer",
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

const PERMISSION_MODE_CYCLE: &[&str] = &[
    "ask",
    "auto",
    "acceptEdits",
    "plan",
    "dontAsk",
    "bypassPermissions",
];

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
    origin: Option<String>,
    tool: Option<String>,
    target: Option<String>,
    capability: Option<String>,
    resource: Option<String>,
    scope: Option<String>,
    size: Option<String>,
    receipt_id: Option<String>,
    expires_at: Option<String>,
    reason: Option<String>,
    risk: Option<String>,
    command: Option<String>,
    preview: Option<String>,
    /// The Claude permission mode this approval was raised under (e.g.
    /// `bypassPermissions`), when the event carries it. Captured so the
    /// most-dangerous mode forces the high-risk two-press gate independent of
    /// the free-text risk string.
    permission_mode: Option<String>,
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
    #[cfg(test)]
    pub(crate) transcript_focused: bool,
    pub(crate) expand_transcript_details: bool,
    pub(crate) help_visible: bool,
    pub(crate) active_overlay: Option<ActiveOverlay>,
    /// The id of the high-risk / bypassPermissions approval currently *armed*
    /// for its explicit second-press confirm. Keying the arm to the selected
    /// approval's identity (instead of a bare overlay-global bool) is fail-safe
    /// by construction: any change of selection -- by navigation, by a queue
    /// mutation that shifts the selected index, or by a committed decision --
    /// leaves a stale id that no longer matches the newly-selected approval, so
    /// the gate re-arms from scratch. Every high-risk approval therefore
    /// requires its OWN two-press confirm; no manual reset on each
    /// selection-change path can be forgotten.
    pub(crate) armed_approval_id: Option<String>,
    pub(crate) overlay_filter: String,
    pub(crate) overlay_selected_index: usize,
    pub(crate) overlay_scroll: u16,
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
    pub(crate) slash_selected_index: usize,
    history: Vec<String>,
    history_index: Option<usize>,
    pub(crate) queued_inputs: VecDeque<String>,
    pub(crate) run_records: Vec<RunRecord>,
    pub(crate) selected_run_index: Option<usize>,
    pub(crate) run_filter: RunFilter,
    auto_select_latest_run: bool,
    last_submitted_text: Option<String>,
    last_prompt_preview: Option<String>,
    /// Identity of the in-flight coalesced assistant entry: `(run_id, index)`
    /// into `transcript`. Lets a growing `assistant_text` snapshot supersede the
    /// run's earlier partial in place instead of stacking duplicates.
    assistant_text_entry: Option<(String, usize)>,
    /// Identity of the in-flight coalesced Progress entry: `(run_id, index)` into
    /// `transcript`. Repeated `run.progress` updates for one run supersede this
    /// entry in place (one updating status line) instead of stacking N frozen
    /// lines. The slot is honoured only while the tracked index is still the
    /// transcript tail; once any other entry is pushed (a tool/assistant/system
    /// line, run completion, etc.) the tail moves and the next progress update
    /// starts a fresh line. See `supersede_progress`.
    progress_entry: Option<(String, usize)>,
}

impl InteractiveApp {
    pub(crate) fn new() -> anyhow::Result<Self> {
        let backend = BackendSession::start()?;
        let mut app = Self {
            state: GatewayAppState::default(),
            input: String::new(),
            input_cursor: 0,
            transcript: Vec::new(),
            transcript_scroll: 0,
            #[cfg(test)]
            transcript_focused: false,
            expand_transcript_details: false,
            help_visible: false,
            active_overlay: None,
            armed_approval_id: None,
            overlay_filter: String::new(),
            overlay_selected_index: 0,
            overlay_scroll: 0,
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
            slash_selected_index: 0,
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
            run_records: Vec::new(),
            selected_run_index: None,
            run_filter: RunFilter::All,
            auto_select_latest_run: true,
            last_submitted_text: None,
            last_prompt_preview: None,
            assistant_text_entry: None,
            progress_entry: None,
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
            #[cfg(test)]
            transcript_focused: false,
            expand_transcript_details: false,
            help_visible: false,
            active_overlay: None,
            armed_approval_id: None,
            overlay_filter: String::new(),
            overlay_selected_index: 0,
            overlay_scroll: 0,
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
            slash_selected_index: 0,
            history: Vec::new(),
            history_index: None,
            queued_inputs: VecDeque::new(),
            run_records: Vec::new(),
            selected_run_index: None,
            run_filter: RunFilter::All,
            auto_select_latest_run: true,
            last_submitted_text: None,
            last_prompt_preview: None,
            assistant_text_entry: None,
            progress_entry: None,
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

    fn cycle_permission_mode(&mut self) {
        let next_mode = next_permission_mode(self.state.active_permission_mode.as_deref());
        self.transcript.push(TranscriptEntry::system(
            "Mode",
            &format!("Switching mode to `{next_mode}`."),
        ));
        self.dispatch_text(format!("/mode {next_mode}"));
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
                    self.refresh_slash_catalog_current_values();
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

    #[cfg(test)]
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

    #[cfg(test)]
    pub(crate) fn selected_approval_preview(&self) -> Option<String> {
        self.selected_approval_detail_text()
    }

    #[cfg(test)]
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
        let count = self.overlay_items().len();
        Some(format!(
            "▌{}  {}  esc closes",
            overlay.title().to_uppercase(),
            count
        ))
    }

    pub(crate) fn overlay_footer_hint(&self) -> Option<&'static str> {
        self.active_overlay.map(ActiveOverlay::footer_hint)
    }

    pub(crate) fn overlay_items(&self) -> Vec<OverlayItem> {
        let Some(overlay) = self.active_overlay else {
            return Vec::new();
        };
        let items = match overlay {
            ActiveOverlay::Memory => self.memory_overlay_items(),
            ActiveOverlay::Evidence => self.evidence_overlay_items(),
            ActiveOverlay::Runs => self.runs_overlay_items(),
            ActiveOverlay::Approvals => self.approvals_overlay_items(),
        };
        filter_overlay_items(items, &self.overlay_filter)
    }

    pub(crate) fn selected_overlay_detail(&self) -> String {
        let items = self.overlay_items();
        if items.is_empty() {
            if self.overlay_filter.trim().is_empty() {
                return "No items available yet.".to_owned();
            }
            return format!("No items match `{}`.", self.overlay_filter.trim());
        }
        items
            .get(self.overlay_selected_index.min(items.len() - 1))
            .map(|item| item.detail.clone())
            .unwrap_or_else(|| "No item selected.".to_owned())
    }

    pub(crate) fn overlay_text(&self) -> Option<String> {
        let overlay = self.active_overlay?;
        let mut lines = vec![
            format!("{} review", overlay.title()),
            format!(
                "  Filter: {}",
                if self.overlay_filter.is_empty() {
                    "none"
                } else {
                    self.overlay_filter.as_str()
                }
            ),
            String::new(),
        ];
        let items = self.overlay_items();
        for (index, item) in items
            .iter()
            .enumerate()
            .skip(self.overlay_scroll as usize)
            .take(10)
        {
            let marker = if index == self.overlay_selected_index {
                "▌"
            } else {
                " "
            };
            lines.push(format!("{marker} {} — {}", item.title, item.summary));
        }
        lines.push(String::new());
        lines.push(self.selected_overlay_detail());
        Some(lines.join("\n"))
    }

    fn memory_overlay_items(&self) -> Vec<OverlayItem> {
        vec![
            OverlayItem {
                title: "Provider".to_owned(),
                summary: self
                    .state
                    .active_provider_family
                    .as_deref()
                    .or(self.state.active_provider_id.as_deref())
                    .unwrap_or("not selected")
                    .to_owned(),
                detail: format!(
                    "Provider\nFamily: {}\nID: {}",
                    self.state
                        .active_provider_family
                        .as_deref()
                        .unwrap_or("not selected"),
                    self.state
                        .active_provider_id
                        .as_deref()
                        .unwrap_or("not selected")
                ),
            },
            OverlayItem {
                title: "Model".to_owned(),
                summary: self
                    .state
                    .active_model_display_name
                    .as_deref()
                    .or(self.state.active_model.as_deref())
                    .unwrap_or("not selected")
                    .to_owned(),
                detail: format!(
                    "Model\nDisplay: {}\nRaw: {}",
                    self.state
                        .active_model_display_name
                        .as_deref()
                        .unwrap_or("not selected"),
                    self.state.active_model.as_deref().unwrap_or("not selected")
                ),
            },
            OverlayItem {
                title: "Last prompt".to_owned(),
                summary: self
                    .last_prompt_preview
                    .as_deref()
                    .unwrap_or("none submitted")
                    .to_owned(),
                detail: format!(
                    "Last prompt\n{}",
                    self.last_prompt_preview
                        .as_deref()
                        .unwrap_or("No prompt submitted in this session.")
                ),
            },
            OverlayItem {
                title: "Receipts".to_owned(),
                summary: format!("{} available", self.state.receipt_ids.len()),
                detail: format!("Receipts\n{}", join_recent(&self.state.receipt_ids)),
            },
            OverlayItem {
                title: "Runs".to_owned(),
                summary: format!("{} available", self.run_records.len()),
                detail: format!(
                    "Runs\n{}",
                    self.run_records
                        .iter()
                        .rev()
                        .take(8)
                        .map(|run| run.run_id.as_str())
                        .collect::<Vec<_>>()
                        .join("\n")
                ),
            },
        ]
    }

    fn evidence_overlay_items(&self) -> Vec<OverlayItem> {
        let mut items = Vec::new();
        items.extend(self.receipt_overlay_items());
        items.extend(self.state.file_paths.iter().rev().map(|path| OverlayItem {
            title: path.clone(),
            summary: "file".to_owned(),
            detail: format!("File\nPath: {path}"),
        }));
        items.extend(self.state.commands.iter().rev().map(|command| OverlayItem {
            title: command.clone(),
            summary: "command".to_owned(),
            detail: format!("Command\n{command}"),
        }));
        items.extend(self.state.tool_events.iter().rev().map(|tool| OverlayItem {
            title: tool.label.clone(),
            summary: tool.kind.clone(),
            detail: format!(
                "Tool\nKind: {}\nLabel: {}\n{}",
                tool.kind,
                tool.label,
                tool.detail.as_deref().unwrap_or("No detail available.")
            ),
        }));
        if items.is_empty() {
            items.push(OverlayItem {
                title: "No evidence yet".to_owned(),
                summary: "run a prompt to collect receipts".to_owned(),
                detail: "Evidence will show receipts, files, commands, and tool events from Gateway runs.".to_owned(),
            });
        }
        items
    }

    fn receipt_overlay_items(&self) -> Vec<OverlayItem> {
        self.state
            .receipt_ids
            .iter()
            .rev()
            .map(|receipt| {
                let run = self.run_for_receipt(receipt);
                let detail = run
                    .map(|run| run.receipt_overlay_detail(receipt))
                    .unwrap_or_else(|| format!("Receipt\nID: {receipt}"));
                OverlayItem {
                    title: receipt.clone(),
                    summary: run
                        .map(|run| {
                            format!(
                                "receipt · {} · {} provenance item(s)",
                                run.status.as_deref().unwrap_or("active"),
                                run.provenance.len()
                            )
                        })
                        .unwrap_or_else(|| "receipt".to_owned()),
                    detail,
                }
            })
            .collect()
    }

    fn run_for_receipt(&self, receipt_id: &str) -> Option<&RunRecord> {
        self.run_records
            .iter()
            .rev()
            .find(|run| run.receipts.iter().any(|receipt| receipt == receipt_id))
    }

    fn runs_overlay_items(&self) -> Vec<OverlayItem> {
        let mut items = self
            .filtered_run_indexes()
            .into_iter()
            .filter_map(|index| self.run_records.get(index).map(|run| (index, run)))
            .map(|(index, run)| OverlayItem {
                title: run.run_id.clone(),
                summary: format!(
                    "{} · {} receipt(s) · {} tool(s)",
                    run.status.as_deref().unwrap_or("active"),
                    run.receipts.len(),
                    run.tools.len()
                ),
                detail: format!("{}\n\nIndex: {index}", run.detail_text()),
            })
            .collect::<Vec<_>>();
        if items.is_empty() {
            items.push(OverlayItem {
                title: "No runs".to_owned(),
                summary: format!("filter={}", self.run_filter.label()),
                detail: self.selected_run_provenance(),
            });
        }
        items
    }

    fn approvals_overlay_items(&self) -> Vec<OverlayItem> {
        let total = self.pending_approvals.len();
        let mut items = self
            .pending_approvals
            .iter()
            .enumerate()
            .map(|(index, approval)| OverlayItem {
                title: if approval.id.is_empty() {
                    format!("approval {}", index + 1)
                } else {
                    approval.id.clone()
                },
                summary: approval
                    .target
                    .as_deref()
                    .or(approval.resource.as_deref())
                    .or(approval.command.as_deref())
                    .or(approval.tool.as_deref())
                    .or(approval.capability.as_deref())
                    .unwrap_or("review required")
                    .to_owned(),
                detail: approval.modal_text(
                    index + 1,
                    total,
                    self.state.receipt_ids.last().map(String::as_str),
                ),
            })
            .collect::<Vec<_>>();
        if items.is_empty() {
            items.push(OverlayItem {
                title: "No pending approvals".to_owned(),
                summary: "queue empty".to_owned(),
                detail: "Approvals requested by the Gateway will appear here with their real target, command, reason, and risk context.".to_owned(),
            });
        }
        items
    }

    #[cfg(test)]
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

    fn selected_approval_is_high_risk(&self) -> bool {
        self.selected_pending_approval()
            .is_some_and(PendingApproval::is_high_risk)
    }

    /// Whether the currently selected approval is the one armed for its
    /// explicit second-press confirm. Drives the footer "armed" affordance.
    pub(crate) fn selected_approval_is_armed(&self) -> bool {
        matches!(
            (&self.armed_approval_id, self.selected_pending_approval()),
            (Some(armed), Some(selected)) if *armed == selected.id
        )
    }

    fn selected_approval_detail_text(&self) -> Option<String> {
        let index = self.selected_approval_index?;
        let approval = self.pending_approvals.get(index)?;
        Some(approval.modal_text(
            index + 1,
            self.pending_approvals.len(),
            self.state.receipt_ids.last().map(String::as_str),
        ))
    }

    fn open_overlay(&mut self, overlay: ActiveOverlay) {
        self.active_overlay = Some(overlay);
        // Single-press keymap: the approvals overlay opens disarmed. The arm is
        // keyed to the selected approval's id, so opening clears any stale arm.
        self.armed_approval_id = None;
        self.overlay_filter.clear();
        self.overlay_selected_index = match overlay {
            ActiveOverlay::Runs => self
                .selected_run_index
                .and_then(|selected| {
                    self.filtered_run_indexes()
                        .iter()
                        .position(|index| *index == selected)
                })
                .unwrap_or_default(),
            ActiveOverlay::Approvals => self.selected_approval_index.unwrap_or_default(),
            _ => 0,
        };
        self.overlay_scroll = 0;
        self.sync_overlay_selection();
    }

    fn surface_pending_approval_overlay(&mut self) {
        self.open_overlay(ActiveOverlay::Approvals);
        self.armed_approval_id = None;
    }

    fn close_unreviewed_approval_overlay(&mut self) {
        if self.active_overlay == Some(ActiveOverlay::Approvals)
            && self.armed_approval_id.is_none()
            && self.pending_approvals.is_empty()
        {
            self.active_overlay = None;
        }
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
                self.open_overlay(ActiveOverlay::Approvals);
                LoopAction::Continue
            }
            KeyCode::Char('x') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.surface_pending_approval_overlay();
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
                self.open_overlay(ActiveOverlay::Runs);
                LoopAction::Continue
            }
            KeyCode::Char('e') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.open_overlay(ActiveOverlay::Evidence);
                LoopAction::Continue
            }
            KeyCode::Char('m') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.open_overlay(ActiveOverlay::Memory);
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
            KeyCode::BackTab => {
                self.cycle_permission_mode();
                LoopAction::Continue
            }
            KeyCode::Char('j') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                if self.slash_palette_active() {
                    self.select_next_slash_suggestion();
                } else {
                    self.select_next_run();
                }
                LoopAction::Continue
            }
            KeyCode::Char('k') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                if self.slash_palette_active() {
                    self.select_previous_slash_suggestion();
                } else {
                    self.select_previous_run();
                }
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
                if self.accept_slash_selection_for_submit() {
                    return LoopAction::Continue;
                }
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
            KeyCode::Up if key.modifiers.contains(KeyModifiers::ALT) => {
                self.scroll_transcript_up_by(1);
                LoopAction::Continue
            }
            KeyCode::Down if key.modifiers.contains(KeyModifiers::ALT) => {
                self.scroll_transcript_down_by(1);
                LoopAction::Continue
            }
            KeyCode::Up => {
                if self.slash_palette_active() {
                    self.select_previous_slash_suggestion();
                } else if self.input_has_multiple_lines() && !self.cursor_is_on_first_line() {
                    self.move_cursor_up_line();
                } else {
                    self.history_previous();
                }
                LoopAction::Continue
            }
            KeyCode::Down => {
                if self.slash_palette_active() {
                    self.select_next_slash_suggestion();
                } else if self.input_has_multiple_lines() && !self.cursor_is_on_last_line() {
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
                self.armed_approval_id = None;
                self.overlay_filter.clear();
            }
            KeyCode::Char('m') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.open_overlay(ActiveOverlay::Memory);
            }
            KeyCode::Char('e') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.open_overlay(ActiveOverlay::Evidence);
            }
            KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.open_overlay(ActiveOverlay::Runs);
            }
            // Single-press approve while the approvals overlay is focused. A
            // low-risk approval is decided on the first 'a'. A high-risk /
            // bypassPermissions approval keeps an explicit confirmation gate:
            // the first 'a' ARMS this specific approval (records its id in
            // `armed_approval_id`) and only a second 'a' -- while that SAME
            // approval is still selected -- approves, so a destructive action
            // never lands on a single accidental keystroke. The arm is keyed to
            // the approval's identity, so navigating away, a queue mutation, or
            // a committed decision leaves a stale id that no longer matches the
            // selection: the gate re-arms from scratch for every high-risk item.
            // This branch is reachable only when an overlay is focused (see
            // `handle_key` routing), so a stray 'a' in the composer can never
            // approve anything.
            KeyCode::Char('a')
                if !key.modifiers.contains(KeyModifiers::CONTROL)
                    && self.active_overlay == Some(ActiveOverlay::Approvals) =>
            {
                let selected_id = self.selected_pending_approval().map(|a| a.id.clone());
                let armed_for_selection = matches!(
                    (&self.armed_approval_id, &selected_id),
                    (Some(armed), Some(selected)) if armed == selected
                );
                if self.selected_approval_is_high_risk() && !armed_for_selection {
                    self.armed_approval_id = selected_id;
                } else {
                    self.approve_selected();
                }
            }
            // Open the approvals overlay from any *other* overlay with Ctrl-A.
            KeyCode::Char('a')
                if key.modifiers.contains(KeyModifiers::CONTROL)
                    && self.active_overlay != Some(ActiveOverlay::Approvals) =>
            {
                self.open_overlay(ActiveOverlay::Approvals);
            }
            // Single-press deny while the approvals overlay is focused. Deny is
            // always unambiguous and one press -- it never falls through to
            // approve and needs no arming step, even for high-risk approvals.
            KeyCode::Char('d')
                if !key.modifiers.contains(KeyModifiers::CONTROL)
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
                self.select_next_overlay_item();
            }
            KeyCode::Char('k') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.select_previous_overlay_item();
            }
            KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.cycle_run_filter();
            }
            KeyCode::Char('o') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.export_selected_run();
            }
            KeyCode::PageUp => {
                self.overlay_scroll = self.overlay_scroll.saturating_sub(6);
            }
            KeyCode::PageDown => {
                self.overlay_scroll = self.overlay_scroll.saturating_add(6);
                self.clamp_overlay_scroll();
            }
            KeyCode::Up => {
                self.select_previous_overlay_item();
            }
            KeyCode::Down => {
                self.select_next_overlay_item();
            }
            KeyCode::Backspace => {
                self.overlay_filter.pop();
                self.overlay_selected_index = 0;
                self.overlay_scroll = 0;
                self.sync_overlay_selection();
            }
            KeyCode::Char(ch) if !key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.overlay_filter.push(ch);
                self.overlay_selected_index = 0;
                self.overlay_scroll = 0;
                self.sync_overlay_selection();
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
            "  PageUp / PageDown scroll transcript by page; Alt-Up / Alt-Down by line".to_owned(),
            "Approvals".to_owned(),
            "  Ctrl-A opens the approval overlay; a approves, d denies, Esc defers".to_owned(),
            "  High-risk approvals require a second a to confirm".to_owned(),
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
            "session.ready"
                if event
                    .data
                    .get("state")
                    .and_then(|value| value.as_str())
                    .is_some_and(|state| state != "ready") =>
            {
                self.transcript.push(TranscriptEntry::system(
                    "Gateway",
                    &summarize_session_ready_event(event),
                ));
            }
            "session.ready" => {}
            "session.status" => {
                let state = event
                    .data
                    .get("state")
                    .and_then(|value| value.as_str())
                    .unwrap_or("unknown");
                if state != "ready" {
                    self.transcript.push(TranscriptEntry::system(
                        "Run blocked",
                        &blocked_run_guidance(event),
                    ));
                }
            }
            "session.history" => {
                self.record_history_event(event);
            }
            "slash.catalog" => {
                self.slash_catalog = slash_hints_from_event(event);
                self.refresh_slash_catalog_current_values();
            }
            "prompt.submitted" => {
                let preview = event
                    .data
                    .get("prompt_preview")
                    .and_then(|value| value.as_str())
                    .unwrap_or("prompt submitted");
                self.last_prompt_preview = Some(preview.to_owned());
            }
            "model.selected" | "model.changed" => {}
            "run.started" => {}
            "run.progress" => {
                if let Some(message) = event.data.get("message").and_then(|value| value.as_str())
                    && !should_hide_transcript_event(event)
                    && should_show_progress_message(event, message)
                    && self.supersede_progress(event, message)
                {
                    self.follow_tail_after_transcript_update();
                }
            }
            "tool.used" => {
                let tool = event
                    .data
                    .get("tool")
                    .and_then(|value| value.as_str())
                    .unwrap_or("tool");
                let message = event.data.get("message").and_then(|value| value.as_str());
                // The typed API adapters emit tool.used with command/target but
                // no message; render whenever any of message/command/target is
                // present so tool activity is never silently dropped.
                let has_renderable = message.is_some()
                    || event.data.get("command").is_some()
                    || event.data.get("target").is_some();
                if has_renderable {
                    let kind = if tool == "Bash" {
                        TranscriptKind::Command
                    } else {
                        TranscriptKind::Tool
                    };
                    let text = summarize_tool_event(event, tool, message);
                    if append_grouped_tool_transcript(&mut self.transcript, kind, tool, &text) {
                        self.follow_tail_after_transcript_update();
                    } else if !recent_transcript_entry_matches(&self.transcript, kind, tool, &text)
                    {
                        self.transcript
                            .push(TranscriptEntry::new(kind, tool, &text));
                        self.follow_tail_after_transcript_update();
                    }
                }
            }
            "run.working" => {
                // Routine working phases are reflected in footer/run detail, not the chat lane.
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
                if !self
                    .pending_approvals
                    .iter()
                    .any(|candidate| candidate.id == approval.id)
                {
                    self.pending_approvals.push(approval.clone());
                    self.selected_approval_index =
                        Some(self.pending_approvals.len().saturating_sub(1));
                }
                self.surface_pending_approval_overlay();
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
            "receipt.created"
                if event
                    .data
                    .get("receipt_id")
                    .and_then(|value| value.as_str())
                    .is_some() =>
            {
                self.transcript.push(TranscriptEntry::new(
                    TranscriptKind::Receipt,
                    "Evidence saved",
                    &summarize_receipt_marker(event),
                ));
                self.follow_tail_after_transcript_update();
            }
            "assistant_text" => {
                // Assistant text is coalesced upstream (the backend Coalescer
                // supersedes cumulative snapshots), so the per-run stream is a
                // growing snapshot. Supersede the run's existing Assistant entry
                // in place rather than stacking N partials.
                if let Some(text) = event.data.get("text").and_then(|value| value.as_str()) {
                    let display_text = text.trim();
                    if display_text.is_empty() {
                        return;
                    }
                    if self.supersede_assistant_text(event, display_text) {
                        self.follow_tail_after_transcript_update();
                    }
                }
            }
            "run.output" => {
                self.close_unreviewed_approval_overlay();
                if let Some(summary) = event.data.get("summary").and_then(|value| value.as_str())
                    && let Some(display_text) = run_output_transcript_text(summary)
                    && !recent_transcript_body_matches(&self.transcript, &display_text)
                {
                    self.transcript
                        .push(TranscriptEntry::assistant("Assistant", &display_text));
                    self.follow_tail_after_transcript_update();
                }
            }
            "run.completed" => {
                self.close_unreviewed_approval_overlay();
                let status = event
                    .data
                    .get("status")
                    .and_then(|value| value.as_str())
                    .unwrap_or("completed");
                if status != "completed" {
                    self.transcript.push(TranscriptEntry::progress(
                        "Run completed",
                        &summarize_run_event(event, status),
                    ));
                }
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

    /// Render a coalesced `assistant_text` snapshot, superseding the same run's
    /// earlier (smaller) snapshot in place. Returns whether the transcript
    /// changed. Dedup is by `run_id` rather than a content-window match.
    ///
    /// `run_id` is not contract-required on `assistant_text` (the backend
    /// `Coalescer` permits run-less streams); a missing id falls to the `""`
    /// key, collapsing run-less snapshots into one slot, mirroring the backend's
    /// `None`-key grouping. This tracks only the most-recent run's slot, which is
    /// sufficient because the gateway has a single run in flight at a time; if
    /// concurrent runs are ever introduced, interleaved snapshots would stack
    /// rather than supersede and this would need a per-run map.
    fn supersede_assistant_text(&mut self, event: &GatewayEvent, text: &str) -> bool {
        let run_key = event.run_id.clone().unwrap_or_default();
        if let Some((existing_run, index)) = self.assistant_text_entry.as_ref()
            && *existing_run == run_key
            && let Some(entry) = self.transcript.get_mut(*index)
            && entry.kind == TranscriptKind::Assistant
        {
            if entry.body == text {
                return false;
            }
            entry.update_body(text);
            return true;
        }
        self.transcript
            .push(TranscriptEntry::assistant("Assistant", text));
        self.assistant_text_entry = Some((run_key, self.transcript.len() - 1));
        true
    }

    /// Render a `run.progress` update, superseding this run's earlier progress
    /// line in place rather than stacking a fresh frozen line per update.
    /// Returns whether the transcript changed.
    ///
    /// The tracked slot is honoured only when it is still the transcript tail
    /// AND keyed to the same run. The tail check is what implements the
    /// "reset on a non-progress entry or new run" requirement without
    /// instrumenting every other push site: as soon as a tool/assistant/system
    /// line (or a different run's progress) is appended, the tracked index is no
    /// longer the tail, so the next progress update appends fresh. A `run_id` of
    /// `None` collapses to the `""` key (run-less progress streams share one
    /// slot), mirroring `supersede_assistant_text`.
    fn supersede_progress(&mut self, event: &GatewayEvent, message: &str) -> bool {
        let run_key = event.run_id.clone().unwrap_or_default();
        if let Some((existing_run, index)) = self.progress_entry.as_ref()
            && *existing_run == run_key
            && *index + 1 == self.transcript.len()
            && let Some(entry) = self.transcript.get_mut(*index)
            && entry.kind == TranscriptKind::Progress
        {
            if entry.body == message {
                return false;
            }
            entry.update_body(message);
            return true;
        }
        self.transcript
            .push(TranscriptEntry::progress("Progress", message));
        self.progress_entry = Some((run_key, self.transcript.len() - 1));
        true
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
                    push_unique_string(&mut run.receipt_details, receipt_detail_from_event(event));
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
        self.reset_slash_selection();
    }

    pub(crate) fn insert_newline(&mut self) {
        self.input.insert(self.input_cursor, '\n');
        self.input_cursor += 1;
        self.reset_slash_selection();
    }

    pub(crate) fn paste_text(&mut self, text: &str) {
        if text.is_empty() {
            return;
        }
        self.input.insert_str(self.input_cursor, text);
        self.input_cursor += text.len();
        self.reset_slash_selection();
    }

    pub(crate) fn clear_input(&mut self) {
        self.input.clear();
        self.input_cursor = 0;
        self.reset_slash_selection();
    }

    pub(crate) fn complete_slash_input(&mut self) {
        if self.input_cursor != self.input.len() {
            return;
        }
        if let Some(completion) =
            slash_completion_at(&self.input, &self.slash_catalog, self.slash_selected_index)
        {
            self.input = completion;
            self.input_cursor = self.input.len();
            self.clamp_slash_selection();
        }
    }

    fn accept_slash_selection_for_submit(&mut self) -> bool {
        if self.input_cursor != self.input.len() || !self.slash_palette_active() {
            return false;
        }
        let Some(completion) =
            slash_completion_at(&self.input, &self.slash_catalog, self.slash_selected_index)
        else {
            return false;
        };
        if completion == self.input {
            return false;
        }
        self.input = completion;
        self.input_cursor = self.input.len();
        self.clamp_slash_selection();
        if selected_slash_completion_is_executable(&self.input) {
            self.submit_input();
        }
        true
    }

    pub(crate) fn backspace(&mut self) {
        if self.input_cursor == 0 {
            return;
        }
        if let Some((index, _)) = self.input[..self.input_cursor].char_indices().last() {
            self.input.replace_range(index..self.input_cursor, "");
            self.input_cursor = index;
            self.reset_slash_selection();
        }
    }

    pub(crate) fn delete(&mut self) {
        if self.input_cursor >= self.input.len() {
            return;
        }
        if let Some(ch) = self.input[self.input_cursor..].chars().next() {
            let next = self.input_cursor + ch.len_utf8();
            self.input.replace_range(self.input_cursor..next, "");
            self.reset_slash_selection();
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
        self.reset_slash_selection();
    }

    pub(crate) fn delete_to_line_end(&mut self) {
        let line_end = self.input[self.input_cursor..]
            .find('\n')
            .map(|index| self.input_cursor + index)
            .unwrap_or(self.input.len());
        self.input.replace_range(self.input_cursor..line_end, "");
        self.reset_slash_selection();
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
        self.reset_slash_selection();
    }

    pub(crate) fn slash_palette_active(&self) -> bool {
        self.input_cursor == self.input.len()
            && self.input.trim_start().starts_with('/')
            && slash_suggestion_count(&self.input, &self.slash_catalog) > 0
    }

    pub(crate) fn select_next_slash_suggestion(&mut self) {
        let count = slash_suggestion_count(&self.input, &self.slash_catalog);
        if count == 0 {
            self.slash_selected_index = 0;
            return;
        }
        self.slash_selected_index = (self.slash_selected_index + 1) % count;
    }

    pub(crate) fn select_previous_slash_suggestion(&mut self) {
        let count = slash_suggestion_count(&self.input, &self.slash_catalog);
        if count == 0 {
            self.slash_selected_index = 0;
            return;
        }
        self.slash_selected_index = if self.slash_selected_index == 0 {
            count - 1
        } else {
            self.slash_selected_index.min(count) - 1
        };
    }

    fn reset_slash_selection(&mut self) {
        self.slash_selected_index = 0;
    }

    fn refresh_slash_catalog_current_values(&mut self) {
        let mode = self
            .state
            .active_permission_mode
            .as_deref()
            .map(display_permission_mode);
        let effort = self.active_effort_value();
        let model = self.state.active_model.clone();
        for hint in &mut self.slash_catalog {
            match hint.name.as_str() {
                "model" => {
                    hint.current_value = model.clone();
                    if let Some(model) = &model
                        && !hint.model_choices.iter().any(|choice| choice == model)
                    {
                        hint.model_choices.insert(0, model.clone());
                    }
                }
                "mode" => {
                    hint.current_value = mode.map(str::to_owned);
                }
                "effort" => {
                    hint.current_value = effort.clone();
                }
                _ => {}
            }
        }
    }

    fn active_effort_value(&self) -> Option<String> {
        if let Some(effort) = self
            .state
            .active_reasoning_effort
            .as_deref()
            .filter(|effort| !effort.trim().is_empty())
        {
            return Some(effort.to_owned());
        }
        let is_claude =
            self.state.active_provider_family.as_deref() == Some("anthropic")
                || self.state.active_model.as_deref().is_some_and(|model| {
                    model.contains("claude") || model.starts_with("anthropic/")
                });
        is_claude.then(|| "default".to_owned())
    }

    fn clamp_slash_selection(&mut self) {
        let count = slash_suggestion_count(&self.input, &self.slash_catalog);
        if count == 0 {
            self.slash_selected_index = 0;
        } else {
            self.slash_selected_index = self.slash_selected_index.min(count - 1);
        }
    }

    pub(crate) fn input_line_count(&self) -> usize {
        self.input.lines().count().max(1)
    }

    #[cfg(test)]
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
        self.scroll_transcript_up_by(12);
    }

    pub(crate) fn scroll_transcript_down(&mut self) {
        self.scroll_transcript_down_by(12);
    }

    pub(crate) fn scroll_transcript_up_by(&mut self, lines: u16) {
        self.transcript_scroll = self.transcript_scroll.saturating_add(lines);
    }

    pub(crate) fn scroll_transcript_down_by(&mut self, lines: u16) {
        self.transcript_scroll = self.transcript_scroll.saturating_sub(lines);
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

    #[cfg(test)]
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
                self.selected_approval_detail_text().unwrap_or_else(
                    || approval.preview_text(self.state.receipt_ids.last().map(String::as_str))
                )
            ),
        ));
        self.send_commands([GatewayCommand::ApprovalDecide {
            approval_id: approval.id,
            decision: "approved".to_owned(),
            operator: "user:ratatui".to_owned(),
            reason: "approved from Ratatui client".to_owned(),
        }]);
        // A committed decision disarms unconditionally: a subsequently-selected
        // high-risk approval must require its own two-press confirm.
        self.armed_approval_id = None;
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
                self.selected_approval_detail_text().unwrap_or_else(
                    || approval.preview_text(self.state.receipt_ids.last().map(String::as_str))
                )
            ),
        ));
        self.send_commands([GatewayCommand::ApprovalDecide {
            approval_id: approval.id,
            decision: "denied".to_owned(),
            operator: "user:ratatui".to_owned(),
            reason: "denied from Ratatui client".to_owned(),
        }]);
        // A committed decision disarms unconditionally (see `approve_selected`).
        self.armed_approval_id = None;
    }

    pub(crate) fn select_next_approval(&mut self) {
        // Changing the selection disarms: arming is bound to the previously
        // selected approval and must not carry to the newly selected one. (The
        // id-keyed match in the 'a' handler already makes this fail-safe; the
        // explicit clear keeps the field from going stale.)
        self.armed_approval_id = None;
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
        // Changing the selection disarms (see `select_next_approval`).
        self.armed_approval_id = None;
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

    fn select_next_overlay_item(&mut self) {
        let items = self.overlay_items();
        if items.is_empty() {
            self.overlay_selected_index = 0;
            return;
        }
        self.overlay_selected_index = (self.overlay_selected_index + 1) % items.len();
        self.sync_overlay_selection();
    }

    fn select_previous_overlay_item(&mut self) {
        let items = self.overlay_items();
        if items.is_empty() {
            self.overlay_selected_index = 0;
            return;
        }
        self.overlay_selected_index = if self.overlay_selected_index == 0 {
            items.len() - 1
        } else {
            self.overlay_selected_index - 1
        };
        self.sync_overlay_selection();
    }

    fn sync_overlay_selection(&mut self) {
        let items = self.overlay_items();
        if items.is_empty() {
            self.overlay_selected_index = 0;
            self.overlay_scroll = 0;
            return;
        }
        self.overlay_selected_index = self.overlay_selected_index.min(items.len() - 1);
        self.clamp_overlay_scroll();
        match self.active_overlay {
            Some(ActiveOverlay::Runs) => {
                let title = &items[self.overlay_selected_index].title;
                self.selected_run_index =
                    self.run_records.iter().position(|run| run.run_id == *title);
                self.auto_select_latest_run = false;
            }
            Some(ActiveOverlay::Approvals) => {
                let title = &items[self.overlay_selected_index].title;
                self.selected_approval_index = self
                    .pending_approvals
                    .iter()
                    .position(|approval| approval.id == *title);
            }
            _ => {}
        }
    }

    fn clamp_overlay_scroll(&mut self) {
        let len = self.overlay_items().len() as u16;
        if len == 0 {
            self.overlay_scroll = 0;
            return;
        }
        self.overlay_scroll = self.overlay_scroll.min(len.saturating_sub(1));
        if (self.overlay_selected_index as u16) < self.overlay_scroll {
            self.overlay_scroll = self.overlay_selected_index as u16;
        }
        let visible_window = 10_u16;
        if (self.overlay_selected_index as u16) >= self.overlay_scroll + visible_window {
            self.overlay_scroll = (self.overlay_selected_index as u16)
                .saturating_sub(visible_window.saturating_sub(1));
        }
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
        let message =
            string_data(event, "message").unwrap_or_else(|| "Approval requested.".to_owned());
        let tool = first_string_data(event, &["tool", "tool_name", "name"]);
        let target = first_string_data(event, &["target", "path", "file"]);
        let reason = first_string_data(event, &["reason", "description"]);
        Self {
            id: string_data(event, "approval_id").unwrap_or_else(|| {
                fallback_approval_id(tool.as_deref(), target.as_deref(), &message)
            }),
            message,
            origin: first_string_data(
                event,
                &["origin", "source", "backend", "provider_id", "provider"],
            ),
            tool,
            target,
            capability: string_data(event, "capability"),
            resource: string_data(event, "resource"),
            scope: first_scalar_data(event, &["scope", "operation_scope"]),
            size: first_scalar_data(event, &["size", "diff_size", "bytes"]),
            receipt_id: first_string_data(event, &["receipt_id", "receipt"]),
            expires_at: string_data(event, "expires_at"),
            reason,
            risk: string_data(event, "risk").or_else(|| string_data(event, "risk_text")),
            command: first_string_data(event, &["command", "shell_command", "bash_command"]),
            preview: first_string_data(
                event,
                &["preview", "diff", "patch", "command_preview", "text"],
            ),
            permission_mode: first_string_data(event, &["permission_mode", "mode"]),
        }
    }

    fn request_text(&self, latest_receipt: Option<&str>) -> String {
        let mut lines = vec![
            format!("Review required: {}", self.subject_label()),
            format!("Origin: {}", self.origin_label()),
            format!("Approval: {}", self.id_label()),
        ];
        push_optional_line(&mut lines, "Tool", self.tool.as_deref());
        push_optional_line(&mut lines, "Target", self.target.as_deref());
        push_optional_line(&mut lines, "Command", self.command.as_deref());
        push_optional_line(
            &mut lines,
            "Receipt",
            self.receipt_id.as_deref().or(latest_receipt),
        );
        push_optional_line(&mut lines, "Reason", self.reason.as_deref());
        if self.risk.as_deref().is_some_and(is_high_risk_text) {
            lines.push("Risk: high - review before deciding".to_owned());
        }
        lines.push("Actions: [a] approve  [d] deny  [Esc] defer".to_owned());
        lines.join("\n")
    }

    fn preview_text(&self, latest_receipt: Option<&str>) -> String {
        self.modal_text(1, 1, latest_receipt)
    }

    fn modal_text(&self, position: usize, total: usize, latest_receipt: Option<&str>) -> String {
        let origin = self.origin_label();
        let mut lines = vec![
            "Review required".to_owned(),
            format!("Origin: {origin}"),
            format!("Queue: {position} of {} pending", total.max(1)),
            format!("Action: {}", self.action_label()),
            format!("Risk: {}", self.risk_label()),
            format!("What: {}", self.subject_label()),
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
        lines.push(String::new());
        lines.push("Source request".to_owned());
        push_optional_line(&mut lines, "Tool", self.tool.as_deref());
        push_optional_line(&mut lines, "Target", self.target.as_deref());
        push_optional_line(&mut lines, "Command", self.command.as_deref());
        push_optional_line(&mut lines, "Reason", self.reason.as_deref());
        if self.has_governance_context() {
            lines.push(String::new());
            lines.push("Craik context".to_owned());
        }
        push_optional_line(&mut lines, "Capability", self.capability.as_deref());
        push_optional_line(&mut lines, "Resource", self.resource.as_deref());
        push_optional_line(&mut lines, "Scope", self.scope.as_deref());
        push_optional_line(&mut lines, "Size", self.size.as_deref());
        push_optional_line(&mut lines, "Risk", self.risk.as_deref());
        push_optional_line(&mut lines, "Receipt", self.receipt_id.as_deref());
        push_optional_line(&mut lines, "Expires", self.expires_at.as_deref());
        if self.risk.as_deref().is_some_and(is_high_risk_text) {
            lines.push(
                "Warning: high-risk approval; review target and receipt before deciding".to_owned(),
            );
        }
        push_optional_line(&mut lines, "Latest receipt", latest_receipt);
        if let Some(preview) = self.preview.as_deref() {
            lines.push(String::new());
            lines.push("Preview".to_owned());
            lines.extend(preview.lines().map(|line| format!("  {line}")));
        } else if let Some(command) = self.command.as_deref() {
            lines.push(String::new());
            lines.push("Preview".to_owned());
            lines.push(format!("  $ {command}"));
        }
        lines.push(String::new());
        if self.is_high_risk() {
            lines.push(
                "Actions: [a] approve (press twice to confirm)  [d] deny  [Esc] defer".to_owned(),
            );
        } else {
            lines.push("Actions: [a] approve  [d] deny  [Esc] defer".to_owned());
        }
        lines.join("\n")
    }

    fn action_label(&self) -> String {
        match (
            self.tool.as_deref(),
            self.target.as_deref(),
            self.command.as_deref(),
        ) {
            (Some(tool), Some(target), _) => format!("{tool} on {target}"),
            (Some(tool), None, Some(command)) => format!("{tool}: {command}"),
            (Some(tool), None, None) => tool.to_owned(),
            (None, Some(target), _) => format!("Access {target}"),
            (None, None, Some(command)) => format!("Run {command}"),
            (None, None, None) => self.subject_label().to_owned(),
        }
    }

    /// A destructive / high-risk approval that must keep an explicit
    /// confirmation gate even under the single-press keymap. Triggered by
    /// EITHER signal:
    ///   - `bypassPermissions` mode -- the most dangerous mode, so it is always
    ///     high-risk regardless of the free-text risk string (which a backend
    ///     may leave benign or empty); OR
    ///   - the `is_high_risk_text` needle heuristic the modal already uses to
    ///     render the "Warning: high-risk approval" affordance.
    fn is_high_risk(&self) -> bool {
        self.is_bypass_permissions() || self.risk.as_deref().is_some_and(is_high_risk_text)
    }

    /// Whether this approval was raised under `bypassPermissions` mode.
    fn is_bypass_permissions(&self) -> bool {
        self.permission_mode
            .as_deref()
            .is_some_and(|mode| mode.eq_ignore_ascii_case("bypassPermissions"))
    }

    fn risk_label(&self) -> &str {
        if self.risk.as_deref().is_some_and(is_high_risk_text) {
            "high - review target and receipt"
        } else {
            self.risk.as_deref().unwrap_or("not specified")
        }
    }

    fn origin_label(&self) -> &str {
        match self.origin.as_deref() {
            Some("claude-code" | "claude_code" | "claude code") => "via Claude Code",
            Some("craik" | "craik governance" | "gateway") => "craik governance",
            Some(origin) => origin,
            None => "craik governance",
        }
    }

    fn id_label(&self) -> &str {
        if self.id.is_empty() {
            "unknown"
        } else {
            self.id.as_str()
        }
    }

    fn subject_label(&self) -> &str {
        self.target
            .as_deref()
            .or(self.command.as_deref())
            .or(self.resource.as_deref())
            .or(self.tool.as_deref())
            .or(self.capability.as_deref())
            .unwrap_or("approval request")
    }

    fn has_governance_context(&self) -> bool {
        self.capability.is_some()
            || self.resource.is_some()
            || self.scope.is_some()
            || self.size.is_some()
            || self.risk.is_some()
            || self.receipt_id.is_some()
            || self.expires_at.is_some()
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

    fn receipt_overlay_detail(&self, receipt_id: &str) -> String {
        let mut lines = vec![
            "Receipt".to_owned(),
            format!("ID: {receipt_id}"),
            format!("Run: {}", self.run_id),
            format!("Status: {}", self.status.as_deref().unwrap_or("active")),
        ];
        push_optional_line(&mut lines, "Task", self.task_id.as_deref());
        push_optional_line(&mut lines, "Provider", self.provider.as_deref());
        push_optional_line(&mut lines, "Model", self.model.as_deref());
        push_matching_detail_section(
            &mut lines,
            "Receipt detail",
            &self.receipt_details,
            receipt_id,
        );
        push_detail_section(&mut lines, "Provenance", &self.provenance);
        push_detail_section(&mut lines, "Tools", &self.tools);
        push_detail_section(&mut lines, "Files", &self.files);
        push_detail_section(&mut lines, "Commands", &self.commands);
        push_detail_section(&mut lines, "Approvals", &self.approvals);
        lines.join("\n")
    }
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

fn summarize_tool_event(
    event: &GatewayEvent,
    tool: &str,
    fallback_message: Option<&str>,
) -> String {
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
    // Only the API adapters carry a free-text message; CLI/typed adapters
    // describe the call via command/target alone.
    if let Some(message) = fallback_message {
        lines.push(format!("Detail: {message}"));
    }
    lines.join("\n")
}

fn summarize_receipt_marker(event: &GatewayEvent) -> String {
    // Differentiate evidence lines by the typed governance identity carried on
    // the event envelope/data: vendor×surface `source`, `execution` posture,
    // and the `decision (decided_by)` attribution. Without these, every receipt
    // collapsed to an identical generic string (the duplicate-evidence bug).
    let mut parts = vec![event.source.clone()];
    if let Some(execution) = string_data(event, "execution") {
        parts.push(execution);
    }
    if let Some(decision) = string_data(event, "decision") {
        match string_data(event, "decided_by") {
            Some(decided_by) => parts.push(format!("{decision} ({decided_by})")),
            None => parts.push(decision),
        }
    }
    format!(
        "Saved evidence · {}. Ctrl-E opens details.",
        parts.join(" · ")
    )
}

fn string_data(event: &GatewayEvent, key: &str) -> Option<String> {
    event
        .data
        .get(key)
        .and_then(|value| value.as_str())
        .filter(|value| !value.trim().is_empty())
        .map(str::to_owned)
}

fn next_permission_mode(current: Option<&str>) -> &'static str {
    let current = match current {
        Some("default") | None => "ask",
        Some(value) => value,
    };
    let index = PERMISSION_MODE_CYCLE
        .iter()
        .position(|mode| *mode == current)
        .unwrap_or(0);
    PERMISSION_MODE_CYCLE[(index + 1) % PERMISSION_MODE_CYCLE.len()]
}

fn selected_slash_completion_is_executable(input: &str) -> bool {
    let words = input.split_whitespace().collect::<Vec<_>>();
    match words.as_slice() {
        ["/model", "set", selector, ..] => selector.contains('/'),
        ["/mode", _] | ["/effort", _] | ["/theme", _] => true,
        [command] => !matches!(
            *command,
            "/model" | "/run" | "/policy" | "/migrate" | "/agent" | "/session"
        ),
        _ => false,
    }
}

fn display_permission_mode(mode: &str) -> &str {
    if mode == "default" { "ask" } else { mode }
}

fn first_string_data(event: &GatewayEvent, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| string_data(event, key))
}

fn scalar_data(event: &GatewayEvent, key: &str) -> Option<String> {
    let value = event.data.get(key)?;
    if let Some(text) = value.as_str() {
        return (!text.trim().is_empty()).then(|| text.to_owned());
    }
    if value.is_number() || value.is_boolean() {
        return Some(value.to_string());
    }
    None
}

fn first_scalar_data(event: &GatewayEvent, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| scalar_data(event, key))
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

fn filter_overlay_items(items: Vec<OverlayItem>, query: &str) -> Vec<OverlayItem> {
    let query = query.trim().to_lowercase();
    if query.is_empty() {
        return items;
    }
    items
        .into_iter()
        .filter(|item| {
            item.title.to_lowercase().contains(&query)
                || item.summary.to_lowercase().contains(&query)
                || item.detail.to_lowercase().contains(&query)
        })
        .collect()
}

fn join_recent(values: &[String]) -> String {
    if values.is_empty() {
        return "None".to_owned();
    }
    values
        .iter()
        .rev()
        .take(8)
        .map(|value| format!("- {value}"))
        .collect::<Vec<_>>()
        .join("\n")
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

fn push_matching_detail_section(
    lines: &mut Vec<String>,
    label: &str,
    values: &[String],
    needle: &str,
) {
    let matching = values
        .iter()
        .filter(|value| value.contains(needle))
        .cloned()
        .collect::<Vec<_>>();
    if matching.is_empty() {
        return;
    }
    push_detail_section(lines, label, &matching);
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

fn fallback_approval_id(tool: Option<&str>, target: Option<&str>, message: &str) -> String {
    let mut seed = String::new();
    for value in [tool, target, Some(message)].into_iter().flatten() {
        if !seed.is_empty() {
            seed.push('_');
        }
        seed.push_str(value);
    }
    let sanitized = seed
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>();
    let suffix = sanitized
        .split('_')
        .filter(|part| !part.is_empty())
        .take(8)
        .collect::<Vec<_>>()
        .join("_");
    if suffix.is_empty() {
        "approval_runtime_request".to_owned()
    } else {
        format!("approval_{suffix}")
    }
}

fn should_hide_transcript_event(event: &GatewayEvent) -> bool {
    if matches!(
        event
            .data
            .get("transcript_visibility")
            .and_then(|value| value.as_str()),
        Some("hidden" | "approval" | "state")
    ) {
        return true;
    }
    first_string_data(event, &["text", "message"])
        .as_deref()
        .is_some_and(|message| is_low_value_lifecycle_message(event, message))
}

fn should_show_progress_message(event: &GatewayEvent, message: &str) -> bool {
    if event
        .data
        .get("transcript_visibility")
        .and_then(|value| value.as_str())
        == Some("visible")
    {
        return true;
    }
    if event
        .data
        .get("level")
        .and_then(|value| value.as_str())
        .is_some_and(|level| matches!(level, "warning" | "error"))
    {
        return true;
    }
    let normalized = normalize_transcript_text(message);
    let lower = normalized.to_ascii_lowercase();
    lower.contains("warning")
        || lower.contains("error")
        || lower.contains("failed")
        || lower.contains("blocked")
        || lower.contains("denied")
}

fn run_output_transcript_text(summary: &str) -> Option<String> {
    // Phase 4 strips contract envelopes at the source (every adapter runs
    // `strip_contract_envelopes` before emitting text), so the TUI no longer
    // needs to defensively scrub contract sections out of `run.output`
    // summaries. A summary that still parses as a structured-output contract is
    // reduced to its display text; everything else passes through verbatim.
    let trimmed = summary.trim();
    if trimmed.is_empty() {
        return None;
    }
    if !looks_like_structured_output_contract(trimmed) {
        return Some(trimmed.to_owned());
    }
    json_value_from_text(trimmed)
        .as_ref()
        .and_then(extract_contract_display_text)
        .or_else(|| text_before_contract_marker(trimmed))
}

fn looks_like_structured_output_contract(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    text.starts_with('{')
        || text.starts_with('[')
        || text.starts_with("```")
        || lower.contains("output contract")
        || lower.contains("craik contract output")
        || lower.contains("**craik.")
        || lower.contains("\"schema\"")
}

fn json_value_from_text(text: &str) -> Option<Value> {
    let trimmed = text.trim();
    let unfenced = trimmed
        .strip_prefix("```json")
        .or_else(|| trimmed.strip_prefix("```"))
        .and_then(|value| value.strip_suffix("```"))
        .map(str::trim)
        .unwrap_or(trimmed);
    serde_json::from_str::<Value>(unfenced)
        .ok()
        .or_else(|| parse_embedded_json(unfenced, '{', '}'))
        .or_else(|| parse_embedded_json(unfenced, '[', ']'))
}

fn parse_embedded_json(text: &str, open: char, close: char) -> Option<Value> {
    let start = text.find(open)?;
    let end = text.rfind(close)?;
    if end <= start {
        return None;
    }
    serde_json::from_str::<Value>(&text[start..=end]).ok()
}

fn extract_contract_display_text(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => displayable_contract_text(text),
        Value::Array(items) => items.iter().find_map(extract_contract_display_text),
        Value::Object(object) => {
            for key in ["observed_output", "payload", "output"] {
                if let Some(text) = object.get(key).and_then(extract_contract_display_text) {
                    return Some(text);
                }
            }
            if let Some(outputs) = object.get("run_outputs").and_then(Value::as_array) {
                for output in outputs {
                    if let Some(text) = output
                        .get("observed_output")
                        .and_then(extract_contract_display_text)
                    {
                        return Some(text);
                    }
                    if let Some(text) = output
                        .get("summary")
                        .and_then(Value::as_str)
                        .and_then(displayable_contract_text)
                    {
                        return Some(text);
                    }
                }
            }
            if let Some(content) = object.get("content")
                && let Some(text) = extract_contract_display_text(content)
            {
                return Some(text);
            }
            for key in [
                "final_answer",
                "answer",
                "text",
                "response",
                "result",
                "summary",
                "message",
            ] {
                if let Some(text) = object
                    .get(key)
                    .and_then(Value::as_str)
                    .and_then(displayable_contract_text)
                {
                    return Some(text);
                }
            }
            None
        }
        _ => None,
    }
}

fn displayable_contract_text(text: &str) -> Option<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() || looks_like_structured_output_contract(trimmed) {
        None
    } else {
        Some(trimmed.to_owned())
    }
}

fn text_before_contract_marker(text: &str) -> Option<String> {
    let lower = text.to_ascii_lowercase();
    let marker = lower
        .find("output contract")
        .or_else(|| lower.find("craik contract output"))
        .or_else(|| lower.find("**craik."))
        .or_else(|| lower.find("craik."))?;
    let prefix = text[..marker].trim();
    if prefix.is_empty()
        || prefix.starts_with('{')
        || prefix.starts_with('[')
        || prefix.starts_with("```")
    {
        None
    } else {
        Some(prefix.to_owned())
    }
}

fn is_low_value_lifecycle_message(event: &GatewayEvent, message: &str) -> bool {
    if event
        .data
        .get("transcript_visibility")
        .and_then(|value| value.as_str())
        == Some("visible")
    {
        return false;
    }
    if message_has_attention(message) {
        return false;
    }
    let normalized = normalize_transcript_text(message);
    let lower = normalized.to_ascii_lowercase();
    if lower.starts_with("claude code event:")
        || lower.starts_with("claude code system event:")
        || lower == "claude code is still running; waiting for stream output."
        || lower == "claude code returned a final result."
        || lower.contains("thinking_tokens")
        || lower.contains("rate_limit_event")
    {
        return true;
    }
    let kind = event
        .data
        .get("kind")
        .and_then(|value| value.as_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    matches!(kind.as_str(), "event" | "system" | "status" | "heartbeat")
}

fn message_has_attention(message: &str) -> bool {
    let lower = normalize_transcript_text(message).to_ascii_lowercase();
    lower.contains("warning")
        || lower.contains("error")
        || lower.contains("failed")
        || lower.contains("blocked")
        || lower.contains("denied")
        || lower.contains("approval")
}

fn recent_transcript_body_matches(entries: &[TranscriptEntry], body: &str) -> bool {
    let normalized = normalize_transcript_text(body);
    if normalized.is_empty() {
        return false;
    }
    entries
        .iter()
        .rev()
        .take(6)
        .any(|entry| normalize_transcript_text(&entry.body) == normalized)
}

fn recent_transcript_entry_matches(
    entries: &[TranscriptEntry],
    kind: TranscriptKind,
    title: &str,
    body: &str,
) -> bool {
    let normalized_title = normalize_transcript_text(title);
    let normalized_body = normalize_transcript_text(body);
    if normalized_body.is_empty() {
        return false;
    }
    entries.iter().rev().take(6).any(|entry| {
        entry.kind == kind
            && normalize_transcript_text(&entry.title) == normalized_title
            && normalize_transcript_text(&entry.body) == normalized_body
    })
}

fn append_grouped_tool_transcript(
    entries: &mut [TranscriptEntry],
    kind: TranscriptKind,
    title: &str,
    body: &str,
) -> bool {
    let Some(last) = entries.last_mut() else {
        return false;
    };
    if last.kind != kind
        || normalize_transcript_text(&last.title) != normalize_transcript_text(title)
    {
        return false;
    }

    let grouped = grouped_tool_transcript_body(title, &last.body, body);
    last.update_body(&grouped);
    true
}

fn grouped_tool_transcript_body(title: &str, existing_body: &str, next_body: &str) -> String {
    let previous_count = grouped_tool_event_count(existing_body).unwrap_or(1);
    let count = previous_count.saturating_add(1);
    let latest_detail = tool_detail_line(next_body).unwrap_or_else(|| compact_text(next_body, 120));
    let mut details = grouped_tool_recent_details(existing_body);
    if details.is_empty() {
        details.push(CountedDetail {
            text: tool_detail_line(existing_body)
                .unwrap_or_else(|| compact_text(existing_body, 120)),
            count: 1,
        });
    }
    push_counted_detail(&mut details, latest_detail.clone());

    let mut lines = vec![format!("Tool: {title}"), format!("Events: {count}")];
    lines.extend(tool_context_lines(next_body));
    lines.push(format!("Latest: {latest_detail}"));
    lines.push("Recent:".to_owned());
    for detail in details.iter().rev().take(4).rev() {
        if detail.count > 1 {
            lines.push(format!("- {} (x{})", detail.text, detail.count));
        } else {
            lines.push(format!("- {}", detail.text));
        }
    }
    lines.join("\n")
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct CountedDetail {
    text: String,
    count: usize,
}

fn grouped_tool_event_count(body: &str) -> Option<usize> {
    body.lines()
        .find_map(|line| line.strip_prefix("Events: ")?.parse::<usize>().ok())
}

fn grouped_tool_recent_details(body: &str) -> Vec<CountedDetail> {
    body.lines()
        .filter_map(|line| parse_counted_detail(line.strip_prefix("- ")?))
        .collect()
}

fn parse_counted_detail(value: &str) -> Option<CountedDetail> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return None;
    }
    if let Some((text, count_text)) = trimmed.rsplit_once(" (x")
        && let Some(count_text) = count_text.strip_suffix(')')
        && let Ok(count) = count_text.parse::<usize>()
    {
        return Some(CountedDetail {
            text: text.to_owned(),
            count,
        });
    }
    Some(CountedDetail {
        text: trimmed.to_owned(),
        count: 1,
    })
}

fn push_counted_detail(details: &mut Vec<CountedDetail>, detail: String) {
    if detail.trim().is_empty() {
        return;
    }
    if let Some(existing) = details.iter_mut().find(|existing| {
        normalize_transcript_text(&existing.text) == normalize_transcript_text(&detail)
    }) {
        existing.count = existing.count.saturating_add(1);
        return;
    }
    details.push(CountedDetail {
        text: detail,
        count: 1,
    });
    let overflow = details.len().saturating_sub(4);
    if overflow > 0 {
        details.drain(0..overflow);
    }
}

fn tool_detail_line(body: &str) -> Option<String> {
    body.lines()
        .find_map(|line| line.strip_prefix("Detail: "))
        .or_else(|| body.lines().find_map(|line| line.strip_prefix("Latest: ")))
        .map(str::to_owned)
}

fn tool_context_lines(body: &str) -> Vec<String> {
    body.lines()
        .filter(|line| {
            line.starts_with("Provider: ")
                || line.starts_with("Family: ")
                || line.starts_with("Model: ")
                || line.starts_with("Response: ")
                || line.starts_with("Command: ")
                || line.starts_with("Target: ")
        })
        .map(str::to_owned)
        .collect()
}

fn normalize_transcript_text(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
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

fn receipt_detail_from_event(event: &GatewayEvent) -> String {
    let mut parts = Vec::new();
    if let Some(id) = string_data(event, "receipt_id") {
        parts.push(format!("id={id}"));
    }
    if let Some(run_id) = event.run_id.as_deref() {
        parts.push(format!("run={run_id}"));
    }
    if let Some(task_id) = event.task_id.as_deref() {
        parts.push(format!("task={task_id}"));
    }
    parts.push(format!("source={}", event.source));
    if let Some(purpose) = string_data(event, "purpose") {
        parts.push(format!("purpose={purpose}"));
    }
    if let Some(execution) = string_data(event, "execution") {
        parts.push(format!("execution={execution}"));
    }
    if let Some(mode) = string_data(event, "mode") {
        parts.push(format!("mode={mode}"));
    }
    if let Some(decision) = string_data(event, "decision") {
        parts.push(format!("decision={decision}"));
    }
    if let Some(decided_by) = string_data(event, "decided_by") {
        parts.push(format!("decided_by={decided_by}"));
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
        count += transcript_entry_visual_line_count(entry);
    }
    count.min(u16::MAX as usize) as u16
}

fn transcript_entry_index_for_scroll(entries: &[TranscriptEntry], scroll: u16) -> usize {
    let mut remaining = scroll as usize;
    for (index, entry) in entries.iter().rev().enumerate() {
        let lines = transcript_entry_visual_line_count(entry);
        if remaining <= lines {
            return entries.len().saturating_sub(index + 1);
        }
        remaining = remaining.saturating_sub(lines);
    }
    0
}

fn transcript_entry_visual_line_count(entry: &TranscriptEntry) -> usize {
    let separator = if matches!(
        entry.kind,
        TranscriptKind::System
            | TranscriptKind::Progress
            | TranscriptKind::Tool
            | TranscriptKind::File
            | TranscriptKind::Command
            | TranscriptKind::Receipt
    ) {
        0
    } else {
        1
    };
    1 + entry.body.lines().count().max(1) + separator
}

#[cfg(test)]
mod tests {
    use super::{ActiveOverlay, InteractiveApp, LoopAction, RunRecord, export_file_stem};
    use crate::backend::{WorkerMessage, format_backend_closed};
    use crate::input::SlashHint;
    use crate::transcript::TranscriptKind;
    use craik_tui_rs::{ActivityItem, GatewayEvent};
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
    fn assistant_text_then_completed_does_not_report_no_model_output() {
        // Typed contract: the model's text arrives as `assistant_text`. It must
        // count as model output so `run.completed` does not spuriously report
        // "No model output" — the live anthropic-cli path emits no `run.output`,
        // only `assistant_text`.
        let assistant = GatewayEvent {
            event_type: "assistant_text".to_owned(),
            source: "anthropic-cli".to_owned(),
            created_at: None,
            run_id: Some("run_text".to_owned()),
            task_id: None,
            data: json!({"text": "Here is the repo overview."}),
        };
        let completed = GatewayEvent {
            event_type: "run.completed".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_text".to_owned()),
            task_id: None,
            data: json!({"status": "completed"}),
        };
        let mut app = InteractiveApp::for_test_with_messages([
            WorkerMessage::Event(assistant),
            WorkerMessage::Event(completed),
        ]);
        app.in_flight = true;

        app.drain_worker();

        assert!(
            !app.state.outputs.is_empty(),
            "assistant_text must count as model output"
        );
        assert!(
            app.transcript
                .iter()
                .all(|entry| entry.title != "No model output"),
            "assistant_text output must suppress the No model output flag"
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
                .any(|entry| entry.title == "Approval approved")
        );
        assert!(
            app.transcript
                .iter()
                .all(|entry| entry.title != "Run completed")
        );
        assert!(
            app.transcript
                .iter()
                .all(|entry| entry.title != "Run state")
        );
        assert!(
            app.transcript
                .iter()
                .all(|entry| entry.title != "Submitted")
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
                source: "gateway".to_owned(),
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
    fn distinct_receipts_render_distinct_evidence_lines() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        let first = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            source: "anthropic-api".to_owned(),
            created_at: None,
            run_id: Some("run_a".to_owned()),
            task_id: Some("task_a".to_owned()),
            data: json!({
                "receipt_id": "receipt_a",
                "purpose": "execution",
                "execution": "craik",
                "mode": "default",
                "decision": "allow",
                "decided_by": "operator"
            }),
        };
        let second = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            source: "google-cli".to_owned(),
            created_at: None,
            run_id: Some("run_b".to_owned()),
            task_id: Some("task_b".to_owned()),
            data: json!({
                "receipt_id": "receipt_b",
                "purpose": "execution",
                "execution": "delegated-observed",
                "mode": "default",
                "decision": "allow",
                "decided_by": "bypass"
            }),
        };

        app.record_event(&first);
        app.record_event(&second);

        let evidence: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Receipt)
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(evidence.len(), 2, "two receipts render two evidence lines");
        assert_ne!(
            evidence[0], evidence[1],
            "receipts that differ by source/execution/decided_by must render distinct lines"
        );
        assert!(evidence[0].contains("anthropic-api"));
        assert!(evidence[0].contains("craik"));
        assert!(evidence[0].contains("operator"));
        assert!(evidence[1].contains("google-cli"));
        assert!(evidence[1].contains("delegated-observed"));
        assert!(evidence[1].contains("bypass"));
    }

    #[test]
    fn tool_used_without_message_still_renders_from_command_or_target() {
        // The typed API adapters emit `tool.used` with command/target but no
        // `message`; the chat lane must still show the tool activity.
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&GatewayEvent {
            event_type: "tool.used".to_owned(),
            source: "anthropic-api".to_owned(),
            created_at: None,
            run_id: Some("run_tool".to_owned()),
            task_id: Some("task_tool".to_owned()),
            data: json!({"tool": "Read", "target": "src/lib.rs"}),
        });

        let tools: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| {
                entry.kind == TranscriptKind::Tool || entry.kind == TranscriptKind::Command
            })
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(
            tools.len(),
            1,
            "tool.used without message must still render"
        );
        assert!(
            tools[0].contains("src/lib.rs"),
            "rendered tool line should carry the target: {:?}",
            tools[0]
        );
    }

    #[test]
    fn assistant_text_event_renders_assistant_entry() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&GatewayEvent {
            event_type: "assistant_text".to_owned(),
            source: "anthropic-api".to_owned(),
            created_at: None,
            run_id: Some("run_text".to_owned()),
            task_id: Some("task_text".to_owned()),
            data: json!({"text": "I can see the repo."}),
        });

        let assistant: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Assistant)
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(assistant, vec!["I can see the repo."]);
    }

    #[test]
    fn coalesced_assistant_text_supersedes_rather_than_stacks() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        for snapshot in ["Reading", "Reading the repo", "Reading the repo now."] {
            app.record_event(&GatewayEvent {
                event_type: "assistant_text".to_owned(),
                source: "anthropic-api".to_owned(),
                created_at: None,
                run_id: Some("run_grow".to_owned()),
                task_id: Some("task_grow".to_owned()),
                data: json!({"text": snapshot}),
            });
        }

        let assistant: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Assistant)
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(
            assistant,
            vec!["Reading the repo now."],
            "growing coalesced assistant text supersedes earlier snapshots"
        );
    }

    #[test]
    fn repeated_progress_for_one_run_collapses_to_single_updating_line() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        for message in [
            "Claude Code is starting up.",
            "Claude Code is reading files.",
            "Claude Code is editing files.",
        ] {
            app.record_event(&GatewayEvent {
                event_type: "run.progress".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: Some("run_progress".to_owned()),
                task_id: None,
                data: json!({"message": message, "transcript_visibility": "visible"}),
            });
        }

        let progress: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Progress)
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(
            progress,
            vec!["Claude Code is editing files."],
            "repeated progress for one run supersedes earlier updates in place"
        );
    }

    #[test]
    fn progress_for_new_run_does_not_supersede_prior_run() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&GatewayEvent {
            event_type: "run.progress".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_a".to_owned()),
            task_id: None,
            data: json!({"message": "Run A progress.", "transcript_visibility": "visible"}),
        });
        app.record_event(&GatewayEvent {
            event_type: "run.progress".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_b".to_owned()),
            task_id: None,
            data: json!({"message": "Run B progress.", "transcript_visibility": "visible"}),
        });

        let progress: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Progress)
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(
            progress,
            vec!["Run A progress.", "Run B progress."],
            "a new run's progress starts a fresh line rather than overwriting the prior run"
        );
    }

    #[test]
    fn progress_does_not_supersede_after_a_non_progress_entry_intervenes() {
        // Pins the TAIL guard in `supersede_progress`: a tracked progress entry
        // may only be superseded in place while it is still the transcript tail.
        // Once a non-progress entry for the same run is appended, the earlier
        // progress entry is buried and a later progress update must APPEND a
        // fresh line, never overwrite the buried one. (Removing the
        // `*index + 1 == len()` guard makes this test fail.)
        let mut app = InteractiveApp::for_test_with_messages([]);

        // 1) First progress for run X -> progress entry at the tail.
        app.record_event(&GatewayEvent {
            event_type: "run.progress".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_x".to_owned()),
            task_id: None,
            data: json!({"message": "First progress.", "transcript_visibility": "visible"}),
        });

        // 2) A NON-progress entry for the SAME run X buries the progress entry
        //    (it is no longer the transcript tail).
        app.record_event(&GatewayEvent {
            event_type: "tool.used".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_x".to_owned()),
            task_id: None,
            data: json!({"tool": "Read", "message": "Read src/lib.rs."}),
        });
        assert!(
            app.transcript
                .last()
                .is_some_and(|entry| entry.kind != TranscriptKind::Progress),
            "the tool.used entry must be the tail, burying the earlier progress entry"
        );

        // 3) Another progress for run X -> must APPEND, not overwrite the buried
        //    earlier progress entry.
        app.record_event(&GatewayEvent {
            event_type: "run.progress".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_x".to_owned()),
            task_id: None,
            data: json!({"message": "Second progress.", "transcript_visibility": "visible"}),
        });

        let progress: Vec<&str> = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Progress)
            .map(|entry| entry.body.as_str())
            .collect();
        assert_eq!(
            progress,
            vec!["First progress.", "Second progress."],
            "a buried progress entry must not be superseded; the later update appends a fresh line"
        );
    }

    #[test]
    fn approval_request_tracks_pending_state_and_actions() {
        let receipt = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({"receipt_id": "receipt_before_approval"}),
        };
        let approval = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
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
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
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
        assert!(entry.body.contains("Review required: src/lib.rs"));
        assert!(entry.body.contains("Approval: approval_edit_123"));
        assert!(entry.body.contains("Tool: Edit"));
        assert!(entry.body.contains("Target: src/lib.rs"));
        assert!(entry.body.contains("Reason: normalize event mapping"));
        assert!(entry.body.contains("Receipt: receipt_before_approval"));
        assert!(entry.body.contains("[a] approve"));
        assert!(entry.body.contains("[d] deny"));
    }

    #[test]
    fn approval_overlay_surfaces_real_payload_fields_and_queue_position() {
        let first = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_bash_1",
                "message": "Run cargo test?",
                "backend": "claude-code",
                "tool": "Bash",
                "command": "cargo test",
                "capability": "command",
                "scope": "workspace",
                "risk": "executes command"
            }),
        };
        let second = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_edit_2",
                "message": "Edit app.rs?",
                "origin": "craik governance",
                "tool": "Edit",
                "target": "crates/craik-tui-rs/src/app.rs",
                "resource": "crates/craik-tui-rs/src/app.rs",
                "capability": "file-write",
                "scope": "workspace",
                "size": 128,
                "receipt_id": "receipt_approval_2",
                "expires_at": "2026-05-29T12:00:00Z",
                "reason": "apply approval modal polish",
                "risk": "writes source files",
                "preview": "- old\n+ new"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.state.receipt_ids.push("receipt_latest".to_owned());

        app.record_event(&first);
        app.record_event(&second);
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::CONTROL));

        let overlay = app.overlay_text().expect("approval overlay");
        assert!(overlay.contains("Queue: 2 of 2 pending"));
        assert!(overlay.contains("Origin: craik governance"));
        assert!(overlay.contains("Action: Edit on crates/craik-tui-rs/src/app.rs"));
        assert!(overlay.contains("Risk: high - review target and receipt"));
        assert!(overlay.contains("What: crates/craik-tui-rs/src/app.rs"));
        assert!(overlay.contains("Source request"));
        assert!(overlay.contains("Craik context"));
        assert!(overlay.contains("Capability: file-write"));
        assert!(overlay.contains("Resource: crates/craik-tui-rs/src/app.rs"));
        assert!(overlay.contains("Scope: workspace"));
        assert!(overlay.contains("Size: 128"));
        assert!(overlay.contains("Receipt: receipt_approval_2"));
        assert!(overlay.contains("Expires: 2026-05-29T12:00:00Z"));
        assert!(overlay.contains("Latest receipt: receipt_latest"));
        assert!(overlay.contains("Preview"));
        assert!(overlay.contains("  - old"));
        assert!(overlay.contains("  + new"));
        assert!(overlay.contains("Actions: [a] approve"));
    }

    #[test]
    fn claude_code_approval_modal_uses_only_source_fields_without_governance_section() {
        let approval = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_edit_claude",
                "message": "Claude Code requests approval for `Edit` on `README.md`: write docs",
                "backend": "claude-code",
                "kind": "approval_request",
                "tool": "Edit",
                "target": "README.md",
                "reason": "write docs"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&approval);
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::CONTROL));

        let overlay = app.overlay_text().expect("approval overlay");
        assert!(overlay.contains("Origin: via Claude Code"));
        assert!(overlay.contains("What: README.md"));
        assert!(overlay.contains("Source request"));
        assert!(overlay.contains("Tool: Edit"));
        assert!(overlay.contains("Target: README.md"));
        assert!(overlay.contains("Reason: write docs"));
        assert!(!overlay.contains("Craik context"));
        assert!(!overlay.contains("Capability:"));
        assert!(!overlay.contains("Scope:"));
    }

    #[test]
    fn approval_payload_aliases_preserve_source_fields() {
        let approval = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "message": "Claude Code requests approval for `Bash`: run tests",
                "source": "claude_code",
                "tool_name": "Bash",
                "path": "crates/craik-tui-rs",
                "shell_command": "cargo test",
                "description": "run tests",
                "receipt": "receipt_alias",
                "patch": "+ ok"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&approval);
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::CONTROL));

        let overlay = app.overlay_text().expect("approval overlay");
        assert!(overlay.contains("Origin: via Claude Code"));
        assert!(overlay.contains("Action: Bash on crates/craik-tui-rs"));
        assert!(overlay.contains("Risk: not specified"));
        assert!(overlay.contains("Tool: Bash"));
        assert!(overlay.contains("Target: crates/craik-tui-rs"));
        assert!(overlay.contains("Command: cargo test"));
        assert!(overlay.contains("Reason: run tests"));
        assert!(overlay.contains("Receipt: receipt_alias"));
        assert!(overlay.contains("  + ok"));
    }

    #[test]
    fn claude_code_approval_without_id_still_surfaces_as_pending() {
        let approval = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "message": "Claude Code requests approval for `Bash`: run tests",
                "backend": "claude-code",
                "kind": "approval_request",
                "tool": "Bash",
                "command": "cargo test",
                "reason": "run tests"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&approval);

        assert_eq!(app.pending_approval_count(), 1);
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
        assert_eq!(
            app.latest_pending_approval(),
            Some("approval_bash_claude_code_requests_approval_for_bash_run")
        );
        let overlay = app.overlay_text().expect("approval overlay");
        assert!(overlay.contains("Origin: via Claude Code"));
        assert!(overlay.contains("Command: cargo test"));
        assert!(overlay.contains("Preview"));
        assert!(overlay.contains("  $ cargo test"));
    }

    #[test]
    fn noisy_claude_code_status_events_do_not_crowd_transcript() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        let events = [
            GatewayEvent {
                event_type: "run.event".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"backend": "claude-code", "kind": "event", "message": "Claude Code event: user.", "transcript_visibility": "hidden"}),
            },
            GatewayEvent {
                event_type: "run.progress".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"message": "Claude Code event: user.", "transcript_visibility": "hidden"}),
            },
            GatewayEvent {
                event_type: "assistant_text".to_owned(),
                source: "anthropic-cli".to_owned(),
                created_at: None,
                run_id: Some("run_1".to_owned()),
                task_id: None,
                data: json!({"text": "I can see the repo."}),
            },
            GatewayEvent {
                event_type: "run.progress".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"message": "Claude Code is using `Read` on `README.md`."}),
            },
            GatewayEvent {
                event_type: "tool.used".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({
                    "backend": "claude-code",
                    "kind": "tool_use",
                    "message": "Claude Code is using `Read` on `README.md`.",
                    "tool": "Read",
                    "target": "README.md"
                }),
            },
            GatewayEvent {
                event_type: "run.progress".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"message": "Claude Code is still running; waiting for stream output.", "transcript_visibility": "hidden"}),
            },
            GatewayEvent {
                event_type: "run.progress".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"message": "Claude Code is still running; waiting for stream output."}),
            },
            GatewayEvent {
                event_type: "run.event".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"backend": "claude-code", "kind": "system", "message": "Claude Code system event: thinking_tokens."}),
            },
            GatewayEvent {
                event_type: "run.event".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"backend": "claude-code", "kind": "event", "message": "Claude Code event: rate_limit_event."}),
            },
            GatewayEvent {
                event_type: "run.event".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: None,
                task_id: None,
                data: json!({"backend": "claude-code", "kind": "result", "message": "Claude Code returned a final result.", "text": "Final answer.", "transcript_visibility": "hidden"}),
            },
            GatewayEvent {
                event_type: "run.output".to_owned(),
                source: "gateway".to_owned(),
                created_at: None,
                run_id: Some("run_1".to_owned()),
                task_id: None,
                data: json!({"summary": "Final answer."}),
            },
        ];

        for event in events {
            app.record_event(&event);
        }

        let transcript_text = app
            .transcript
            .iter()
            .map(|entry| format!("{} {}", entry.title, entry.body))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(!transcript_text.contains("Claude Code event: user."));
        assert!(!transcript_text.contains("still running; waiting for stream output"));
        assert!(!transcript_text.contains("Claude Code returned a final result."));
        assert!(!transcript_text.contains("thinking_tokens"));
        assert!(!transcript_text.contains("rate_limit_event"));
        assert_eq!(
            app.transcript
                .iter()
                .filter(|entry| entry.body.contains("I can see the repo."))
                .count(),
            1
        );
        assert_eq!(
            app.transcript
                .iter()
                .filter(|entry| entry.body.contains("Final answer."))
                .count(),
            1
        );
        assert!(transcript_text.contains("Tool: Read"));
        assert!(transcript_text.contains("Target: README.md"));
    }

    #[test]
    fn structured_run_output_contract_does_not_dump_json_into_transcript() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        let raw_contract = json!({
            "schema": "craik.claude_code_run_execution",
            "status": "completed",
            "run_outputs": [
                {
                    "schema": "craik.run_output",
                    "summary": "Reviewed the implementation plan.",
                    "observed_output": {
                        "text": "Reviewed the implementation plan and identified the next phase."
                    }
                }
            ],
            "receipt_ids": ["receipt_1"]
        })
        .to_string();

        app.record_event(&GatewayEvent {
            event_type: "run.output".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_contract".to_owned()),
            task_id: Some("task_contract".to_owned()),
            data: json!({"summary": raw_contract}),
        });

        let transcript_text = app
            .transcript
            .iter()
            .map(|entry| entry.body.as_str())
            .collect::<Vec<_>>()
            .join("\n");
        assert!(transcript_text.contains("Reviewed the implementation plan"));
        assert!(!transcript_text.contains("craik.claude_code_run_execution"));
        assert!(!transcript_text.contains("\"run_outputs\""));
        assert_eq!(app.run_records[0].outputs.len(), 1);
        assert!(app.run_records[0].outputs[0].contains("craik.claude_code_run_execution"));
    }

    #[test]
    fn output_contract_without_display_text_stays_out_of_chat_lane() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&GatewayEvent {
            event_type: "run.output".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_contract".to_owned()),
            task_id: Some("task_contract".to_owned()),
            data: json!({"summary": "{\"schema\":\"craik.output_contract\",\"receipt_ids\":[\"receipt_1\"]}"}),
        });

        assert!(app.transcript.is_empty());
        assert_eq!(app.run_records[0].outputs.len(), 1);
    }

    // Contract-strip chat-lane tests were removed in Phase 6 Task 6.1: the
    // backend now strips contract envelopes at the source (every adapter runs
    // `strip_contract_envelopes`), and the TUI no longer routes assistant
    // content through `run.event`. The `strip_craik_contract_output_sections`
    // band-aid and its helpers were deleted, so these tests no longer have a
    // production target. Assistant rendering is covered by
    // `assistant_text_event_renders_assistant_entry` and
    // `coalesced_assistant_text_supersedes_rather_than_stacks`.

    #[test]
    fn pending_approval_overlay_survives_run_output_until_reviewed() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.record_event(&GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_approval".to_owned()),
            task_id: Some("task_approval".to_owned()),
            data: json!({
                "approval_id": "approval_edit_1",
                "message": "Edit src/lib.rs?",
                "tool": "Edit",
                "target": "src/lib.rs"
            }),
        });
        app.record_event(&GatewayEvent {
            event_type: "run.output".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_approval".to_owned()),
            task_id: Some("task_approval".to_owned()),
            data: json!({"summary": "Waiting for approval."}),
        });

        assert_eq!(app.pending_approval_count(), 1);
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
    }

    #[test]
    fn run_records_collect_evidence_and_can_be_navigated() {
        let first = GatewayEvent {
            event_type: "run.started".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({"model": "claude-sonnet", "provider_id": "provider_anthropic"}),
        };
        let tool = GatewayEvent {
            event_type: "tool.used".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({"tool": "Bash", "command": "cargo test", "message": "ran tests"}),
        };
        let receipt = GatewayEvent {
            event_type: "receipt.created".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({"receipt_id": "receipt_run_1"}),
        };
        let second = GatewayEvent {
            event_type: "run.started".to_owned(),
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_done".to_owned()),
            task_id: None,
            data: json!({"status": "completed"}),
        };
        let second = GatewayEvent {
            event_type: "run.started".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_active".to_owned()),
            task_id: None,
            data: json!({}),
        };
        let third = GatewayEvent {
            event_type: "run.started".to_owned(),
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_live".to_owned()),
            task_id: Some("task_live".to_owned()),
            data: json!({"model": "claude-opus", "provider_id": "provider_anthropic"}),
        };
        let working = GatewayEvent {
            event_type: "run.working".to_owned(),
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
                .all(|entry| entry.title != "Run state")
        );
    }

    #[test]
    fn multiple_approvals_can_be_selected_and_decided() {
        let first = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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
            source: "gateway".to_owned(),
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

        app.record_event(&event);
        assert_eq!(
            app.transcript
                .iter()
                .filter(|entry| entry.title == "Bash")
                .count(),
            1
        );
        let grouped_entry = app
            .transcript
            .last()
            .expect("grouped tool transcript entry");
        assert!(grouped_entry.body.contains("Events: 2"));
        assert!(
            grouped_entry
                .body
                .contains("Latest: Command completed successfully.")
        );
        assert!(
            grouped_entry
                .body
                .contains("- Command completed successfully. (x2)")
        );
    }

    #[test]
    fn consecutive_tool_events_group_by_tool_title_without_hiding_context() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        let glob_event = GatewayEvent {
            event_type: "tool.used".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "tool": "Glob",
                "target": "src/**/*.rs",
                "message": "Claude Code is using Glob."
            }),
        };
        let read_event = GatewayEvent {
            event_type: "tool.used".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "tool": "Read",
                "target": "README.md",
                "message": "Claude Code is using Read on README.md."
            }),
        };

        app.record_event(&glob_event);
        app.record_event(&glob_event);
        app.record_event(&read_event);
        app.record_event(&read_event);

        let tool_entries = app
            .transcript
            .iter()
            .filter(|entry| entry.kind == TranscriptKind::Tool)
            .collect::<Vec<_>>();
        assert_eq!(tool_entries.len(), 2);
        assert_eq!(tool_entries[0].title, "Glob");
        assert!(tool_entries[0].body.contains("Events: 2"));
        assert!(tool_entries[0].body.contains("Target: src/**/*.rs"));
        assert!(tool_entries[1].body.contains("Events: 2"));
        assert!(tool_entries[1].body.contains("Target: README.md"));
    }

    #[test]
    fn model_events_update_state_and_receipts_surface_provider_context() {
        let model = GatewayEvent {
            event_type: "model.selected".to_owned(),
            source: "gateway".to_owned(),
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
            source: "anthropic-api".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: Some("task_1".to_owned()),
            data: json!({
                "receipt_id": "receipt_run_1_provider",
                "purpose": "execution",
                "execution": "craik",
                "mode": "default",
                "decision": "allow",
                "decided_by": "operator"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.state.apply_event(&model);
        app.record_event(&model);
        app.state.apply_event(&receipt);
        app.record_event(&receipt);

        assert_eq!(app.state.active_model.as_deref(), Some("claude-opus-4-7"));
        assert_eq!(
            app.state.active_provider_id.as_deref(),
            Some("provider_anthropic")
        );
        assert!(
            app.transcript
                .iter()
                .all(|entry| entry.title != "Model selected")
        );

        // The evidence line is now differentiated by the typed governance
        // identity (source / execution / decision) rather than collapsing to a
        // generic receipt-id string.
        let receipt_entry = app.transcript.last().expect("receipt transcript entry");
        assert_eq!(receipt_entry.title, "Evidence saved");
        assert!(receipt_entry.body.contains("Ctrl-E opens details"));
        assert!(receipt_entry.body.contains("anthropic-api"));
        assert!(receipt_entry.body.contains("craik"));
        assert!(receipt_entry.body.contains("allow (operator)"));

        app.open_overlay(ActiveOverlay::Evidence);
        let detail = app
            .overlay_items()
            .into_iter()
            .find(|item| item.title == "receipt_run_1_provider")
            .expect("receipt appears in evidence overlay")
            .detail;
        assert!(detail.contains("Receipt"));
        assert!(detail.contains("Run: run_1"));
        assert!(detail.contains("Task: task_1"));
        // Under the typed contract, provider identity rides the `source`
        // envelope on the receipt, not a `provider_id` data field.
        assert!(detail.contains("Receipt detail:"));
        assert!(detail.contains("source=anthropic-api"));
        assert!(detail.contains("execution=craik"));
        assert!(detail.contains("decided_by=operator"));
        assert!(detail.contains("Provenance:"));
    }

    #[test]
    fn session_ready_updates_state_without_crowding_transcript() {
        let ready = GatewayEvent {
            event_type: "session.ready".to_owned(),
            source: "gateway".to_owned(),
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

        assert!(app.transcript.is_empty());
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
                .contains("Memory review")
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

    fn low_risk_approval_event() -> GatewayEvent {
        GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_read_1",
                "message": "Read src/lib.rs?",
                "tool": "Read",
                "target": "src/lib.rs"
            }),
        }
    }

    fn high_risk_approval_event() -> GatewayEvent {
        GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_bash_1",
                "message": "Run rm -rf build?",
                "tool": "Bash",
                "command": "rm -rf build",
                "risk": "executes command with bypassPermissions; writes and deletes files"
            }),
        }
    }

    #[test]
    fn single_press_a_approves_low_risk_approval_when_overlay_active() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&low_risk_approval_event());
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));

        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));

        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "a approves a low-risk approval in one press"
        );
        assert!(
            !app.transcript.iter().any(|entry| entry.title == "Denying"),
            "approve never falls through to deny"
        );
    }

    #[test]
    fn single_press_d_denies_when_overlay_active() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&low_risk_approval_event());

        app.handle_key(KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE));

        assert!(
            app.transcript.iter().any(|entry| entry.title == "Denying"),
            "d denies in one press"
        );
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "deny is unambiguous and never approves"
        );
    }

    #[test]
    fn esc_defers_approval_overlay_without_deciding() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&low_risk_approval_event());
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));

        app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));

        assert_eq!(app.active_overlay, None, "esc dismisses the overlay");
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving" || entry.title == "Denying"),
            "esc defers without approving or denying"
        );
        // The approval remains pending so it can be revisited.
        assert_eq!(app.pending_approval_count(), 1);
    }

    #[test]
    fn approval_keys_do_nothing_when_overlay_inactive() {
        // No overlay active: the composer owns input, so a/d type normally and
        // never reach the approval decision path. This is the critical safety
        // property -- a stray keystroke while typing must never approve.
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&low_risk_approval_event());
        app.handle_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
        assert_eq!(app.active_overlay, None);
        let pending_before = app.pending_approval_count();

        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        app.handle_key(KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE));

        assert_eq!(
            app.input, "ad",
            "approval keys type into the composer when no overlay is focused"
        );
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving" || entry.title == "Denying"),
            "no decision is taken outside the approval overlay"
        );
        assert_eq!(app.pending_approval_count(), pending_before);
    }

    #[test]
    fn high_risk_approval_requires_explicit_confirm_before_a_decides() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&high_risk_approval_event());
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));

        // First 'a' arms the destructive confirm; it must NOT approve yet.
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "a high-risk approval is not approved on the first press"
        );
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));

        // Second 'a' confirms.
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "the explicit confirm press approves the high-risk approval"
        );
    }

    fn high_risk_approval_event_b() -> GatewayEvent {
        GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_bash_2",
                "message": "Run rm -rf dist?",
                "tool": "Bash",
                "command": "rm -rf dist",
                "risk": "executes command; writes and deletes files"
            }),
        }
    }

    #[test]
    fn arming_high_risk_then_navigating_disarms() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&high_risk_approval_event());
        app.record_event(&high_risk_approval_event_b());
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
        assert_eq!(app.pending_approvals.len(), 2);

        // Select approval A and arm it with a single 'a' (does NOT commit).
        app.handle_key(KeyEvent::new(KeyCode::Char('p'), KeyModifiers::CONTROL));
        assert_eq!(
            app.selected_pending_approval().unwrap().id,
            "approval_bash_1"
        );
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "arming A must not approve anything yet"
        );

        // Navigate to B. The arm must NOT carry over: a single 'a' on B must
        // only arm B, never commit it.
        app.handle_key(KeyEvent::new(KeyCode::Char('n'), KeyModifiers::CONTROL));
        assert_eq!(
            app.selected_pending_approval().unwrap().id,
            "approval_bash_2"
        );
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving" && entry.body.contains("approval_bash_2")),
            "navigating to B must disarm; the first post-navigation 'a' must NOT commit B"
        );

        // A second 'a' on B (now armed from a disarmed state) commits it.
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approving" && entry.body.contains("approval_bash_2")),
            "B requires its OWN two-press confirm from a disarmed state"
        );
    }

    #[test]
    fn arming_does_not_carry_after_a_committed_decision() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&high_risk_approval_event());
        app.record_event(&high_risk_approval_event_b());

        // Arm + commit high-risk A (two 'a' presses on A).
        app.handle_key(KeyEvent::new(KeyCode::Char('p'), KeyModifiers::CONTROL));
        assert_eq!(
            app.selected_pending_approval().unwrap().id,
            "approval_bash_1"
        );
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approving" && entry.body.contains("approval_bash_1")),
            "A is committed by its two-press confirm"
        );

        // Select B; the committed decision on A must have disarmed the gate.
        app.handle_key(KeyEvent::new(KeyCode::Char('n'), KeyModifiers::CONTROL));
        assert_eq!(
            app.selected_pending_approval().unwrap().id,
            "approval_bash_2"
        );
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving" && entry.body.contains("approval_bash_2")),
            "a single 'a' on B after a committed decision must NOT commit B"
        );
    }

    #[test]
    fn high_risk_approval_can_still_be_denied_in_one_press() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&high_risk_approval_event());

        // Deny is always single-press and unambiguous, even for high-risk.
        app.handle_key(KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE));
        assert!(app.transcript.iter().any(|entry| entry.title == "Denying"));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving")
        );
    }

    #[test]
    fn bypass_permissions_approval_is_high_risk_even_without_risk_keywords() {
        // A bypassPermissions-mode approval with a benign risk string (none of
        // the "write"/"delete"/"exec"... needles) must still be treated as
        // high-risk: bypassPermissions is the most dangerous mode, so it always
        // requires the two-press confirm regardless of the risk text.
        let event = GatewayEvent {
            event_type: "approval.requested".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({
                "approval_id": "approval_bypass_1",
                "message": "Proceed?",
                "tool": "Read",
                "permission_mode": "bypassPermissions",
                "risk": "routine"
            }),
        };
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(&event);
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Approvals));
        assert!(
            app.selected_approval_is_high_risk(),
            "bypassPermissions is always high-risk regardless of risk text"
        );

        // First 'a' must only arm, not commit.
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            !app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "a bypassPermissions approval is not approved on the first press"
        );
        // Second 'a' commits.
        app.handle_key(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Approving"),
            "the explicit confirm press approves the bypassPermissions approval"
        );
    }

    #[test]
    fn overlay_filter_narrows_evidence_and_selected_detail() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.state.receipt_ids = vec!["receipt_1".to_owned()];
        app.state.file_paths = vec!["src/main.rs".to_owned()];
        app.state.commands = vec!["cargo test".to_owned()];
        app.state.tool_events = vec![ActivityItem {
            kind: "tool".to_owned(),
            label: "Bash".to_owned(),
            detail: Some("Command completed.".to_owned()),
        }];

        app.handle_key(KeyEvent::new(KeyCode::Char('e'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Evidence));
        assert!(app.overlay_items().len() >= 4);

        for ch in "cargo".chars() {
            app.handle_key(KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE));
        }

        let items = app.overlay_items();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].title, "cargo test");
        assert!(app.selected_overlay_detail().contains("Command"));
    }

    #[test]
    fn runs_overlay_selection_updates_selected_run() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.run_records = vec![
            RunRecord {
                run_id: "run_one".to_owned(),
                status: Some("completed".to_owned()),
                ..RunRecord::default()
            },
            RunRecord {
                run_id: "run_two".to_owned(),
                status: Some("running".to_owned()),
                ..RunRecord::default()
            },
        ];
        app.selected_run_index = Some(0);

        app.handle_key(KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL));
        assert_eq!(app.active_overlay, Some(ActiveOverlay::Runs));
        app.handle_key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));

        assert_eq!(app.selected_run_index, Some(1));
        assert!(app.selected_overlay_detail().contains("run_two"));
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
    fn slash_palette_selection_drives_tab_completion() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.slash_catalog = vec![
            SlashHint::new(
                "receipt",
                "/receipt latest",
                "Show latest receipt.",
                "Evidence",
            ),
            SlashHint::new("run", "/run <prompt>", "Run an audited prompt.", "Run"),
        ];
        app.input = "/r".to_owned();
        app.input_cursor = app.input.len();

        app.handle_key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));
        assert_eq!(app.slash_selected_index, 1);
        app.handle_key(KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));

        assert_eq!(app.input, "/run ");
        assert_eq!(app.input_cursor, app.input.len());
    }

    #[test]
    fn slash_palette_drilldown_completion_fills_selected_value() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        let mut mode = SlashHint::new(
            "mode",
            "/mode [ask|auto|acceptEdits|plan|dontAsk|bypassPermissions]",
            "Set mode.",
            "Run",
        );
        mode.current_value = Some("ask".to_owned());
        app.slash_catalog = vec![mode];
        app.input = "/mode ".to_owned();
        app.input_cursor = app.input.len();

        app.handle_key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));
        app.handle_key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));
        app.handle_key(KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));

        assert_eq!(app.input, "/mode acceptEdits ");
    }

    #[test]
    fn enter_submits_selected_executable_slash_completion() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        let mut model = SlashHint::new(
            "model",
            "/model [set <provider/model>]",
            "Set model.",
            "Run",
        );
        model.model_choices = vec![
            "anthropic/claude-opus-4-7".to_owned(),
            "openai/gpt-5.2".to_owned(),
        ];
        model.subcommands = vec!["set".to_owned()];
        app.slash_catalog = vec![model];
        app.input = "/model set o".to_owned();
        app.input_cursor = app.input.len();

        app.handle_key(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE));

        assert_eq!(
            app.last_submitted_text.as_deref(),
            Some("/model set openai/gpt-5.2")
        );
        assert!(app.input.is_empty());
        assert!(app.in_flight);
    }

    #[test]
    fn enter_completes_non_executable_slash_selection_without_submitting() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        let mut model = SlashHint::new(
            "model",
            "/model [set <provider/model>]",
            "Set model.",
            "Run",
        );
        model.subcommands = vec!["set".to_owned()];
        app.slash_catalog = vec![model];
        app.input = "/model ".to_owned();
        app.input_cursor = app.input.len();

        app.handle_key(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE));

        assert_eq!(app.input, "/model set ");
        assert!(app.last_submitted_text.is_none());
        assert!(!app.in_flight);
    }

    #[test]
    fn slash_catalog_current_values_refresh_after_state_changes() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.slash_catalog = vec![
            SlashHint::new(
                "model",
                "/model [set <provider/model>]",
                "Set model.",
                "Run",
            ),
            SlashHint::new(
                "mode",
                "/mode [ask|auto|acceptEdits|plan|dontAsk|bypassPermissions]",
                "Set mode.",
                "Run",
            ),
            SlashHint::new(
                "effort",
                "/effort [default|low|medium|high|max]",
                "Set effort.",
                "Run",
            ),
        ];
        let event = GatewayEvent {
            event_type: "model.changed".to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "model": "anthropic/claude-opus-4-7",
                "provider_family": "anthropic",
                "reasoning_effort": "high"
            }),
        };

        app.state.active_permission_mode = Some("default".to_owned());
        app.state.apply_event(&event);
        app.refresh_slash_catalog_current_values();

        assert_eq!(
            app.slash_catalog[0].current_value.as_deref(),
            Some("anthropic/claude-opus-4-7")
        );
        assert_eq!(app.slash_catalog[1].current_value.as_deref(), Some("ask"));
        assert_eq!(app.slash_catalog[2].current_value.as_deref(), Some("high"));
    }

    #[test]
    fn shift_tab_cycles_permission_mode_through_gateway() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.state.active_permission_mode = Some("default".to_owned());

        app.handle_key(KeyEvent::new(KeyCode::BackTab, KeyModifiers::SHIFT));

        assert!(app.in_flight);
        assert!(
            app.transcript
                .iter()
                .any(|entry| entry.title == "Mode" && entry.body.contains("`auto`"))
        );
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
                "Evidence saved",
                "Saved evidence. Ctrl-E opens details. receipt_1",
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
            source: "gateway".to_owned(),
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

    #[test]
    fn transcript_scroll_keys_keep_footer_pinned_and_move_viewport() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        app.handle_key(KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE));
        assert_eq!(app.transcript_scroll, 12);

        app.handle_key(KeyEvent::new(KeyCode::Down, KeyModifiers::ALT));
        assert_eq!(app.transcript_scroll, 11);

        app.handle_key(KeyEvent::new(KeyCode::Up, KeyModifiers::ALT));
        assert_eq!(app.transcript_scroll, 12);

        app.handle_key(KeyEvent::new(KeyCode::PageDown, KeyModifiers::NONE));
        assert_eq!(app.transcript_scroll, 0);
    }

    fn event(
        event_type: &str,
        run_id: Option<&str>,
        task_id: Option<&str>,
        data: serde_json::Value,
    ) -> GatewayEvent {
        GatewayEvent {
            event_type: event_type.to_owned(),
            source: "gateway".to_owned(),
            created_at: None,
            run_id: run_id.map(str::to_owned),
            task_id: task_id.map(str::to_owned),
            data,
        }
    }
}
