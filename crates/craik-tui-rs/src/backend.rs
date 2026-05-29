use anyhow::Context;
use craik_tui_rs::{
    GatewayCommand, GatewayEvent, encode_gateway_command, format_gateway_contract_diagnostic,
    validate_gateway_event,
};
use std::{
    error::Error,
    io::{self, BufRead, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{
        Arc, Mutex,
        mpsc::{self, Receiver},
    },
    thread,
};

const BACKEND_COMMAND: &str = "uv run craik tui-backend --jsonl";

#[derive(Debug, Clone)]
pub enum WorkerMessage {
    Event(GatewayEvent),
    Error(String),
    Closed(String),
}

pub struct BackendSession {
    stdin: Option<Arc<Mutex<ChildStdin>>>,
    pub receiver: Receiver<WorkerMessage>,
    child: Option<Child>,
}

impl BackendSession {
    pub fn start() -> anyhow::Result<Self> {
        let mut child = Command::new("uv")
            .args(["run", "craik", "tui-backend", "--jsonl"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| anyhow::anyhow!("{}", format_backend_start_error(&error)))?;
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
                            let issues = validate_gateway_event(&event);
                            if issues.is_empty() {
                                let _ = event_sender.send(WorkerMessage::Event(event));
                            } else {
                                let _ = event_sender.send(WorkerMessage::Error(
                                    format_gateway_contract_diagnostic(&event, &issues),
                                ));
                            }
                        }
                        Err(error) => {
                            let _ = event_sender.send(WorkerMessage::Error(
                                format_backend_parse_error(&error, &line),
                            ));
                        }
                    },
                    Err(error) => {
                        let _ = event_sender
                            .send(WorkerMessage::Error(format_backend_read_error(&error)));
                        break;
                    }
                }
            }
            let _ = event_sender.send(WorkerMessage::Closed(format_backend_closed()));
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
    pub fn for_test(receiver: Receiver<WorkerMessage>) -> Self {
        Self {
            stdin: None,
            receiver,
            child: None,
        }
    }

    pub fn send(&self, command: &GatewayCommand) -> anyhow::Result<()> {
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

    pub fn close(&mut self) -> anyhow::Result<()> {
        let result = self.send(&GatewayCommand::SessionClose);
        self.stdin = None;
        result
    }
}

pub fn format_backend_start_error(error: &dyn Error) -> String {
    [
        "Gateway backend failed to start.".to_owned(),
        format!("Command: {BACKEND_COMMAND}"),
        format!("Cause: {error}"),
        "Recovery: run `uv run craik tui-backend --jsonl` from this repo to inspect the backend, then press Ctrl-B in the TUI to reconnect.".to_owned(),
    ]
    .join("\n")
}

pub fn format_backend_parse_error(error: &dyn Error, line: &str) -> String {
    [
        "Gateway backend emitted non-contract JSON.".to_owned(),
        format!("Command: {BACKEND_COMMAND}"),
        format!("Cause: {error}"),
        format!("Line: {}", line.trim()),
        "Recovery: inspect the backend stderr/log output and keep stdout reserved for Gateway JSONL events.".to_owned(),
    ]
    .join("\n")
}

pub fn format_backend_read_error(error: &dyn Error) -> String {
    [
        "Gateway backend output stream failed.".to_owned(),
        format!("Command: {BACKEND_COMMAND}"),
        format!("Cause: {error}"),
        "Recovery: restart the backend with Ctrl-B; if this repeats, run the backend command directly and inspect stderr.".to_owned(),
    ]
    .join("\n")
}

pub fn format_backend_closed() -> String {
    [
        "Gateway backend output stream closed.".to_owned(),
        format!("Command: {BACKEND_COMMAND}"),
        "Recovery: press Ctrl-B to restart the Gateway backend. If it closes again, run the command directly to inspect stderr.".to_owned(),
    ]
    .join("\n")
}

impl Drop for BackendSession {
    fn drop(&mut self) {
        let _ = self.close();
        if let Some(child) = &mut self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        format_backend_closed, format_backend_parse_error, format_backend_read_error,
        format_backend_start_error,
    };
    use std::io;

    #[test]
    fn backend_start_error_names_command_and_recovery() {
        let error = io::Error::new(io::ErrorKind::NotFound, "uv not found");

        let diagnostic = format_backend_start_error(&error);

        assert!(diagnostic.contains("Gateway backend failed to start."));
        assert!(diagnostic.contains("uv run craik tui-backend --jsonl"));
        assert!(diagnostic.contains("uv not found"));
        assert!(diagnostic.contains("press Ctrl-B"));
    }

    #[test]
    fn backend_parse_error_preserves_bad_line() {
        let error = serde_json::from_str::<serde_json::Value>("not-json")
            .expect_err("invalid JSON should fail");

        let diagnostic = format_backend_parse_error(&error, "not-json");

        assert!(diagnostic.contains("non-contract JSON"));
        assert!(diagnostic.contains("Line: not-json"));
        assert!(diagnostic.contains("stdout reserved for Gateway JSONL"));
    }

    #[test]
    fn backend_read_and_close_errors_are_actionable() {
        let error = io::Error::other("stream interrupted");

        assert!(format_backend_read_error(&error).contains("Ctrl-B"));
        assert!(format_backend_closed().contains("run the command directly"));
    }
}
