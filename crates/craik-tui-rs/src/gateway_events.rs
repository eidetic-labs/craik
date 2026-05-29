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
                aliases: string_array_from_object(object, "aliases"),
                choices: choices_from_object(object),
                subcommands: explicit_or_usage_subcommands(object),
                requires_confirmation: object
                    .get("requires_confirmation")
                    .or_else(|| object.get("requiresConfirmation"))
                    .and_then(|value| value.as_bool())
                    .unwrap_or(false),
                confirm_message: object
                    .get("confirm_message")
                    .or_else(|| object.get("confirmMessage"))
                    .and_then(|value| value.as_str())
                    .map(str::to_owned),
                cli_mirror: object
                    .get("cli_mirror")
                    .or_else(|| object.get("cliMirror"))
                    .and_then(|value| value.as_str())
                    .map(str::to_owned),
                required_args: string_array_from_object(object, "required_args"),
                examples: string_array_from_object(object, "examples"),
                current_value: object
                    .get("current_value")
                    .or_else(|| object.get("current"))
                    .and_then(|value| value.as_str())
                    .map(str::to_owned),
            })
        })
        .collect()
}

fn string_array_from_object(
    object: &serde_json::Map<String, serde_json::Value>,
    key: &str,
) -> Vec<String> {
    object
        .get(key)
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
        .filter_map(|value| value.as_str().map(str::to_owned))
        .collect()
}

fn choices_from_object(object: &serde_json::Map<String, serde_json::Value>) -> Vec<String> {
    let Some(choices) = object.get("choices") else {
        return Vec::new();
    };
    if let Some(array) = choices.as_array() {
        return array
            .iter()
            .filter_map(|value| value.as_str().map(str::to_owned))
            .collect();
    }
    choices
        .as_object()
        .into_iter()
        .flat_map(|items| items.values())
        .flat_map(|value| value.as_array().into_iter().flatten())
        .filter_map(|value| value.as_str().map(str::to_owned))
        .collect()
}

fn explicit_or_usage_subcommands(
    object: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    let explicit = string_array_from_object(object, "subcommands");
    if !explicit.is_empty() {
        return explicit;
    }
    subcommands_from_usage(
        object
            .get("usage")
            .and_then(|value| value.as_str())
            .unwrap_or_default(),
    )
}

fn subcommands_from_usage(usage: &str) -> Vec<String> {
    usage
        .split(['[', ']', '|'])
        .flat_map(|chunk| chunk.split_whitespace())
        .filter(|token| {
            token
                .chars()
                .all(|character| character.is_ascii_alphabetic() || character == '-')
        })
        .filter(|token| !matches!(*token, "prompt" | "provider" | "model" | "approval"))
        .map(str::to_owned)
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
            | "session.history"
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
                    {"name": "run", "usage": "/run <prompt>", "summary": "Run an audited prompt.", "category": "Run", "cli_mirror": "run prompt"},
                    {"name": "theme", "usage": "/theme [dark|light|monochrome]", "summary": "Set theme.", "choices": {"theme": ["dark", "light", "monochrome"]}, "current_value": "dark", "mutating": true, "aliases": ["style"], "examples": ["/theme light"]},
                    {"name": "logout", "usage": "/logout [profile]", "summary": "Log out.", "requires_confirmation": true, "confirm_message": "This command changes local Craik state."},
                    {"name": "status", "usage": "/status", "summary": "Show Gateway status."}
                ]
            }),
        };

        let hints = slash_hints_from_event(&event);

        assert_eq!(hints.len(), 4);
        assert_eq!(hints[0].name, "run");
        assert_eq!(hints[0].usage, "/run <prompt>");
        assert_eq!(hints[0].category, "Run");
        assert_eq!(hints[1].choices, ["dark", "light", "monochrome"]);
        assert_eq!(hints[1].current_value.as_deref(), Some("dark"));
        assert_eq!(hints[1].aliases, ["style"]);
        assert_eq!(hints[1].examples, ["/theme light"]);
        assert!(hints[2].requires_confirmation);
        assert_eq!(
            hints[2].confirm_message.as_deref(),
            Some("This command changes local Craik state.")
        );
        assert_eq!(hints[0].cli_mirror.as_deref(), Some("run prompt"));
        assert_eq!(hints[3].summary, "Show Gateway status.");
        assert_eq!(hints[3].category, "Session");
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
