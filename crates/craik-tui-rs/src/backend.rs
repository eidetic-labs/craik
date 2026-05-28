use anyhow::Context;
use craik_tui_rs::{GatewayCommand, GatewayEvent, encode_gateway_command, validate_gateway_event};
use std::{
    io::{self, BufRead, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{
        Arc, Mutex,
        mpsc::{self, Receiver},
    },
    thread,
};

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
                            let issues = validate_gateway_event(&event);
                            if issues.is_empty() {
                                let _ = event_sender.send(WorkerMessage::Event(event));
                            } else {
                                let issue_text = issues
                                    .into_iter()
                                    .map(|issue| issue.message)
                                    .collect::<Vec<_>>()
                                    .join("; ");
                                let _ = event_sender.send(WorkerMessage::Error(format!(
                                    "backend event contract violation for `{}`: {issue_text}",
                                    event.event_type
                                )));
                            }
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
            let _ = event_sender.send(WorkerMessage::Closed(
                "Gateway output stream closed.".to_owned(),
            ));
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
