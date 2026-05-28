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
    terminal::{disable_raw_mode, enable_raw_mode},
};
use input::{input_cursor_position, render_input_lines, render_search_lines};
use ratatui::{
    Frame, Terminal,
    backend::{CrosstermBackend, TestBackend},
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Padding, Paragraph, Wrap},
};
use render::{ActivityMetrics, render_activity_panel, render_provenance_panel, status_line};
use std::{
    env, fs,
    io::{self, IsTerminal},
    time::Duration,
};
use transcript::{
    TranscriptRenderOptions, render_transcript_lines_window, search_match_count,
    transcript_line_count, transcript_render_window_start, transcript_scroll_offset,
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

fn run_interactive_app() -> anyhow::Result<()> {
    enable_raw_mode()?;
    let stdout = io::stdout();
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    terminal.clear()?;
    let result = run_interactive_loop(&mut terminal);
    disable_raw_mode()?;
    terminal.show_cursor()?;
    result
}

fn run_interactive_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
) -> anyhow::Result<()> {
    let mut app = InteractiveApp::new()?;
    loop {
        app.drain_worker();
        terminal.draw(|frame| draw_interactive_frame(frame, &app))?;

        if event::poll(Duration::from_millis(80))? {
            match event::read()? {
                Event::Key(key) => {
                    if key.kind != KeyEventKind::Press {
                        continue;
                    }
                    if app.handle_key(key) == LoopAction::Exit {
                        break;
                    }
                }
                Event::Paste(text) => {
                    app.paste_text(&text);
                }
                _ => {}
            }
        }
    }
    app.shutdown();
    Ok(())
}

fn draw_interactive_frame(frame: &mut Frame<'_>, app: &InteractiveApp) {
    let area = frame.area();
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(8),
            Constraint::Length(input_panel_height(app)),
            Constraint::Length(1),
        ])
        .split(area);
    let transcript_options = TranscriptRenderOptions {
        expand_details: app.expand_transcript_details,
        search_query: active_search_query(app),
    };

    if app.transcript_focused || area.width < 100 {
        render_transcript_panel(frame, app, vertical[0], &transcript_options);
    } else {
        let body = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(64), Constraint::Percentage(36)])
            .split(vertical[0]);
        render_transcript_panel(frame, app, body[0], &transcript_options);

        let side = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Percentage(44), Constraint::Percentage(56)])
            .split(body[1]);
        let selected_approval_summary = app.selected_approval_summary();
        let selected_approval_preview = app.selected_approval_preview();
        let selected_run_summary = app.selected_run_summary();
        let selected_run_detail = app.selected_run_detail();
        let activity = Paragraph::new(render_activity_panel(
            &app.state,
            ActivityMetrics {
                slash_commands: app.slash_catalog.len(),
                queued_inputs: app.queued_inputs.len(),
                last_error: app.last_error.as_deref(),
                pending_approvals: app.pending_approval_count(),
                latest_pending_approval: app.latest_pending_approval(),
                selected_approval_summary: selected_approval_summary.as_deref(),
                selected_approval_preview: selected_approval_preview.as_deref(),
                selected_run_summary: selected_run_summary.as_deref(),
                selected_run_detail: selected_run_detail.as_deref(),
                backend_connected: app.backend_connected,
            },
        ))
        .block(Block::default().title("Activity").borders(Borders::ALL))
        .wrap(Wrap { trim: false });
        frame.render_widget(activity, side[0]);

        let provenance = Paragraph::new(render_provenance_panel(&app.selected_run_provenance()))
            .block(
                Block::default()
                    .title("Run provenance  Ctrl-J/K select  Ctrl-L filter")
                    .borders(Borders::ALL),
            )
            .wrap(Wrap { trim: false });
        frame.render_widget(provenance, side[1]);
    }

    if app.help_visible {
        let help = Paragraph::new(app.help_text())
            .block(
                Block::default()
                    .title("Help  Esc closes")
                    .borders(Borders::ALL)
                    .padding(Padding::horizontal(1)),
            )
            .wrap(Wrap { trim: false });
        frame.render_widget(help, vertical[0]);
    }

    let input_title = input_title(app);
    let input_block = Block::default()
        .title(Line::from(vec![Span::styled(
            input_title,
            Style::default().add_modifier(Modifier::BOLD),
        )]))
        .borders(Borders::ALL)
        .padding(Padding::horizontal(1));
    let input_inner = input_block.inner(vertical[1]);
    let mut input_lines = if app.search_active {
        render_search_lines(
            &app.search_query,
            search_match_count(&app.transcript, &app.search_query),
            app.search_match_index,
        )
    } else {
        render_input_lines(&app.input, &app.slash_catalog)
    };
    if !app.search_active {
        let context = app.prompt_context();
        if !context.is_empty() {
            input_lines.push(Line::from(Span::styled(
                "Readiness",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            )));
            input_lines.extend(context.lines().map(|line| {
                Line::from(Span::styled(
                    format!("  {line}"),
                    Style::default().fg(Color::DarkGray),
                ))
            }));
        }
    }
    let input = Paragraph::new(input_lines)
        .block(input_block)
        .wrap(Wrap { trim: false });
    frame.render_widget(input, vertical[1]);
    if app.search_active {
        frame.set_cursor_position(input_cursor_position(
            &app.search_query,
            app.search_query.len(),
            input_inner,
        ));
    } else {
        frame.set_cursor_position(input_cursor_position(
            &app.input,
            app.input_cursor,
            input_inner,
        ));
    }

    let footer = Paragraph::new(status_line(
        &app.state,
        app.in_flight,
        app.latest_pending_approval(),
        app.transcript_focused,
        app.search_active,
        !app.expand_transcript_details,
    ));
    frame.render_widget(footer, vertical[2]);
}

fn input_panel_height(app: &InteractiveApp) -> u16 {
    if app.search_active {
        5
    } else if app.input.trim_start().starts_with('/') {
        12
    } else {
        let content_lines = app.input_line_count().min(8) as u16;
        let context_lines = app.prompt_context().lines().count().min(4) as u16;
        (content_lines + context_lines + 5).clamp(8, 15)
    }
}

fn input_title(app: &InteractiveApp) -> String {
    if app.search_active {
        return "Search  Enter closes / Ctrl-N next / Ctrl-P previous / Esc cancel".to_owned();
    }
    let (line, col) = app.input_cursor_line_col();
    format!(
        "Prompt  {} line(s), {} char(s), cursor {line}:{col}  Enter sends / Ctrl-Y retry / Ctrl-C stop / Alt-Enter newline",
        app.input_line_count(),
        app.input_char_count()
    )
}

fn render_transcript_panel(
    frame: &mut Frame<'_>,
    app: &InteractiveApp,
    area: ratatui::layout::Rect,
    options: &TranscriptRenderOptions<'_>,
) {
    let transcript_height = area.height.saturating_sub(2);
    let offset = transcript_scroll_offset(
        &app.transcript,
        options,
        app.transcript_scroll,
        transcript_height,
    );
    let transcript = Paragraph::new(render_transcript_lines_window(
        &app.transcript,
        options,
        offset,
        transcript_height,
    ))
    .block(
        Block::default()
            .title(transcript_title(
                app,
                options,
                transcript_height,
                area.width,
            ))
            .borders(Borders::ALL),
    )
    .scroll((
        offset.saturating_sub(transcript_render_window_start(offset)),
        0,
    ))
    .wrap(Wrap { trim: false });
    frame.render_widget(transcript, area);
}

fn transcript_title(
    app: &InteractiveApp,
    options: &TranscriptRenderOptions<'_>,
    visible_height: u16,
    visible_width: u16,
) -> Line<'static> {
    let total = transcript_line_count(&app.transcript, options);
    let offset = transcript_scroll_offset(
        &app.transcript,
        options,
        app.transcript_scroll,
        visible_height,
    );
    let top = if total == 0 {
        0
    } else {
        offset.saturating_add(1)
    };
    let bottom = offset.saturating_add(visible_height).min(total);
    let search_count = search_match_count(&app.transcript, &app.search_query);
    let jump = app
        .transcript_jump_summary()
        .map(|summary| format!(" | Jump: {summary}"))
        .unwrap_or_default();
    let detail_mode = if app.expand_transcript_details {
        "expanded"
    } else {
        "collapsed"
    };
    let tail_mode = if app.transcript_scroll == 0 {
        "following"
    } else {
        "scrolled back"
    };
    let focus_mode = if app.transcript_focused {
        "focused"
    } else {
        "split"
    };
    let search = if active_search_query(app).is_some() {
        if let Some(index) = app.search_match_index {
            format!(" | Search: {}/{} matches", index + 1, search_count)
        } else {
            format!(" | Search: {} matches", search_count)
        }
    } else {
        String::new()
    };
    if visible_width < 84 {
        return Line::from(format!(
            "Transcript | {top}-{bottom}/{total} | {tail_mode} | {detail_mode}{search}{jump}"
        ));
    }
    Line::from(format!(
        "Transcript {focus_mode} | Lines {top}-{bottom}/{total} | Tail {tail_mode} | Details {detail_mode}{search}{jump}"
    ))
}

fn active_search_query(app: &InteractiveApp) -> Option<&str> {
    let query = app.search_query.trim();
    (!query.is_empty()).then_some(query)
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
        "Craik Rust/Ratatui operator TUI",
        "",
        "Interactive:",
        "  craik-tui-rs",
        "  craik tui",
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
        InteractiveApp, Terminal, TestBackend, draw_interactive_frame, input_panel_height,
        input_title,
    };
    use craik_tui_rs::parse_gateway_events;

    const CLAUDE_CODE_STREAM: &str =
        include_str!("../../../tests/fixtures/gateway/claude_code_stream.jsonl");

    #[test]
    fn interactive_frame_renders_core_regions() {
        let backend = TestBackend::new(100, 24);
        let mut terminal = Terminal::new(backend).expect("test terminal is created");
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.input = "Review the plan".to_owned();
        app.input_cursor = app.input.len();

        terminal
            .draw(|frame| draw_interactive_frame(frame, &app))
            .expect("interactive frame renders");

        let rendered = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect::<String>();

        assert!(rendered.contains("Transcript"));
        assert!(rendered.contains("Activity"));
        assert!(rendered.contains("Prompt"));
        assert!(rendered.contains("Review the plan"));
        assert!(rendered.contains("Craik"));
    }

    #[test]
    fn fixture_backed_wide_frame_renders_activity_and_evidence_context() {
        let app = app_from_fixture(CLAUDE_CODE_STREAM);
        let rendered = render_app_frame(&app, 140, 42);

        assert!(rendered.contains("Transcript"));
        assert!(rendered.contains("Activity"));
        assert!(rendered.contains("Run provenance"));
        assert!(rendered.contains("Receipts: 2"));
        assert!(rendered.contains("Tools"));
        assert!(rendered.contains("Approvals seen"));
        assert!(rendered.contains("normalized Gateway"));
        assert!(rendered.contains("Run completed"));
    }

    #[test]
    fn fixture_backed_narrow_frame_prioritizes_transcript_over_activity_panel() {
        let app = app_from_fixture(CLAUDE_CODE_STREAM);
        let rendered = render_app_frame(&app, 72, 24);

        assert!(rendered.contains("Transcript"));
        assert!(rendered.contains("Prompt"));
        assert!(rendered.contains("receipt_run_review_desktop_plan"));
        assert!(!rendered.contains("Activity"));
    }

    #[test]
    fn slash_input_gets_extra_panel_height_for_suggestions() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        assert_eq!(input_panel_height(&app), 8);
        app.input = "/r".to_owned();
        assert_eq!(input_panel_height(&app), 12);
        app.search_active = true;
        assert_eq!(input_panel_height(&app), 5);
    }

    #[test]
    fn prompt_input_height_grows_with_multiline_content() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        assert_eq!(input_panel_height(&app), 8);
        app.input = "one\ntwo\nthree\nfour".to_owned();

        assert_eq!(input_panel_height(&app), 11);
        assert!(input_title(&app).contains("4 line(s)"));
    }

    #[test]
    fn terminal_setup_does_not_capture_mouse_or_enter_alternate_screen() {
        let source = include_str!("main.rs");

        assert!(!source.contains(&["Enter", "AlternateScreen"].concat()));
        assert!(!source.contains(&["Enable", "MouseCapture"].concat()));
        assert!(!source.contains(&["Disable", "MouseCapture"].concat()));
    }

    fn app_from_fixture(input: &str) -> InteractiveApp {
        let events = parse_gateway_events(input).expect("fixture parses");
        let mut app = InteractiveApp::for_test_with_messages([]);
        for event in events {
            app.state.apply_event(&event);
            app.record_event(&event);
        }
        app
    }

    fn render_app_frame(app: &InteractiveApp, width: u16, height: u16) -> String {
        let backend = TestBackend::new(width, height);
        let mut terminal = Terminal::new(backend).expect("test terminal is created");
        terminal
            .draw(|frame| draw_interactive_frame(frame, app))
            .expect("interactive frame renders");
        terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect::<String>()
    }
}
