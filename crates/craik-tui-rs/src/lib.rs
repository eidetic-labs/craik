use anyhow::{Context, bail};
mod model_names;
use model_names::readable_model_label;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    io::Write,
    process::{Command, Stdio},
    sync::OnceLock,
};

const GATEWAY_EVENT_CONTRACT_JSON: &str =
    include_str!("../../../src/craik/runtime/backend/gateway_event_contract.json");

#[derive(Debug, Deserialize, Clone)]
pub struct GatewayEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub created_at: Option<String>,
    pub run_id: Option<String>,
    pub task_id: Option<String>,
    #[serde(default)]
    pub data: Value,
}

#[derive(Debug, PartialEq, Eq)]
pub struct GatewayContractIssue {
    pub event_index: usize,
    pub event_type: String,
    pub message: String,
}

#[derive(Debug, Deserialize)]
struct GatewayEventContract {
    event_types: serde_json::Map<String, Value>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(tag = "type")]
pub enum GatewayCommand {
    #[serde(rename = "session.status")]
    SessionStatus,
    #[serde(rename = "session.history")]
    SessionHistory,
    #[serde(rename = "prompt.submit")]
    PromptSubmit { text: String },
    #[serde(rename = "slash.submit")]
    SlashSubmit { text: String },
    #[serde(rename = "slash.catalog")]
    SlashCatalog,
    #[serde(rename = "model.set")]
    ModelSet {
        model: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        display_name: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        reasoning_effort: Option<String>,
    },
    #[serde(rename = "approval.decide")]
    ApprovalDecide {
        approval_id: String,
        decision: String,
        operator: String,
        reason: String,
    },
    #[serde(rename = "run.interrupt")]
    RunInterrupt { run_id: String, reason: String },
    #[serde(rename = "session.close")]
    SessionClose,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct GatewayReplaySummary {
    pub event_types: Vec<String>,
    pub run_ids: Vec<String>,
    pub task_ids: Vec<String>,
    pub receipt_ids: Vec<String>,
    pub progress_messages: Vec<String>,
    pub tool_names: Vec<String>,
    pub file_paths: Vec<String>,
    pub commands: Vec<String>,
    pub approval_requests: Vec<String>,
}

impl GatewayReplaySummary {
    pub fn has_lifecycle(&self) -> bool {
        let observed: BTreeSet<&str> = self.event_types.iter().map(String::as_str).collect();
        [
            "prompt.submitted",
            "run.started",
            "receipt.created",
            "run.completed",
        ]
        .into_iter()
        .all(|event_type| observed.contains(event_type))
    }

    pub fn has_working_state(&self) -> bool {
        self.event_types
            .iter()
            .any(|event_type| event_type == "model.selected" || event_type == "run.working")
            || !self.progress_messages.is_empty()
    }

    pub fn has_activity(&self) -> bool {
        !self.tool_names.is_empty()
            || !self.file_paths.is_empty()
            || !self.commands.is_empty()
            || !self.approval_requests.is_empty()
    }
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct GatewayAppState {
    pub ready: bool,
    pub readiness_state: Option<String>,
    pub active_model: Option<String>,
    pub active_model_display_name: Option<String>,
    pub active_reasoning_effort: Option<String>,
    pub active_permission_mode: Option<String>,
    pub active_provider_id: Option<String>,
    pub active_provider_family: Option<String>,
    pub backend: Option<String>,
    pub working_phase: Option<String>,
    pub run_status: Option<String>,
    pub run_ids: Vec<String>,
    pub task_ids: Vec<String>,
    pub progress_messages: Vec<String>,
    pub tool_events: Vec<ActivityItem>,
    pub file_paths: Vec<String>,
    pub commands: Vec<String>,
    pub approval_requests: Vec<String>,
    pub approval_resolutions: Vec<String>,
    pub receipt_ids: Vec<String>,
    pub outputs: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
pub struct ActivityItem {
    pub kind: String,
    pub label: String,
    pub detail: Option<String>,
}

impl GatewayAppState {
    pub fn apply_event(&mut self, event: &GatewayEvent) {
        if let Some(run_id) = &event.run_id {
            push_unique(&mut self.run_ids, run_id);
        }
        if let Some(task_id) = &event.task_id {
            push_unique(&mut self.task_ids, task_id);
        }

        match event.event_type.as_str() {
            "session.ready" => {
                self.ready = true;
            }
            "session.status" => {
                self.readiness_state = string_at(&event.data, &["state"]);
                self.active_permission_mode = permission_mode(&event.data);
                self.apply_model_state(&event.data);
            }
            "session.history" => {
                for item in array_at(&event.data, &["receipts"]) {
                    if let Some(receipt_id) = item.get("id").and_then(|value| value.as_str()) {
                        push_unique(&mut self.receipt_ids, receipt_id);
                    }
                    if let Some(task_id) = item.get("task_id").and_then(|value| value.as_str()) {
                        push_unique(&mut self.task_ids, task_id);
                    }
                }
            }
            "model.changed" => {
                self.apply_model_state(&event.data);
            }
            "model.selected" => {
                self.apply_model_state(&event.data);
                self.backend = string_at(&event.data, &["backend"])
                    .or_else(|| string_at(&event.data, &["profile", "backend"]));
            }
            "run.working" => {
                self.backend = string_at(&event.data, &["backend"]).or_else(|| self.backend.take());
                self.working_phase = string_at(&event.data, &["phase"]);
            }
            "run.progress" => {
                if let Some(message) = string_at(&event.data, &["message"]) {
                    self.progress_messages.push(message);
                }
            }
            "run.started" => {
                self.backend = string_at(&event.data, &["backend"]).or_else(|| self.backend.take());
                self.run_status = Some("running".to_owned());
            }
            "tool.used" => {
                let label = string_at(&event.data, &["tool"]).unwrap_or_else(|| "tool".to_owned());
                let detail = string_at(&event.data, &["target"])
                    .or_else(|| string_at(&event.data, &["command"]))
                    .or_else(|| string_at(&event.data, &["message"]));
                self.tool_events.push(ActivityItem {
                    kind: "tool".to_owned(),
                    label,
                    detail,
                });
                if let Some(command) = string_at(&event.data, &["command"]) {
                    push_unique(&mut self.commands, &command);
                }
                push_files(&mut self.file_paths, &event.data);
            }
            "file.changed" => {
                push_files(&mut self.file_paths, &event.data);
                let label =
                    string_at(&event.data, &["target"]).unwrap_or_else(|| "file".to_owned());
                self.tool_events.push(ActivityItem {
                    kind: "file".to_owned(),
                    label,
                    detail: string_at(&event.data, &["message"]),
                });
            }
            "approval.requested" => {
                if let Some(message) = string_at(&event.data, &["message"]) {
                    self.approval_requests.push(message);
                }
            }
            "approval.resolved" => {
                let approval_id = string_at(&event.data, &["approval_id"])
                    .unwrap_or_else(|| "approval".to_owned());
                let decision =
                    string_at(&event.data, &["decision"]).unwrap_or_else(|| "resolved".to_owned());
                self.approval_resolutions
                    .push(format!("{approval_id}: {decision}"));
            }
            "receipt.created" => {
                if let Some(receipt_id) = string_at(&event.data, &["receipt_id"]) {
                    push_unique(&mut self.receipt_ids, &receipt_id);
                }
            }
            "run.output" => {
                if let Some(summary) = string_at(&event.data, &["summary"]) {
                    self.outputs.push(summary);
                }
            }
            "run.event" => {
                if let Some(text) = string_at(&event.data, &["text"])
                    .or_else(|| string_at(&event.data, &["message"]))
                {
                    self.outputs.push(text);
                }
            }
            "run.completed" => {
                self.run_status =
                    string_at(&event.data, &["status"]).or_else(|| Some("completed".to_owned()));
                self.backend = string_at(&event.data, &["backend"]).or_else(|| self.backend.take());
                self.working_phase = None;
            }
            "run.interrupt.requested" => {
                self.run_status = Some("interrupt requested".to_owned());
            }
            "slash.completed" => {
                if let Some(summary) = summarize_slash_completed(&event.data) {
                    self.outputs.push(summary);
                }
            }
            "error" => {
                self.errors.push(
                    string_at(&event.data, &["message"])
                        .unwrap_or_else(|| "unknown error".to_owned()),
                );
            }
            _ => {}
        }
    }

    fn apply_model_state(&mut self, data: &Value) {
        if let Some(model) = string_at(data, &["model"]) {
            self.active_model = Some(model);
        }
        if let Some(provider_id) = string_at(data, &["provider_id"])
            .or_else(|| string_at(data, &["profile", "provider_id"]))
            .or_else(|| string_at(data, &["payload", "active_profile", "provider_id"]))
        {
            self.active_provider_id = Some(provider_id);
        }
        if let Some(provider_family) = string_at(data, &["provider_family"])
            .or_else(|| string_at(data, &["profile", "provider_family"]))
            .or_else(|| string_at(data, &["payload", "active_profile", "provider_family"]))
        {
            self.active_provider_family = Some(provider_family);
        }
        if let Some(display_name) = model_changed_display_name(data)
            .or_else(|| string_at(data, &["profile", "display_name"]))
            .or_else(|| string_at(data, &["payload", "active_profile", "display_name"]))
            .or_else(|| string_at(data, &["display_name"]))
        {
            self.active_model_display_name = Some(readable_model_label(
                self.active_provider_family.as_deref(),
                self.active_model.as_deref(),
                Some(&display_name),
            ));
        } else if let Some(model) = self.active_model.as_deref() {
            self.active_model_display_name = Some(readable_model_label(
                self.active_provider_family.as_deref(),
                Some(model),
                None,
            ));
        }
        if let Some(effort) = reasoning_effort(data) {
            self.active_reasoning_effort = Some(effort);
        }
    }
}

pub fn parse_gateway_events(input: &str) -> anyhow::Result<Vec<GatewayEvent>> {
    input
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str::<GatewayEvent>(line).map_err(Into::into))
        .collect()
}

pub fn validate_gateway_event(event: &GatewayEvent) -> Vec<GatewayContractIssue> {
    validate_gateway_event_at(event, 0)
}

pub fn validate_gateway_events(events: &[GatewayEvent]) -> Vec<GatewayContractIssue> {
    events
        .iter()
        .enumerate()
        .flat_map(|(index, event)| validate_gateway_event_at(event, index))
        .collect()
}

pub fn summarize_gateway_events(events: &[GatewayEvent]) -> GatewayReplaySummary {
    let mut summary = GatewayReplaySummary::default();
    for event in events {
        push_unique(&mut summary.event_types, &event.event_type);
        if let Some(run_id) = &event.run_id {
            push_unique(&mut summary.run_ids, run_id);
        }
        if let Some(task_id) = &event.task_id {
            push_unique(&mut summary.task_ids, task_id);
        }
        if let Some(receipt_id) = event
            .data
            .get("receipt_id")
            .and_then(|value| value.as_str())
        {
            push_unique(&mut summary.receipt_ids, receipt_id);
        }
        if event.event_type == "run.progress"
            && let Some(message) = event.data.get("message").and_then(|value| value.as_str())
        {
            summary.progress_messages.push(message.to_owned());
        }
        if event.event_type == "tool.used" {
            if let Some(tool) = event.data.get("tool").and_then(|value| value.as_str()) {
                push_unique(&mut summary.tool_names, tool);
            }
            if let Some(command) = event.data.get("command").and_then(|value| value.as_str()) {
                push_unique(&mut summary.commands, command);
            }
            push_files(&mut summary.file_paths, &event.data);
        }
        if event.event_type == "file.changed" {
            push_files(&mut summary.file_paths, &event.data);
        }
        if event.event_type == "approval.requested"
            && let Some(message) = event.data.get("message").and_then(|value| value.as_str())
        {
            summary.approval_requests.push(message.to_owned());
        }
    }
    summary
}

pub fn app_state_from_events(events: &[GatewayEvent]) -> GatewayAppState {
    let mut state = GatewayAppState::default();
    for event in events {
        state.apply_event(event);
    }
    state
}

fn validate_gateway_event_at(
    event: &GatewayEvent,
    event_index: usize,
) -> Vec<GatewayContractIssue> {
    let mut issues = Vec::new();
    let Some(rule) = gateway_event_contract().event_types.get(&event.event_type) else {
        issues.push(contract_issue(
            event_index,
            event,
            format!("unsupported event type `{}`", event.event_type),
        ));
        return issues;
    };
    if !event.data.is_object() {
        issues.push(contract_issue(
            event_index,
            event,
            "event data must be a JSON object",
        ));
        return issues;
    }

    for requirement in rule
        .get("requirements")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        validate_contract_requirement(&mut issues, event_index, event, requirement);
    }
    issues
}

pub fn render_replay_text(summary: &GatewayReplaySummary) -> String {
    let lifecycle = if summary.has_lifecycle() {
        "complete"
    } else {
        "incomplete"
    };
    let working = if summary.has_working_state() {
        "available"
    } else {
        "missing"
    };
    [
        "Craik Gateway Replay".to_owned(),
        format!("Lifecycle: {lifecycle}"),
        format!("Working state: {working}"),
        format!("Runs: {}", join_or_none(&summary.run_ids)),
        format!("Tasks: {}", join_or_none(&summary.task_ids)),
        format!("Receipts: {}", join_or_none(&summary.receipt_ids)),
        format!("Progress: {}", join_or_none(&summary.progress_messages)),
        format!("Tools: {}", join_or_none(&summary.tool_names)),
        format!("Files: {}", join_or_none(&summary.file_paths)),
        format!("Commands: {}", join_or_none(&summary.commands)),
        format!("Approvals: {}", join_or_none(&summary.approval_requests)),
    ]
    .join("\n")
}

pub fn render_dashboard_text(state: &GatewayAppState) -> String {
    let model = readable_model_label(
        state.active_provider_family.as_deref(),
        state.active_model.as_deref(),
        state.active_model_display_name.as_deref(),
    );
    let run_state = state.run_status.as_deref().unwrap_or("idle");
    let phase = state.working_phase.as_deref().unwrap_or("none");
    [
        "Craik Rust/Ratatui Gateway".to_owned(),
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
        format!("Run: {run_state} · phase {phase}"),
        format!("Runs: {}", join_or_none(&state.run_ids)),
        format!("Tasks: {}", join_or_none(&state.task_ids)),
        format!("Progress: {}", join_or_none(&state.progress_messages)),
        format!("Tools: {}", render_activity(&state.tool_events)),
        format!("Files: {}", join_or_none(&state.file_paths)),
        format!("Commands: {}", join_or_none(&state.commands)),
        format!(
            "Approval requests: {}",
            join_or_none(&state.approval_requests)
        ),
        format!(
            "Approval decisions: {}",
            join_or_none(&state.approval_resolutions)
        ),
        format!("Receipts: {}", join_or_none(&state.receipt_ids)),
        format!("Output: {}", join_or_none(&state.outputs)),
        format!("Errors: {}", join_or_none(&state.errors)),
    ]
    .join("\n")
}

pub fn encode_gateway_command(command: &GatewayCommand) -> anyhow::Result<String> {
    Ok(serde_json::to_string(command)?)
}

pub fn run_backend_commands(commands: &[GatewayCommand]) -> anyhow::Result<Vec<GatewayEvent>> {
    if commands.is_empty() {
        bail!("at least one Gateway command is required")
    }

    let mut child = Command::new("uv")
        .args(["run", "craik", "tui-backend", "--jsonl"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("failed to start `uv run craik tui-backend --jsonl`")?;

    {
        let stdin = child
            .stdin
            .as_mut()
            .context("backend stdin was not captured")?;
        for command in commands {
            stdin.write_all(encode_gateway_command(command)?.as_bytes())?;
            stdin.write_all(b"\n")?;
        }
    }

    let output = child.wait_with_output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("Gateway backend exited with {}: {stderr}", output.status);
    }

    let stdout = String::from_utf8(output.stdout).context("Gateway backend emitted non-UTF-8")?;
    let events = parse_gateway_events(&stdout)?;
    let issues = validate_gateway_events(&events);
    if !issues.is_empty() {
        bail!(
            "Gateway backend emitted invalid events. {}",
            format_gateway_contract_issues(&issues)
        );
    }
    Ok(events)
}

fn push_unique(values: &mut Vec<String>, value: &str) {
    if !values.iter().any(|candidate| candidate == value) {
        values.push(value.to_owned());
    }
}

fn push_files(values: &mut Vec<String>, data: &Value) {
    if let Some(files) = data.get("files").and_then(|value| value.as_array()) {
        for file in files {
            if let Some(path) = file.as_str() {
                push_unique(values, path);
            }
        }
    }
}

fn gateway_event_contract() -> &'static GatewayEventContract {
    static CONTRACT: OnceLock<GatewayEventContract> = OnceLock::new();
    CONTRACT.get_or_init(|| {
        serde_json::from_str(GATEWAY_EVENT_CONTRACT_JSON)
            .expect("embedded Gateway event contract must parse")
    })
}

fn contract_issue(
    event_index: usize,
    event: &GatewayEvent,
    message: impl Into<String>,
) -> GatewayContractIssue {
    GatewayContractIssue {
        event_index,
        event_type: event.event_type.clone(),
        message: message.into(),
    }
}

fn validate_contract_requirement(
    issues: &mut Vec<GatewayContractIssue>,
    event_index: usize,
    event: &GatewayEvent,
    requirement: &Value,
) {
    let Some(kind) = requirement.get("kind").and_then(Value::as_str) else {
        return;
    };
    let message = requirement
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("Gateway event contract requirement failed");

    match kind {
        "non_empty_string" => {
            let Some(path) = requirement.get("path").and_then(Value::as_str) else {
                return;
            };
            if string_at_event_path(event, path)
                .unwrap_or_default()
                .trim()
                .is_empty()
            {
                issues.push(contract_issue(event_index, event, message));
            }
        }
        "array" => {
            let Some(path) = requirement.get("path").and_then(Value::as_str) else {
                return;
            };
            if !value_at_event_path(event, path).is_some_and(Value::is_array) {
                issues.push(contract_issue(event_index, event, message));
            }
        }
        "one_non_empty_string" => {
            let Some(paths) = requirement.get("paths").and_then(Value::as_array) else {
                return;
            };
            let passed = paths.iter().filter_map(Value::as_str).any(|path| {
                !string_at_event_path(event, path)
                    .unwrap_or_default()
                    .trim()
                    .is_empty()
            });
            if !passed {
                issues.push(contract_issue(event_index, event, message));
            }
        }
        "one_present" => {
            let Some(paths) = requirement.get("paths").and_then(Value::as_array) else {
                return;
            };
            let passed = paths
                .iter()
                .filter_map(Value::as_str)
                .any(|path| value_at_event_path(event, path).is_some());
            if !passed {
                issues.push(contract_issue(event_index, event, message));
            }
        }
        _ => {}
    }
}

fn string_at_event_path<'a>(event: &'a GatewayEvent, path: &str) -> Option<&'a str> {
    match path {
        "run_id" => event.run_id.as_deref(),
        "task_id" => event.task_id.as_deref(),
        _ => value_at_event_path(event, path).and_then(Value::as_str),
    }
}

fn value_at_event_path<'a>(event: &'a GatewayEvent, path: &str) -> Option<&'a Value> {
    let mut parts = path.split('.');
    match parts.next()? {
        "data" => {
            let mut value = &event.data;
            for key in parts {
                value = value.get(key)?;
            }
            Some(value)
        }
        _ => None,
    }
}

fn string_at(data: &Value, path: &[&str]) -> Option<String> {
    let mut value = data;
    for key in path {
        value = value.get(key)?;
    }
    value.as_str().map(str::to_owned)
}

fn array_at<'a>(data: &'a Value, path: &[&str]) -> &'a [Value] {
    let mut value = data;
    for key in path {
        let Some(next) = value.get(key) else {
            return &[];
        };
        value = next;
    }
    value.as_array().map(Vec::as_slice).unwrap_or(&[])
}

fn model_changed_display_name(data: &Value) -> Option<String> {
    let active_profile_id = string_at(data, &["payload", "active_profile_id"])?;
    data.get("payload")?
        .get("profiles")?
        .get(active_profile_id)?
        .get("display_name")?
        .as_str()
        .map(str::to_owned)
}

fn reasoning_effort(data: &Value) -> Option<String> {
    string_at(data, &["reasoning_effort"])
        .or_else(|| string_at(data, &["profile", "options", "reasoning_effort"]))
        .or_else(|| {
            string_at(
                data,
                &["payload", "active_profile", "options", "reasoning_effort"],
            )
        })
        .or_else(|| {
            let active_profile_id = string_at(data, &["payload", "active_profile_id"])?;
            string_at(
                data,
                &[
                    "payload",
                    "profiles",
                    active_profile_id.as_str(),
                    "options",
                    "reasoning_effort",
                ],
            )
        })
}

fn permission_mode(data: &Value) -> Option<String> {
    string_at(data, &["claude_permission_mode"]).or_else(|| string_at(data, &["permission_mode"]))
}

fn summarize_slash_completed(data: &Value) -> Option<String> {
    if let Some(payload) = data.get("payload") {
        if let Some(items) = payload.as_array() {
            if items.is_empty() {
                return Some("Slash command completed: no records".to_owned());
            }
            let mut lines = vec![format!("Slash command completed: {} records", items.len())];
            for item in items.iter().take(5) {
                if let Some(object) = item.as_object() {
                    let id = object.get("id").and_then(Value::as_str).unwrap_or("record");
                    let status = object
                        .get("status")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown");
                    let runner = object
                        .get("runner_id")
                        .and_then(Value::as_str)
                        .unwrap_or("runner unknown");
                    lines.push(format!("- {id} [{status}] via {runner}"));
                }
            }
            if items.len() > 5 {
                lines.push(format!("- and {} more", items.len() - 5));
            }
            return Some(lines.join("\n"));
        }
        if let Some(object) = payload.as_object() {
            let keys = object.keys().cloned().collect::<Vec<_>>();
            return Some(format!("Slash command completed: {}", keys.join(", ")));
        }
    }
    string_at(data, &["text"])
}

fn join_or_none(values: &[String]) -> String {
    if values.is_empty() {
        "none".to_owned()
    } else {
        values.join(", ")
    }
}

fn render_activity(items: &[ActivityItem]) -> String {
    if items.is_empty() {
        return "none".to_owned();
    }
    items
        .iter()
        .map(|item| {
            if let Some(detail) = &item.detail {
                format!("{} {} ({detail})", item.kind, item.label)
            } else {
                format!("{} {}", item.kind, item.label)
            }
        })
        .collect::<Vec<_>>()
        .join(", ")
}

pub fn format_gateway_contract_issues(issues: &[GatewayContractIssue]) -> String {
    issues
        .iter()
        .map(|issue| {
            format!(
                "#{} {}: {}",
                issue.event_index, issue.event_type, issue.message
            )
        })
        .collect::<Vec<_>>()
        .join("; ")
}

pub fn format_gateway_contract_diagnostic(
    event: &GatewayEvent,
    issues: &[GatewayContractIssue],
) -> String {
    let mut lines = vec![format!(
        "Gateway event contract violation for `{}`.",
        event.event_type
    )];
    if let Some(context) = event_context(event) {
        lines.push(format!("Context: {context}"));
    }
    if !issues.is_empty() {
        lines.push("Issues:".to_owned());
        for issue in issues {
            lines.push(format!("- {}", issue.message));
        }
    }
    lines.push(
        "Recovery: update the backend emitter or the Gateway event contract, then retry the run."
            .to_owned(),
    );
    lines.join("\n")
}

pub fn format_gateway_error_event(event: &GatewayEvent) -> Option<String> {
    if event.event_type != "error" {
        return None;
    }
    let message =
        string_at(&event.data, &["message"]).unwrap_or_else(|| "unknown Gateway error".to_owned());
    if string_at(&event.data, &["kind"]).as_deref() != Some("contract_violation") {
        return Some(message);
    }

    let mut lines = vec![message];
    if let Some(context) = event_context(event) {
        lines.push(format!("Context: {context}"));
    }
    if let Some(issues) = event.data.get("issues").and_then(Value::as_array) {
        let issue_lines = issues
            .iter()
            .filter_map(Value::as_str)
            .filter(|issue| !issue.trim().is_empty())
            .map(|issue| format!("- {issue}"))
            .collect::<Vec<_>>();
        if !issue_lines.is_empty() {
            lines.push("Issues:".to_owned());
            lines.extend(issue_lines);
        }
    }
    if let Some(recovery) = string_at(&event.data, &["recovery"]) {
        lines.push(format!("Recovery: {recovery}"));
    }
    Some(lines.join("\n"))
}

fn event_context(event: &GatewayEvent) -> Option<String> {
    let mut parts = Vec::new();
    if let Some(run_id) = &event.run_id {
        parts.push(format!("run {run_id}"));
    }
    if let Some(task_id) = &event.task_id {
        parts.push(format!("task {task_id}"));
    }
    for (label, path) in [
        ("backend", &["backend"][..]),
        ("provider", &["provider_id"][..]),
        ("family", &["provider_family"][..]),
        ("model", &["model"][..]),
    ] {
        if let Some(value) = string_at(&event.data, path) {
            parts.push(format!("{label} {value}"));
        }
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join(", "))
    }
}

pub fn status_command_sequence() -> Vec<GatewayCommand> {
    vec![GatewayCommand::SessionStatus, GatewayCommand::SessionClose]
}

pub fn prompt_command_sequence(text: String) -> Vec<GatewayCommand> {
    vec![GatewayCommand::PromptSubmit { text }]
}

pub fn slash_command_sequence(text: String) -> Vec<GatewayCommand> {
    vec![GatewayCommand::SlashSubmit { text }]
}

pub fn approval_command_sequence(
    approval_id: String,
    decision: String,
    operator: String,
    reason: String,
) -> Vec<GatewayCommand> {
    vec![
        GatewayCommand::ApprovalDecide {
            approval_id,
            decision,
            operator,
            reason,
        },
        GatewayCommand::SessionClose,
    ]
}

pub fn interrupt_command_sequence(run_id: String, reason: String) -> Vec<GatewayCommand> {
    vec![
        GatewayCommand::RunInterrupt { run_id, reason },
        GatewayCommand::SessionClose,
    ]
}

pub fn model_command_sequence(
    model: String,
    display_name: Option<String>,
    reasoning_effort: Option<String>,
) -> Vec<GatewayCommand> {
    vec![
        GatewayCommand::ModelSet {
            model,
            display_name,
            reasoning_effort,
        },
        GatewayCommand::SessionClose,
    ]
}

pub fn sample_gateway_command_json() -> Value {
    json!({
        "status": encode_gateway_command(&GatewayCommand::SessionStatus).unwrap_or_default(),
        "prompt": encode_gateway_command(&GatewayCommand::PromptSubmit {
            text: "Review the plan".to_owned(),
        }).unwrap_or_default(),
        "slash": encode_gateway_command(&GatewayCommand::SlashSubmit {
            text: "/run list".to_owned(),
        }).unwrap_or_default(),
    })
}

#[cfg(test)]
mod tests {
    use super::{
        GatewayCommand, GatewayEvent, app_state_from_events, encode_gateway_command,
        format_gateway_contract_diagnostic, format_gateway_error_event, gateway_event_contract,
        parse_gateway_events, render_dashboard_text, render_replay_text,
        sample_gateway_command_json, summarize_gateway_events, validate_gateway_event,
        validate_gateway_events,
    };
    use serde_json::json;

    const GATEWAY_FIXTURES: &[&str] = &[
        include_str!("../../../tests/fixtures/gateway/contract_event_coverage.jsonl"),
        include_str!("../../../tests/fixtures/gateway/prompt_run.jsonl"),
        include_str!("../../../tests/fixtures/gateway/claude_code_stream.jsonl"),
        include_str!("../../../tests/fixtures/gateway/provider_anthropic_messages_stream.jsonl"),
        include_str!("../../../tests/fixtures/gateway/provider_openai_responses_stream.jsonl"),
        include_str!("../../../tests/fixtures/gateway/provider_gemini_stream.jsonl"),
        include_str!("../../../tests/fixtures/gateway/provider_local_ollama_stream.jsonl"),
    ];

    const PROVIDER_FIXTURES: &[(&str, &str, &str, &str, &str)] = &[
        (
            include_str!(
                "../../../tests/fixtures/gateway/provider_anthropic_messages_stream.jsonl"
            ),
            "provider_anthropic_messages",
            "anthropic",
            "Anthropic Claude Sonnet 4",
            "provider",
        ),
        (
            include_str!("../../../tests/fixtures/gateway/provider_openai_responses_stream.jsonl"),
            "provider_openai_responses",
            "openai",
            "OpenAI GPT-5.4",
            "provider",
        ),
        (
            include_str!("../../../tests/fixtures/gateway/provider_gemini_stream.jsonl"),
            "provider_gemini",
            "gemini",
            "Google Gemini 2.5 Pro",
            "provider",
        ),
        (
            include_str!("../../../tests/fixtures/gateway/provider_local_ollama_stream.jsonl"),
            "provider_local_ollama",
            "chat_completions",
            "Local Ollama Llama 3.1 8B",
            "local",
        ),
    ];

    #[test]
    fn summarizes_gateway_replay_fixture() {
        let input = include_str!("../../../tests/fixtures/gateway/prompt_run.jsonl");
        let events = parse_gateway_events(input).expect("fixture parses");

        let summary = summarize_gateway_events(&events);

        assert!(summary.has_lifecycle());
        assert!(summary.has_working_state());
        assert_eq!(summary.run_ids, ["run_review_the_plan"]);
        assert_eq!(
            summary.receipt_ids,
            ["receipt_run_review_the_plan_claude_code"]
        );
        insta::assert_snapshot!(render_replay_text(&summary), @r###"
        Craik Gateway Replay
        Lifecycle: complete
        Working state: available
        Runs: run_review_the_plan
        Tasks: task_review_the_plan
        Receipts: receipt_run_review_the_plan_claude_code
        Progress: Preparing audited model run.
        Tools: none
        Files: none
        Commands: none
        Approvals: none
        "###);
    }

    #[test]
    fn summarizes_structured_activity_fixture() {
        let input = include_str!("../../../tests/fixtures/gateway/claude_code_stream.jsonl");
        let events = parse_gateway_events(input).expect("fixture parses");

        let summary = summarize_gateway_events(&events);

        assert!(summary.has_lifecycle());
        assert!(summary.has_working_state());
        assert!(summary.has_activity());
        assert_eq!(summary.tool_names, ["Read", "Grep", "Bash"]);
        assert_eq!(
            summary.commands,
            ["uv run pytest tests/test_backend_gateway_session.py"]
        );
        assert_eq!(
            summary.file_paths,
            [
                "/Users/bjones/Desktop/Craik_Backend_Plan.md",
                "src/craik/runtime/backend",
                "src/craik/runtime/backend/session.py",
            ]
        );
    }

    #[test]
    fn builds_dashboard_state_from_full_gateway_activity() {
        let input = include_str!("../../../tests/fixtures/gateway/claude_code_stream.jsonl");
        let events = parse_gateway_events(input).expect("fixture parses");

        let state = app_state_from_events(&events);

        assert_eq!(state.backend.as_deref(), Some("claude-code"));
        assert_eq!(state.run_status.as_deref(), Some("completed"));
        assert_eq!(state.tool_events.len(), 4);
        assert_eq!(state.approval_requests.len(), 1);
        assert_eq!(state.outputs.len(), 3);
        insta::assert_snapshot!(render_dashboard_text(&state), @r###"
        Craik Rust/Ratatui Gateway
        Session: starting
        Readiness: unknown
        Model: not selected
        Backend: claude-code
        Run: completed · phase none
        Runs: run_review_desktop_plan
        Tasks: task_review_desktop_plan
        Progress: Preparing audited model run., Claude Code is using `Read` on `/Users/bjones/Desktop/Craik_Backend_Plan.md`., Claude Code is using `Grep` on `src/craik/runtime/backend`., Claude Code is using `Bash`: `uv run pytest tests/test_backend_gateway_session.py`.
        Tools: tool Read (/Users/bjones/Desktop/Craik_Backend_Plan.md), tool Grep (src/craik/runtime/backend), tool Bash (uv run pytest tests/test_backend_gateway_session.py), file src/craik/runtime/backend/session.py (Claude Code diff:
        --- a/src/craik/runtime/backend/session.py
        +++ b/src/craik/runtime/backend/session.py
        @@
        +stream normalized Claude events)
        Files: /Users/bjones/Desktop/Craik_Backend_Plan.md, src/craik/runtime/backend, src/craik/runtime/backend/session.py
        Commands: uv run pytest tests/test_backend_gateway_session.py
        Approval requests: Claude Code requests approval for `Edit` on `src/craik/runtime/backend/session.py`: normalize stream event mapping
        Approval decisions: none
        Receipts: receipt_review_desktop_plan_claude_code_approval, receipt_run_review_desktop_plan_claude_code
        Output: 7 passed in 1.09s, Reviewed the plan and normalized Gateway event handling for Claude Code stream events., Reviewed the plan and normalized Gateway event handling for Claude Code stream events.
        Errors: none
        "###);
    }

    #[test]
    fn encodes_gateway_commands_for_backend_protocol() {
        let command = GatewayCommand::ModelSet {
            model: "anthropic/claude-opus-4-7".to_owned(),
            display_name: Some("Anthropic Claude Opus 4.7".to_owned()),
            reasoning_effort: Some("high".to_owned()),
        };

        let encoded = encode_gateway_command(&command).expect("command serializes");

        assert_eq!(
            encoded,
            r#"{"type":"model.set","model":"anthropic/claude-opus-4-7","display_name":"Anthropic Claude Opus 4.7","reasoning_effort":"high"}"#
        );
        assert_eq!(
            sample_gateway_command_json()["slash"],
            r#"{"type":"slash.submit","text":"/run list"}"#
        );
        assert_eq!(
            encode_gateway_command(&GatewayCommand::SessionHistory).expect("command serializes"),
            r#"{"type":"session.history"}"#
        );
    }

    #[test]
    fn session_history_updates_dashboard_state() {
        let event = GatewayEvent {
            event_type: "session.history".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "receipts": [
                    {"id": "receipt_history_1", "task_id": "task_history_1"}
                ]
            }),
        };

        let issues = validate_gateway_events(std::slice::from_ref(&event));
        let state = app_state_from_events(&[event]);

        assert!(issues.is_empty());
        assert_eq!(state.receipt_ids, ["receipt_history_1"]);
        assert_eq!(state.task_ids, ["task_history_1"]);
    }

    #[test]
    fn model_changed_uses_active_profile_display_name() {
        let event = GatewayEvent {
            event_type: "model.changed".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "model": "anthropic/claude-opus-4-7",
                "payload": {
                    "active_profile_id": "anthropic-opus",
                    "profiles": {
                        "anthropic-opus": {
                            "display_name": "Anthropic Claude Opus 4.7 High",
                            "options": {
                                "reasoning_effort": "high"
                            }
                        }
                    }
                }
            }),
        };

        let state = app_state_from_events(&[event]);

        assert_eq!(
            state.active_model.as_deref(),
            Some("anthropic/claude-opus-4-7")
        );
        assert_eq!(
            state.active_model_display_name.as_deref(),
            Some("Anthropic Claude Opus 4.7 High")
        );
        assert_eq!(state.active_reasoning_effort.as_deref(), Some("high"));
    }

    #[test]
    fn model_selected_uses_profile_reasoning_effort() {
        let event = GatewayEvent {
            event_type: "model.selected".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "model": "claude-opus-4-7",
                "profile": {
                    "display_name": "Anthropic Claude Opus 4.7",
                    "options": {
                        "reasoning_effort": "max"
                    }
                }
            }),
        };

        let state = app_state_from_events(&[event]);

        assert_eq!(state.active_reasoning_effort.as_deref(), Some("max"));
    }

    #[test]
    fn session_status_updates_mode_and_active_model() {
        let event = GatewayEvent {
            event_type: "session.status".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "state": "fully-ready",
                "claude_permission_mode": "auto",
                "model": "anthropic/claude-opus-4-7",
                "provider_id": "provider_anthropic",
                "provider_family": "anthropic",
                "display_name": "Anthropic Claude Opus 4.7",
                "reasoning_effort": "high"
            }),
        };

        let state = app_state_from_events(&[event]);

        assert_eq!(state.readiness_state.as_deref(), Some("fully-ready"));
        assert_eq!(state.active_permission_mode.as_deref(), Some("auto"));
        assert_eq!(
            state.active_model.as_deref(),
            Some("anthropic/claude-opus-4-7")
        );
        assert_eq!(
            state.active_provider_id.as_deref(),
            Some("provider_anthropic")
        );
        assert_eq!(state.active_reasoning_effort.as_deref(), Some("high"));
    }

    #[test]
    fn slash_completed_summarizes_structured_run_lists() {
        let event = GatewayEvent {
            event_type: "slash.completed".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "payload": [
                    {
                        "id": "run_docs",
                        "status": "completed",
                        "runner_id": "claude-code"
                    },
                    {
                        "id": "run_review",
                        "status": "running",
                        "runner_id": "provider_anthropic"
                    }
                ],
                "shape": "json"
            }),
        };

        let state = app_state_from_events(&[event]);

        assert_eq!(
            state.outputs,
            [
                "Slash command completed: 2 records\n- run_docs [completed] via claude-code\n- run_review [running] via provider_anthropic"
            ]
        );
    }

    #[test]
    fn gateway_fixtures_satisfy_event_contract() {
        for input in GATEWAY_FIXTURES {
            let events = parse_gateway_events(input).expect("fixture parses");

            assert_eq!(validate_gateway_events(&events), []);
        }
    }

    #[test]
    fn gateway_event_contract_is_embedded_single_source() {
        let contract = gateway_event_contract();
        let rule = contract
            .event_types
            .get("run.completed")
            .expect("run.completed event rule exists");

        assert!(contract.event_types.contains_key("model.selected"));
        assert!(contract.event_types.contains_key("approval.requested"));
        assert_eq!(
            rule.get("requirements")
                .and_then(|value| value.as_array())
                .expect("requirements are an array")
                .len(),
            2
        );
    }

    #[test]
    fn provider_fixtures_render_consistent_dashboard_state() {
        for (input, provider_id, provider_family, display_name, backend) in PROVIDER_FIXTURES {
            let events = parse_gateway_events(input).expect("fixture parses");
            let state = app_state_from_events(&events);

            assert!(state.ready);
            assert_eq!(state.active_provider_id.as_deref(), Some(*provider_id));
            assert_eq!(
                state.active_provider_family.as_deref(),
                Some(*provider_family)
            );
            assert_eq!(
                state.active_model_display_name.as_deref(),
                Some(*display_name)
            );
            assert_eq!(state.backend.as_deref(), Some(*backend));
            assert_eq!(state.run_status.as_deref(), Some("completed"));
            assert_eq!(state.run_ids.len(), 1);
            assert_eq!(state.task_ids.len(), 1);
            assert_eq!(state.tool_events.len(), 1);
            assert_eq!(state.receipt_ids.len(), 1);
            assert_eq!(state.outputs.len(), 1);

            let rendered = render_dashboard_text(&state);
            assert!(rendered.contains(*provider_id));
            assert!(rendered.contains(*display_name));
            assert!(rendered.contains("Run: completed"));
            assert!(rendered.contains("Receipts: receipt_provider_"));
            assert!(rendered.contains("Output: "));
        }
    }

    #[test]
    fn event_contract_reports_missing_required_fields() {
        let events = parse_gateway_events(
            r#"{"type":"run.completed","data":{"status":"completed"},"run_id":null,"task_id":null}"#,
        )
        .expect("fixture parses");

        let issues = validate_gateway_events(&events);

        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].event_index, 0);
        assert_eq!(issues[0].event_type, "run.completed");
        assert_eq!(issues[0].message, "run_id is required");
    }

    #[test]
    fn contract_diagnostic_includes_context_and_recovery() {
        let event = GatewayEvent {
            event_type: "run.completed".to_owned(),
            created_at: None,
            run_id: None,
            task_id: Some("task_contract".to_owned()),
            data: json!({
                "status": "completed",
                "backend": "provider",
                "provider_id": "provider_anthropic",
                "model": "claude-sonnet-4"
            }),
        };
        let issues = validate_gateway_event(&event);

        let diagnostic = format_gateway_contract_diagnostic(&event, &issues);

        assert!(diagnostic.contains("Gateway event contract violation for `run.completed`."));
        assert!(diagnostic.contains("task task_contract"));
        assert!(diagnostic.contains("backend provider"));
        assert!(diagnostic.contains("- run_id is required"));
        assert!(diagnostic.contains("Recovery: update the backend emitter"));
    }

    #[test]
    fn contract_error_event_formats_structured_recovery_detail() {
        let event = GatewayEvent {
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
        };

        let message = format_gateway_error_event(&event).expect("error message formats");

        assert!(message.contains("Gateway backend emitted invalid event"));
        assert!(message.contains("run run_contract"));
        assert!(message.contains("provider provider_anthropic"));
        assert!(message.contains("- run_id is required"));
        assert!(message.contains("Recovery: Update the backend emitter before retrying."));
    }
}
