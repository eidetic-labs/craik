use crate::input::SlashHint;
use craik_tui_rs::GatewayEvent;

pub fn slash_hints_from_event(event: &GatewayEvent) -> Vec<SlashHint> {
    event
        .data
        .get("commands")
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
        .filter_map(|value| {
            let object = value.as_object()?;
            let name = object.get("name")?.as_str()?;
            Some(SlashHint {
                name: name.to_owned(),
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
                category: object
                    .get("category")
                    .or_else(|| object.get("group"))
                    .and_then(|value| value.as_str())
                    .map(str::to_owned)
                    .unwrap_or_else(|| slash_category(name)),
            })
        })
        .collect()
}

fn slash_category(name: &str) -> String {
    match name {
        "run" | "stop" | "interrupt" | "model" => "Run",
        "receipt" | "receipts" | "evidence" | "provenance" => "Evidence",
        "status" | "config" | "auth" | "login" => "Session",
        "help" | "commands" => "Help",
        _ => "Workflow",
    }
    .to_owned()
}

pub fn is_request_terminal_event(event: &GatewayEvent) -> bool {
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

pub fn summarize_slash_output(event: &GatewayEvent) -> Option<String> {
    let data = &event.data;
    if let Some(payload) = data.get("payload")
        && let Some(items) = payload.as_array()
    {
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
    data.get("text")
        .and_then(|value| value.as_str())
        .map(str::to_owned)
}

#[cfg(test)]
mod tests {
    use super::{is_request_terminal_event, slash_hints_from_event, summarize_slash_output};
    use craik_tui_rs::GatewayEvent;
    use serde_json::json;

    #[test]
    fn terminal_event_detection_covers_request_boundaries() {
        let completed = GatewayEvent {
            event_type: "run.completed".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({}),
        };
        let progress = GatewayEvent {
            event_type: "run.progress".to_owned(),
            created_at: None,
            run_id: Some("run_1".to_owned()),
            task_id: None,
            data: json!({}),
        };

        assert!(is_request_terminal_event(&completed));
        assert!(!is_request_terminal_event(&progress));
    }

    #[test]
    fn slash_catalog_parses_command_hints() {
        let event = GatewayEvent {
            event_type: "slash.catalog".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "commands": [
                    {"name": "run", "usage": "/run <prompt>", "summary": "Run an audited prompt.", "category": "Run"},
                    {"name": "status", "usage": "/status", "summary": "Show Gateway status."}
                ]
            }),
        };

        let hints = slash_hints_from_event(&event);

        assert_eq!(hints.len(), 2);
        assert_eq!(hints[0].name, "run");
        assert_eq!(hints[0].usage, "/run <prompt>");
        assert_eq!(hints[0].category, "Run");
        assert_eq!(hints[1].summary, "Show Gateway status.");
        assert_eq!(hints[1].category, "Session");
    }

    #[test]
    fn slash_output_summarizes_structured_payloads() {
        let event = GatewayEvent {
            event_type: "slash.completed".to_owned(),
            created_at: None,
            run_id: None,
            task_id: None,
            data: json!({
                "payload": [
                    {"id": "run_1", "status": "completed", "runner_id": "claude-code"},
                    {"id": "run_2", "status": "failed", "runner_id": "openai"}
                ]
            }),
        };

        let summary = summarize_slash_output(&event).expect("summary exists");

        assert!(summary.contains("2 records"));
        assert!(summary.contains("run_1 [completed] via claude-code"));
        assert!(summary.contains("run_2 [failed] via openai"));
    }
}
