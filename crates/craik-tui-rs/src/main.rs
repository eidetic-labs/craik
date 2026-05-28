use anyhow::{Context, bail};
mod app;
mod backend;
mod gateway_events;
mod input;
mod render;
mod transcript;

use app::{InteractiveApp, LoopAction};
use craik_tui_rs::{
    app_state_from_events, approval_command_sequence, format_gateway_contract_issues,
    interrupt_command_sequence, model_command_sequence, parse_gateway_events,
    prompt_command_sequence, render_dashboard_text, render_replay_text, run_backend_commands,
    slash_command_sequence, status_command_sequence, summarize_gateway_events,
    validate_gateway_events,
};
use crossterm::{
    event::{self, Event, KeyEventKind},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use input::{input_cursor_position, render_input_lines};
use ratatui::{
    Terminal,
    backend::{CrosstermBackend, TestBackend},
    layout::{Constraint, Direction, Layout},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
};
use render::{ActivityMetrics, render_activity_panel, status_line};
use std::{
    env, fs,
    io::{self, IsTerminal},
    time::Duration,
};
use transcript::{render_transcript_lines, transcript_scroll_offset};

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
                .scroll((
                    transcript_scroll_offset(
                        &app.transcript,
                        app.transcript_scroll,
                        transcript_height,
                    ),
                    0,
                ))
                .wrap(Wrap { trim: false });
            frame.render_widget(transcript, body[0]);

            let activity = Paragraph::new(render_activity_panel(
                &app.state,
                ActivityMetrics {
                    slash_commands: app.slash_catalog.len(),
                    queued_inputs: app.queued_inputs.len(),
                    last_error: app.last_error.as_deref(),
                },
            ))
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
            let input = Paragraph::new(render_input_lines(&app.input, &app.slash_catalog))
                .block(input_block)
                .wrap(Wrap { trim: false });
            frame.render_widget(input, vertical[1]);
            frame.set_cursor_position(input_cursor_position(
                &app.input,
                app.input_cursor,
                input_inner,
            ));

            let footer = Paragraph::new(status_line(&app.state, app.in_flight));
            frame.render_widget(footer, vertical[2]);
        })?;

        if event::poll(Duration::from_millis(80))?
            && let Event::Key(key) = event::read()?
        {
            if key.kind != KeyEventKind::Press {
                continue;
            }
            if app.handle_key(key) == LoopAction::Exit {
                break;
            }
        }
    }
    Ok(())
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
    let issues = validate_gateway_events(&events);
    if !issues.is_empty() {
        bail!(
            "Gateway replay contains invalid events: {}",
            format_gateway_contract_issues(&issues)
        );
    }
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
