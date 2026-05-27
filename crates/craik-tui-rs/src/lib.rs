use serde::Deserialize;
use std::collections::BTreeSet;

#[derive(Debug, Deserialize)]
pub struct GatewayEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub run_id: Option<String>,
    pub task_id: Option<String>,
    #[serde(default)]
    pub data: serde_json::Value,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct GatewayReplaySummary {
    pub event_types: Vec<String>,
    pub run_ids: Vec<String>,
    pub task_ids: Vec<String>,
    pub receipt_ids: Vec<String>,
    pub progress_messages: Vec<String>,
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
            .any(|event_type| event_type == "model.selected")
            || !self.progress_messages.is_empty()
    }
}

pub fn parse_gateway_events(input: &str) -> anyhow::Result<Vec<GatewayEvent>> {
    input
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str::<GatewayEvent>(line).map_err(Into::into))
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
        if event.event_type == "run.progress" {
            if let Some(message) = event.data.get("message").and_then(|value| value.as_str()) {
                summary.progress_messages.push(message.to_owned());
            }
        }
    }
    summary
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
    ]
    .join("\n")
}

fn push_unique(values: &mut Vec<String>, value: &str) {
    if !values.iter().any(|candidate| candidate == value) {
        values.push(value.to_owned());
    }
}

fn join_or_none(values: &[String]) -> String {
    if values.is_empty() {
        "none".to_owned()
    } else {
        values.join(", ")
    }
}

#[cfg(test)]
mod tests {
    use super::{parse_gateway_events, render_replay_text, summarize_gateway_events};

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
        Progress: Preparing audited Claude Code run.
        "###);
    }
}
