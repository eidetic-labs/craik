use anyhow::{Context, bail};
mod app;
mod backend;
mod gateway_events;
mod input;
mod model_names;
mod render;
mod theme;
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
use input::{
    input_cursor_position, render_input_lines, render_search_lines, render_slash_palette_lines,
};
use ratatui::{
    Frame, Terminal, TerminalOptions, Viewport,
    backend::{Backend, CrosstermBackend, TestBackend},
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Clear, Padding, Paragraph, Widget, Wrap},
};
use render::{StatusLineMetrics, status_line};
use std::{
    env, fs,
    io::{self, IsTerminal},
    time::Duration,
};
use transcript::{TranscriptRenderOptions, render_transcript_lines, search_match_count};
#[cfg(test)]
use transcript::{render_transcript_lines_window, transcript_line_count, transcript_scroll_offset};

const NATIVE_LIVE_VIEWPORT_HEIGHT: u16 = 14;

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
                    .border_style(theme::mute_style())
                    .borders(Borders::ALL)
                    .border_type(BorderType::Rounded),
            ),
            frame.area(),
        );
    })?;

    println!("{rendered}");
    Ok(())
}

fn run_interactive_app() -> anyhow::Result<()> {
    initialize_detected_theme();
    enable_raw_mode()?;
    let stdout = io::stdout();
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::with_options(
        backend,
        TerminalOptions {
            viewport: Viewport::Inline(NATIVE_LIVE_VIEWPORT_HEIGHT),
        },
    )?;
    let result = run_interactive_loop(&mut terminal);
    disable_raw_mode()?;
    terminal.show_cursor()?;
    result
}

fn initialize_detected_theme() {
    // An explicit OSC 11 response (tests / CI / terminal wrappers) wins.
    if let Ok(response) = env::var("CRAIK_TUI_OSC11_RESPONSE")
        && theme::set_detected_terminal_mode_from_osc11(&response)
    {
        return;
    }
    detect_terminal_background();
}

fn detect_terminal_background() {
    use terminal_colorsaurus::{QueryOptions, ThemeMode as TerminalThemeMode, theme_mode};
    // Queries the terminal's background (OSC 11) with a bounded timeout and a
    // safe fallback: on a non-TTY, a non-responding terminal, or any error this
    // returns Err and we leave detection to COLORFGBG / the dark default.
    if let Ok(mode) = theme_mode(QueryOptions::default()) {
        theme::set_detected_terminal_mode(match mode {
            TerminalThemeMode::Dark => theme::ThemeMode::Dark,
            TerminalThemeMode::Light => theme::ThemeMode::Light,
        });
    }
}

fn run_interactive_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
) -> anyhow::Result<()> {
    let mut app = InteractiveApp::new()?;
    let mut native_transcript = NativeTranscriptState::default();
    loop {
        app.drain_worker();
        flush_native_transcript(terminal, &mut native_transcript, &app)?;
        terminal.draw(|frame| draw_native_live_frame(frame, &app))?;

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

#[derive(Default)]
struct NativeTranscriptState {
    flushed_entries: usize,
}

fn flush_native_transcript<B: Backend>(
    terminal: &mut Terminal<B>,
    state: &mut NativeTranscriptState,
    app: &InteractiveApp,
) -> Result<(), B::Error> {
    if state.flushed_entries > app.transcript.len() {
        state.flushed_entries = 0;
    }
    if state.flushed_entries == app.transcript.len() {
        return Ok(());
    }

    let size = terminal.size()?;
    let options = TranscriptRenderOptions {
        expand_details: app.expand_transcript_details,
        search_query: None,
        content_width: Some(transcript_content_width(size.width)),
    };
    let lines = render_transcript_lines(&app.transcript[state.flushed_entries..], &options);
    let lines = wrap_transcript_lines(lines, transcript_content_width(size.width));
    if lines.is_empty() {
        state.flushed_entries = app.transcript.len();
        return Ok(());
    }

    let height = u16::try_from(lines.len()).unwrap_or(u16::MAX);
    terminal.insert_before(height, |buffer| {
        Paragraph::new(lines).render(buffer.area, buffer);
    })?;
    state.flushed_entries = app.transcript.len();
    Ok(())
}

fn draw_native_live_frame(frame: &mut Frame<'_>, app: &InteractiveApp) {
    let area = frame.area();
    if app.help_visible {
        let help = Paragraph::new(app.help_text())
            .block(
                Block::default()
                    .title("▌HELP  Esc closes")
                    .title_style(theme::accent_style())
                    .border_style(theme::mute_style())
                    .borders(Borders::LEFT)
                    .padding(Padding::horizontal(1)),
            )
            .wrap(Wrap { trim: false });
        frame.render_widget(help, area);
        return;
    }
    if app.active_overlay.is_some() {
        render_active_overlay(frame, app, area);
        return;
    }

    let slash_palette_lines = if app.search_active {
        Vec::new()
    } else {
        render_slash_palette_lines(&app.input, &app.slash_catalog, app.slash_selected_index)
    };
    let palette_height = slash_palette_lines.len().min(6) as u16;
    let input_height = input_panel_height(app);
    let footer_height = 1;
    let activity_lines = model_activity_line(app)
        .map(|line| wrap_transcript_line(line, transcript_content_width(area.width)))
        .unwrap_or_default();
    let activity_height = u16::try_from(activity_lines.len()).unwrap_or(u16::MAX);
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(0),
            Constraint::Length(activity_height),
            Constraint::Length(palette_height),
            Constraint::Length(input_height),
            Constraint::Length(footer_height),
        ])
        .split(area);

    if !activity_lines.is_empty() {
        frame.render_widget(
            Paragraph::new(activity_lines)
                .style(theme::surface_style())
                .wrap(Wrap { trim: false }),
            vertical[1],
        );
    }

    if !slash_palette_lines.is_empty() {
        let slash_palette = Paragraph::new(slash_palette_lines)
            .block(
                Block::default()
                    .borders(Borders::LEFT)
                    .border_style(Style::default().fg(theme::accent()))
                    .style(theme::surface_style())
                    .padding(Padding::horizontal(1)),
            )
            .style(theme::surface_style())
            .wrap(Wrap { trim: false });
        frame.render_widget(slash_palette, vertical[2]);
    }

    render_input_panel(frame, app, vertical[3]);
    render_footer(frame, app, vertical[4]);
}

#[cfg(test)]
fn draw_interactive_frame(frame: &mut Frame<'_>, app: &InteractiveApp) {
    let area = frame.area();
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(8),
            Constraint::Length(1),
            Constraint::Length(input_panel_height(app)),
            Constraint::Length(1),
        ])
        .split(area);
    let transcript_options = TranscriptRenderOptions {
        expand_details: app.expand_transcript_details,
        search_query: active_search_query(app),
        content_width: Some(transcript_content_width(area.width)),
    };

    let slash_palette_lines =
        if app.search_active || app.help_visible || app.active_overlay.is_some() {
            Vec::new()
        } else {
            render_slash_palette_lines(&app.input, &app.slash_catalog, app.slash_selected_index)
        };
    let (transcript_area, slash_palette_area) = if slash_palette_lines.is_empty() {
        (vertical[0], None)
    } else {
        let palette_height = slash_palette_lines.len().min(6) as u16;
        let body = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(8), Constraint::Length(palette_height)])
            .split(vertical[0]);
        (body[0], Some(body[1]))
    };

    render_transcript_panel(frame, app, transcript_area, &transcript_options);

    if app.help_visible {
        let help = Paragraph::new(app.help_text())
            .block(
                Block::default()
                    .title("▌HELP  Esc closes")
                    .title_style(theme::accent_style())
                    .border_style(theme::mute_style())
                    .borders(Borders::LEFT)
                    .padding(Padding::horizontal(1)),
            )
            .wrap(Wrap { trim: false });
        frame.render_widget(help, transcript_area);
    } else if app.active_overlay.is_some() {
        render_active_overlay(frame, app, transcript_area);
    } else if let Some(slash_palette_area) = slash_palette_area {
        let slash_palette = Paragraph::new(slash_palette_lines)
            .block(
                Block::default()
                    .borders(Borders::LEFT)
                    .border_style(Style::default().fg(theme::accent()))
                    .style(theme::surface_style())
                    .padding(Padding::horizontal(1)),
            )
            .style(theme::surface_style())
            .wrap(Wrap { trim: false });
        frame.render_widget(slash_palette, slash_palette_area);
    }

    render_input_panel(frame, app, vertical[2]);
    render_footer(frame, app, vertical[3]);
}

fn render_input_panel(frame: &mut Frame<'_>, app: &InteractiveApp, area: Rect) {
    let input_title = input_title(app);
    let mut input_block = Block::default()
        .borders(Borders::LEFT)
        .border_style(Style::default().fg(theme::accent()))
        .style(theme::surface_style())
        .padding(Padding::horizontal(1));
    if !input_title.is_empty() {
        input_block = input_block.title(Line::from(vec![Span::styled(
            input_title,
            theme::accent_style(),
        )]));
    }
    let input_inner = input_block.inner(area);
    let input_lines = if app.search_active {
        render_search_lines(
            &app.search_query,
            search_match_count(&app.transcript, &app.search_query),
            app.search_match_index,
        )
    } else {
        render_input_lines(&app.input, &app.slash_catalog)
    };
    let input_row_offset = centered_input_row_offset(input_inner.height, input_lines.len());
    let input_lines = vertically_center_input_lines(input_lines, input_row_offset);
    let input = Paragraph::new(input_lines)
        .block(input_block)
        .wrap(Wrap { trim: false });
    frame.render_widget(input, area);
    let cursor_area = Rect {
        y: input_inner.y.saturating_add(input_row_offset),
        height: input_inner.height.saturating_sub(input_row_offset),
        ..input_inner
    };
    if app.search_active {
        frame.set_cursor_position(input_cursor_position(
            &app.search_query,
            app.search_query.len(),
            cursor_area,
        ));
    } else {
        frame.set_cursor_position(input_cursor_position(
            &app.input,
            app.input_cursor,
            cursor_area,
        ));
    }
}

fn render_footer(frame: &mut Frame<'_>, app: &InteractiveApp, area: Rect) {
    let footer = Paragraph::new(status_line(
        &app.state,
        StatusLineMetrics {
            in_flight: app.in_flight,
            pending_approval: app.latest_pending_approval(),
            approval_reviewed: app.active_overlay == Some(app::ActiveOverlay::Approvals)
                && app.approval_overlay_reviewed,
            backend_connected: app.backend_connected,
            queued_inputs: app.queued_inputs.len(),
            active_overlay: app.active_overlay.map(|overlay| overlay.title()),
            search_active: app.search_active,
            details_collapsed: !app.expand_transcript_details,
        },
    ));
    frame.render_widget(footer, area);
}

fn render_active_overlay(frame: &mut Frame<'_>, app: &InteractiveApp, area: ratatui::layout::Rect) {
    if app.active_overlay == Some(app::ActiveOverlay::Approvals) {
        render_approval_overlay(frame, app, area);
        return;
    }
    render_browse_overlay(frame, app, area);
}

fn render_browse_overlay(frame: &mut Frame<'_>, app: &InteractiveApp, area: ratatui::layout::Rect) {
    let body = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(38), Constraint::Percentage(62)])
        .split(area);
    let list_area = body[0];
    let detail_area = body[1];
    let title = app
        .overlay_title()
        .unwrap_or_else(|| "▌OVERLAY  Esc returns to chat".to_owned());
    let items = app.overlay_items();
    let visible_capacity = list_area.height.saturating_sub(4) as usize;
    let mut list_lines = vec![
        Line::from(vec![
            Span::styled("▌", theme::accent_style()),
            Span::styled(" filter  ", theme::mute_style()),
            Span::styled(
                if app.overlay_filter.is_empty() {
                    "type to narrow"
                } else {
                    app.overlay_filter.as_str()
                },
                if app.overlay_filter.is_empty() {
                    theme::dim_style()
                } else {
                    theme::accent_style()
                },
            ),
        ]),
        Line::from(Span::styled(
            format!(
                "{} {}",
                items.len(),
                if items.len() == 1 { "item" } else { "items" }
            ),
            theme::dim_style(),
        )),
        Line::from(""),
    ];
    for (index, item) in items
        .iter()
        .enumerate()
        .skip(app.overlay_scroll as usize)
        .take(visible_capacity)
    {
        let selected = index == app.overlay_selected_index;
        let marker = if selected { "▌ " } else { "  " };
        let row_style = overlay_row_style(selected);
        list_lines.push(Line::from(vec![
            Span::styled(
                marker,
                if selected {
                    theme::accent_style()
                } else {
                    theme::mute_style()
                },
            ),
            Span::styled(item.title.clone(), row_style),
        ]));
        list_lines.push(Line::from(vec![
            Span::styled("   ", theme::mute_style()),
            Span::styled(item.summary.clone(), overlay_summary_style(selected)),
        ]));
    }
    if items.is_empty() {
        list_lines.push(Line::from(Span::styled(
            "No matching items.",
            theme::dim_style(),
        )));
    }
    let list = Paragraph::new(list_lines)
        .block(
            Block::default()
                .title(title)
                .title_style(theme::accent_style())
                .border_style(theme::accent_style())
                .borders(Borders::LEFT)
                .padding(Padding::horizontal(1)),
        )
        .wrap(Wrap { trim: false });
    let detail = Paragraph::new(overlay_detail_lines(&app.selected_overlay_detail()))
        .block(
            Block::default()
                .title(overlay_detail_title(app))
                .title_style(theme::mute_style())
                .border_style(theme::mute_style())
                .borders(Borders::LEFT)
                .padding(Padding::horizontal(1)),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(Clear, area);
    frame.render_widget(list, list_area);
    frame.render_widget(detail, detail_area);
}

fn overlay_detail_title(app: &InteractiveApp) -> Line<'static> {
    Line::from(vec![
        Span::styled("selected", theme::accent_style()),
        Span::styled("  ", theme::mute_style()),
        Span::styled(
            app.overlay_footer_hint().unwrap_or("Esc chat").to_owned(),
            theme::mute_style(),
        ),
    ])
}

fn overlay_row_style(selected: bool) -> Style {
    if selected {
        theme::selected_style()
    } else {
        theme::primary_style()
    }
}

fn overlay_summary_style(selected: bool) -> Style {
    if selected {
        Style::default().fg(theme::primary())
    } else {
        theme::dim_style()
    }
}

fn overlay_detail_lines(detail: &str) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    for raw in detail.lines() {
        if raw.trim().is_empty() {
            lines.push(Line::default());
            continue;
        }
        if raw.starts_with("- ") {
            lines.push(Line::from(vec![
                Span::styled("  - ", theme::mute_style()),
                Span::styled(raw.trim_start_matches("- ").to_owned(), theme::dim_style()),
            ]));
            continue;
        }
        if let Some((label, value)) = raw.split_once(':') {
            lines.push(Line::from(vec![
                Span::styled(format!("{label}: "), theme::mute_style()),
                Span::styled(value.trim_start().to_owned(), theme::primary_style()),
            ]));
            continue;
        }
        if lines.is_empty() {
            lines.push(Line::from(Span::styled(
                raw.to_owned(),
                theme::accent_style(),
            )));
        } else {
            lines.push(Line::from(Span::styled(raw.to_owned(), theme::dim_style())));
        }
    }
    if lines.is_empty() {
        lines.push(Line::from(Span::styled(
            "No detail available.",
            theme::dim_style(),
        )));
    }
    lines
}

fn render_approval_overlay(
    frame: &mut Frame<'_>,
    app: &InteractiveApp,
    area: ratatui::layout::Rect,
) {
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage(6),
            Constraint::Percentage(88),
            Constraint::Percentage(6),
        ])
        .split(area);
    let horizontal = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(12),
            Constraint::Percentage(76),
            Constraint::Percentage(12),
        ])
        .split(vertical[1]);
    let overlay_area = horizontal[1];
    let body = app.overlay_text().unwrap_or_default();
    let title = approval_overlay_title(&body);
    let border_style = if body.contains("Warning:") {
        Style::default()
            .fg(theme::amber())
            .add_modifier(Modifier::BOLD)
    } else {
        theme::accent_style()
    };
    let overlay = Paragraph::new(approval_overlay_lines(&body))
        .block(
            Block::default()
                .title(title)
                .title_style(border_style)
                .border_style(border_style)
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .padding(Padding::horizontal(1)),
        )
        .style(theme::surface_style())
        .wrap(Wrap { trim: false });
    frame.render_widget(Clear, area);
    frame.render_widget(overlay, overlay_area);
}

fn approval_overlay_title(body: &str) -> Line<'static> {
    let origin = body
        .lines()
        .find_map(|line| line.strip_prefix("Origin: "))
        .unwrap_or("unknown origin");
    Line::from(vec![
        Span::styled("▌Approval", theme::accent_style()),
        Span::styled("  ", theme::mute_style()),
        Span::styled(origin.to_owned(), theme::dim_style()),
        Span::styled("  Esc defer", theme::mute_style()),
    ])
}

fn approval_overlay_lines(body: &str) -> Vec<Line<'static>> {
    let has_actions = body.lines().any(|line| line.starts_with("Actions:"));
    let mut rendered = Vec::new();
    for line in body.lines() {
        if line.starts_with("Actions:") {
            continue;
        }
        if line.starts_with("Warning:") {
            rendered.push(Line::from(Span::styled(
                line.to_owned(),
                Style::default()
                    .fg(theme::amber())
                    .add_modifier(Modifier::BOLD),
            )));
            continue;
        }
        if line == "Review required" {
            rendered.push(Line::from(vec![
                Span::styled("Decision", theme::mute_style()),
                Span::styled("  operator approval required", theme::primary_style()),
            ]));
            if has_actions {
                rendered.push(approval_actions_line());
            }
            continue;
        }
        if line == "Preview" || line == "Source request" || line == "Craik context" {
            rendered.push(Line::from(Span::styled(
                line.to_owned(),
                theme::accent_style(),
            )));
            continue;
        }
        if let Some(diff) = line.strip_prefix("  +") {
            rendered.push(Line::from(vec![
                Span::styled(
                    "  +",
                    Style::default()
                        .fg(theme::sage())
                        .bg(theme::sage_surface())
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    diff.to_owned(),
                    Style::default()
                        .fg(theme::primary())
                        .bg(theme::sage_surface()),
                ),
            ]));
            continue;
        }
        if let Some(diff) = line.strip_prefix("  -") {
            rendered.push(Line::from(vec![
                Span::styled(
                    "  -",
                    Style::default()
                        .fg(theme::red())
                        .bg(theme::red_surface())
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    diff.to_owned(),
                    Style::default()
                        .fg(theme::primary())
                        .bg(theme::red_surface()),
                ),
            ]));
            continue;
        }
        if let Some(command) = line.strip_prefix("  $ ") {
            rendered.push(Line::from(vec![
                Span::styled(
                    "  $ ",
                    Style::default()
                        .fg(theme::amber())
                        .bg(theme::surface())
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(command.to_owned(), theme::primary_style()),
            ]));
            continue;
        }
        if let Some((label, value)) = line.split_once(':') {
            let label_style = match label {
                "Queue" => theme::dim_style(),
                "Risk" | "Warning" => Style::default()
                    .fg(theme::amber())
                    .add_modifier(Modifier::BOLD),
                "Action" | "What" | "Target" | "Command" | "Tool" | "Capability" | "Scope"
                | "Size" => theme::mute_style().add_modifier(Modifier::BOLD),
                _ => theme::mute_style(),
            };
            rendered.push(Line::from(vec![
                Span::styled(format!("{label}: "), label_style),
                Span::styled(value.trim_start().to_owned(), theme::primary_style()),
            ]));
            continue;
        }
        rendered.push(Line::from(line.to_owned()));
    }
    rendered
}

fn approval_actions_line() -> Line<'static> {
    Line::from(vec![
        Span::styled("Actions: ", theme::mute_style()),
        Span::styled(
            "[Ctrl-A] approve",
            Style::default()
                .fg(theme::sage())
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw("  "),
        Span::styled(
            "[Ctrl-X] deny",
            Style::default()
                .fg(theme::red())
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw("  "),
        Span::styled("[Esc] defer", theme::dim_style()),
    ])
}

fn input_panel_height(app: &InteractiveApp) -> u16 {
    if app.search_active {
        4
    } else if app.input.trim_start().starts_with('/') {
        3
    } else {
        let content_lines = app.input_line_count().min(8) as u16;
        (content_lines + 2).clamp(3, 10)
    }
}

fn centered_input_row_offset(input_height: u16, line_count: usize) -> u16 {
    let visible_lines = u16::try_from(line_count)
        .unwrap_or(u16::MAX)
        .min(input_height);
    input_height.saturating_sub(visible_lines) / 2
}

fn vertically_center_input_lines(lines: Vec<Line<'static>>, row_offset: u16) -> Vec<Line<'static>> {
    let mut centered = Vec::with_capacity(lines.len().saturating_add(usize::from(row_offset)));
    centered.extend((0..row_offset).map(|_| Line::default()));
    centered.extend(lines);
    centered
}

fn input_title(app: &InteractiveApp) -> String {
    if app.search_active {
        return "▌Search  Enter closes / Ctrl-N next / Ctrl-P previous / Esc cancel".to_owned();
    }
    String::new()
}

#[cfg(test)]
fn render_transcript_panel(
    frame: &mut Frame<'_>,
    app: &InteractiveApp,
    area: ratatui::layout::Rect,
    options: &TranscriptRenderOptions<'_>,
) {
    let activity_line = model_activity_line(app);
    let content_width = transcript_content_width(area.width);
    let activity_lines = activity_line
        .map(|line| {
            let mut lines = Vec::from([Line::default()]);
            lines.extend(wrap_transcript_line(line, content_width));
            lines
        })
        .unwrap_or_default();
    let activity_height = u16::try_from(activity_lines.len()).unwrap_or(u16::MAX);
    let transcript_height = area
        .height
        .saturating_sub(1)
        .saturating_sub(activity_height);
    let offset = transcript_scroll_offset(
        &app.transcript,
        options,
        app.transcript_scroll,
        transcript_height,
    );
    let transcript_lines =
        render_transcript_lines_window(&app.transcript, options, offset, transcript_height);
    let mut transcript_lines = visible_wrapped_transcript_lines(
        transcript_lines,
        content_width,
        transcript_height,
        app.transcript_scroll,
    );
    transcript_lines.extend(activity_lines);
    let transcript = Paragraph::new(transcript_lines).block(
        Block::default()
            .title(transcript_title(
                app,
                options,
                transcript_height,
                area.width,
            ))
            .title_style(theme::accent_style())
            .border_style(theme::mute_style())
            .borders(Borders::LEFT)
            .padding(Padding::horizontal(1)),
    );
    frame.render_widget(transcript, area);
}

#[cfg(test)]
fn visible_wrapped_transcript_lines(
    lines: Vec<Line<'static>>,
    width: usize,
    visible_height: u16,
    transcript_scroll: u16,
) -> Vec<Line<'static>> {
    let wrapped = wrap_transcript_lines(lines, width);
    let visible_height = usize::from(visible_height);
    if visible_height == 0 || wrapped.len() <= visible_height {
        return wrapped;
    }
    let end = wrapped
        .len()
        .saturating_sub(usize::from(transcript_scroll))
        .max(visible_height)
        .min(wrapped.len());
    let start = end.saturating_sub(visible_height);
    wrapped[start..end].to_vec()
}

fn model_activity_line(app: &InteractiveApp) -> Option<Line<'static>> {
    let label = if app.pending_approval_count() > 0 {
        "waiting for approval"
    } else if matches!(app.state.working_phase.as_deref(), Some("thinking")) {
        "thinking"
    } else if app.state.working_phase.is_some()
        || matches!(app.state.run_status.as_deref(), Some("running"))
    {
        "working"
    } else {
        return None;
    };
    let detail = latest_activity_detail(app);
    Some(Line::from(vec![
        Span::raw("  "),
        Span::styled("◐ ", Style::default().fg(theme::amber())),
        Span::styled(label.to_owned(), theme::primary_style()),
        Span::styled("  ", theme::mute_style()),
        Span::styled(detail, theme::dim_style()),
    ]))
}

fn latest_activity_detail(app: &InteractiveApp) -> String {
    if let Some(message) = app.state.progress_messages.last() {
        return compact_activity_detail(message);
    }
    if let Some(item) = app.state.tool_events.last() {
        let detail = item
            .detail
            .as_deref()
            .map(|value| format!("{}: {value}", item.label))
            .unwrap_or_else(|| item.label.clone());
        return compact_activity_detail(&detail);
    }
    if let Some(command) = app.state.commands.last() {
        return compact_activity_detail(command);
    }
    app.state
        .backend
        .as_deref()
        .map(|backend| format!("{backend} is active"))
        .unwrap_or_else(|| "waiting for the next event".to_owned())
}

fn compact_activity_detail(value: &str) -> String {
    const MAX_CHARS: usize = 96;
    let compact = value.split_whitespace().collect::<Vec<_>>().join(" ");
    if compact.chars().count() <= MAX_CHARS {
        compact
    } else {
        format!(
            "{}...",
            compact
                .chars()
                .take(MAX_CHARS.saturating_sub(3))
                .collect::<String>()
        )
    }
}

fn transcript_content_width(area_width: u16) -> usize {
    usize::from(area_width.saturating_sub(3)).max(1)
}

fn wrap_transcript_lines(lines: Vec<Line<'static>>, width: usize) -> Vec<Line<'static>> {
    if width < 12 {
        return lines;
    }
    lines
        .into_iter()
        .flat_map(|line| wrap_transcript_line(line, width))
        .collect()
}

fn wrap_transcript_line(line: Line<'static>, width: usize) -> Vec<Line<'static>> {
    let continuation_prefix = "  ";
    let continuation_width = continuation_prefix.chars().count();
    let mut output = Vec::new();
    let mut current = Vec::new();
    let mut current_width = 0usize;

    for span in line.spans {
        let style = span.style;
        let mut remaining = span.content.into_owned();
        while !remaining.is_empty() {
            if current_width >= width {
                output.push(Line::from(current));
                current = vec![Span::styled(continuation_prefix, theme::dim_style())];
                current_width = continuation_width;
            }
            let available = width.saturating_sub(current_width).max(1);
            let take = remaining.chars().take(available).collect::<String>();
            current_width = current_width.saturating_add(take.chars().count());
            current.push(Span::styled(take.clone(), style));
            remaining = remaining.chars().skip(take.chars().count()).collect();
            if !remaining.is_empty() {
                output.push(Line::from(current));
                current = vec![Span::styled(continuation_prefix, theme::dim_style())];
                current_width = continuation_width;
            }
        }
    }

    if current.is_empty() {
        output.push(Line::default());
    } else {
        output.push(Line::from(current));
    }
    output
}

#[cfg(test)]
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
        return Line::from(vec![
            Span::styled("▌Chat ", theme::accent_style()),
            Span::styled(
                format!("{top}-{bottom}/{total}  {tail_mode}  {detail_mode}{search}{jump}"),
                theme::mute_style(),
            ),
        ]);
    }
    Line::from(vec![
        Span::styled("▌Chat ", theme::accent_style()),
        Span::styled(format!("{focus_mode}  "), theme::primary_style()),
        Span::styled(
            format!(
                "lines {top}-{bottom}/{total}  tail {tail_mode}  details {detail_mode}{search}{jump}"
            ),
            theme::mute_style(),
        ),
    ])
}

#[cfg(test)]
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
        InteractiveApp, Terminal, TestBackend, approval_overlay_lines, approval_overlay_title,
        centered_input_row_offset, draw_interactive_frame, draw_native_live_frame,
        flush_native_transcript, input_panel_height, input_title, overlay_detail_lines,
        vertically_center_input_lines, visible_wrapped_transcript_lines,
    };
    use crate::{
        app::ActiveOverlay,
        theme::{ThemeMode, with_mode_for_test},
        transcript::{TranscriptEntry, TranscriptKind},
    };
    use craik_tui_rs::parse_gateway_events;
    use ratatui::{TerminalOptions, Viewport, text::Line};

    const CLAUDE_CODE_STREAM: &str =
        include_str!("../../../tests/fixtures/gateway/claude_code_stream.jsonl");
    const PROVIDER_FIXTURES: &[(&str, &str, &str)] = &[
        (
            include_str!(
                "../../../tests/fixtures/gateway/provider_anthropic_messages_stream.jsonl"
            ),
            "provider_anthropic_messages",
            "Sonnet 4",
        ),
        (
            include_str!("../../../tests/fixtures/gateway/provider_openai_responses_stream.jsonl"),
            "provider_openai_responses",
            "GPT-5.4",
        ),
        (
            include_str!("../../../tests/fixtures/gateway/provider_gemini_stream.jsonl"),
            "provider_gemini",
            "Google Gemini 2.5 Pro",
        ),
        (
            include_str!("../../../tests/fixtures/gateway/provider_local_ollama_stream.jsonl"),
            "provider_local_ollama",
            "Local Ollama Llama 3.1 8B",
        ),
    ];

    #[test]
    fn interactive_frame_renders_core_regions() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.input = "Review the plan".to_owned();
        app.input_cursor = app.input.len();
        let rows = render_app_frame_rows(&app, 100, 24);
        let rendered = rows.join("\n");

        assert!(rendered.contains("Chat"));
        assert!(!rendered.contains("Activity"));
        assert!(!rendered.contains("Run provenance"));
        assert!(rendered.contains("Review the plan"));
        assert!(rendered.contains("ask"));
        assert_eq!(rows.len(), 24);
        assert!(!rows.iter().any(|row| row.contains("▌Prompt")));
        assert!(!rendered.contains("Type a prompt"));
        assert!(!rendered.contains("Enter sends"));
        assert!(!rendered.contains("Alt-Enter newline"));
    }

    #[test]
    fn fixture_backed_wide_frame_keeps_chat_home_full_width() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = None;
        let rendered = render_app_frame(&app, 140, 42);

        assert!(rendered.contains("Chat"));
        assert!(!rendered.contains("Activity"));
        assert!(!rendered.contains("Run provenance"));
        assert!(rendered.contains("normalized Gateway"));
        assert!(!rendered.contains("Run completed"));
    }

    #[test]
    fn active_overlay_renders_over_main_body_without_hiding_prompt() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = Some(ActiveOverlay::Evidence);
        app.input = "Continue analysis".to_owned();
        app.input_cursor = app.input.len();

        let rendered = render_app_frame(&app, 120, 34);

        assert!(rendered.contains("EVIDENCE"));
        assert!(rendered.contains("filter"));
        assert!(rendered.contains("receipt_run_review_desktop_plan"));
        assert!(rendered.contains("Ctrl-R runs"));
        assert!(rendered.contains("Continue analysis"));
        assert!(rendered.contains("esc chat"));
    }

    #[test]
    fn transcript_rows_have_padding_and_do_not_touch_prompt_area() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = None;
        app.input = "Continue analysis".to_owned();
        app.input_cursor = app.input.len();

        let rows = render_app_frame_rows(&app, 120, 34);
        let content_row = rows
            .iter()
            .find(|row| row.contains("Reviewed the plan"))
            .expect("transcript content visible");
        let input_row = rows
            .iter()
            .position(|row| row.contains("Continue analysis"))
            .expect("input visible");

        assert!(
            content_row
                .find("Reviewed")
                .is_some_and(|column| column >= 2)
        );
        assert!(
            rows[input_row.saturating_sub(1)]
                .replace('│', "")
                .trim()
                .is_empty()
        );
    }

    #[test]
    fn active_run_renders_activity_inside_transcript_panel() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.state.run_status = Some("running".to_owned());
        app.state.working_phase = Some("thinking".to_owned());
        app.state
            .progress_messages
            .push("Inspecting repository structure".to_owned());
        app.input = "next question".to_owned();
        app.input_cursor = app.input.len();

        let rows = render_app_frame_rows(&app, 100, 24);
        let activity_row = rows
            .iter()
            .position(|row| row.contains("thinking") && row.contains("Inspecting repository"))
            .expect("activity row visible in main transcript panel");
        let input_row = rows
            .iter()
            .position(|row| row.contains("next question"))
            .expect("composer stays pinned below transcript");

        assert!(activity_row < input_row);
        assert!(
            rows.iter()
                .any(|row| row.contains("●") || row.contains("◐"))
        );
    }

    #[test]
    fn wrapped_activity_row_reserves_transcript_space() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.transcript.push(TranscriptEntry::new(
            TranscriptKind::Assistant,
            "Claude",
            "The last visible transcript line should stay above the active run marker.",
        ));
        app.state.run_status = Some("running".to_owned());
        app.state.working_phase = Some("thinking".to_owned());
        app.state.progress_messages.push(
            "Inspecting a very long path and collecting enough context that the activity message wraps on narrow terminal widths".to_owned(),
        );
        app.input = "follow up".to_owned();
        app.input_cursor = app.input.len();

        let rows = render_app_frame_rows(&app, 54, 14);
        let activity_row = rows
            .iter()
            .position(|row| row.contains("thinking"))
            .expect("wrapped activity remains visible");
        let input_row = rows
            .iter()
            .position(|row| row.contains("follow up"))
            .expect("composer remains visible");

        assert!(activity_row < input_row);
        assert!(
            rows[input_row.saturating_sub(1)]
                .replace('│', "")
                .trim()
                .is_empty()
        );
    }

    #[test]
    fn wrapped_transcript_rows_keep_continuation_gutter() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.transcript.push(TranscriptEntry::new(
            TranscriptKind::Command,
            "Bash",
            "Command: echo \"== crates ==\" && ls -1 crates 2>/dev/null; echo \"== git status ==\" && git status --short; echo \"== head ==\" && git log --oneline -1",
        ));

        let rows = render_app_frame_rows(&app, 72, 18);
        let continuation = rows
            .iter()
            .find(|row| row.contains("--oneline"))
            .expect("wrapped command continuation is visible");

        assert!(
            continuation
                .find("--oneline")
                .is_some_and(|column| column >= 3)
        );
    }

    #[test]
    fn wrapped_transcript_viewport_follows_visual_bottom() {
        let lines = vec![
            Line::from("alpha beta gamma delta epsilon zeta eta"),
            Line::from("theta"),
        ];

        let visible = visible_wrapped_transcript_lines(lines, 12, 2, 0)
            .into_iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>();
        let rendered = visible.join("\n");

        assert_eq!(visible.len(), 2);
        assert!(!rendered.contains("alpha"));
        assert!(rendered.contains("theta"));
    }

    #[test]
    fn approval_overlay_lines_preserve_decision_labels() {
        let lines = approval_overlay_lines(
            "Review required\nOrigin: claude-code\nQueue: 1 of 2 pending\nWarning: risky\nPreview\n  - old\n  + new\nActions: [Ctrl-A] approve  [Ctrl-X] deny  [Esc] defer",
        );
        let rendered = lines
            .iter()
            .flat_map(|line| line.spans.iter())
            .map(|span| span.content.as_ref())
            .collect::<String>();

        assert!(rendered.contains("Queue: 1 of 2 pending"));
        assert!(rendered.contains("  - old"));
        assert!(rendered.contains("  + new"));
        assert!(rendered.contains("[Ctrl-A] approve"));
        assert!(rendered.contains("[Ctrl-X] deny"));
        assert!(rendered.contains("[Esc] defer"));
        let removed = lines
            .iter()
            .find(|line| line.to_string().contains("- old"))
            .expect("removed diff line is rendered");
        let added = lines
            .iter()
            .find(|line| line.to_string().contains("+ new"))
            .expect("added diff line is rendered");
        assert_eq!(removed.spans[0].style.bg, Some(crate::theme::red_surface()));
        assert_eq!(removed.spans[1].style.bg, Some(crate::theme::red_surface()));
        assert_eq!(added.spans[0].style.bg, Some(crate::theme::sage_surface()));
        assert_eq!(added.spans[1].style.bg, Some(crate::theme::sage_surface()));
    }

    #[test]
    fn approval_overlay_title_surfaces_origin() {
        let title =
            approval_overlay_title("Review required\nOrigin: claude-code\nQueue: 1 of 1 pending");
        let rendered = title
            .spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect::<String>();

        assert!(rendered.contains("Approval"));
        assert!(rendered.contains("claude-code"));
        assert!(rendered.contains("Esc defer"));
    }

    #[test]
    fn fixture_backed_narrow_frame_prioritizes_transcript_over_activity_panel() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = None;
        let rendered = render_app_frame(&app, 72, 24);

        assert!(rendered.contains("Chat"));
        assert!(rendered.contains("normalized Gateway"));
        assert!(!rendered.contains("Activity"));
    }

    #[test]
    fn provider_fixtures_render_provider_neutral_tui_frames() {
        for (input, provider_id, model_fragment) in PROVIDER_FIXTURES {
            let app = app_from_fixture(input);
            let rendered = render_app_frame(&app, 144, 38);

            assert!(rendered.contains("Chat"));
            assert!(!rendered.contains("Activity"));
            assert!(!rendered.contains("Run provenance"));
            assert!(rendered.contains(*provider_id));
            assert!(rendered.contains(*model_fragment));
            assert!(!rendered.contains("Run completed"));
        }
    }

    #[test]
    fn visual_frame_regressions_cover_theme_variants() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.input = "Review the plan".to_owned();
        app.input_cursor = app.input.len();

        for mode in [ThemeMode::Dark, ThemeMode::Light, ThemeMode::Monochrome] {
            let rendered = render_app_frame_with_theme(&app, 100, 24, mode);

            assert!(rendered.contains("Chat"));
            assert!(rendered.contains("Review the plan"));
            assert!(!rendered.contains("▌Prompt"));
        }
    }

    #[test]
    fn visual_frame_regression_covers_slash_autocomplete() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.slash_catalog = crate::gateway_events::slash_hints_from_event(
            &serde_json::from_str(
                r#"{
                    "type": "slash.catalog",
                    "data": {
                        "commands": [
                            {
                                "name": "mode",
                                "usage": "/mode [ask|auto|acceptEdits|plan|dontAsk|bypassPermissions]",
                                "summary": "Inspect or set Claude Code mode.",
                                "category": "Run",
                                "choices": {"mode": ["ask", "auto", "acceptEdits", "plan"]},
                                "current_value": "ask"
                            },
                            {
                                "name": "clear",
                                "usage": "/clear",
                                "summary": "Clear the current transcript.",
                                "category": "Workflow",
                                "requires_confirmation": true,
                                "confirm_message": "This discards the current session transcript."
                            }
                        ]
                    }
                }"#,
            )
            .expect("catalog fixture parses"),
        );
        app.input = "/mode ".to_owned();
        app.input_cursor = app.input.len();

        let rows = render_app_frame_rows(&app, 104, 28);
        let rendered = rows.join("\n");

        assert!(rendered.contains("/ commands"));
        assert!(rendered.contains("/mode ask"));
        assert!(rendered.contains("current"));
        assert!(rendered.contains("read-only"));
        assert!(!rendered.contains("▸"));
        let palette_row = rows
            .iter()
            .position(|row| row.contains("/ commands"))
            .expect("palette visible");
        let typed_input_row = rows
            .iter()
            .rposition(|row| row.contains("/mode "))
            .expect("typed input visible");
        assert!(palette_row < typed_input_row);
        assert!(!rendered.contains("Enter sends"));
        assert!(!rendered.contains("Alt-Enter newline"));
    }

    #[test]
    fn visual_frame_regression_uses_catalog_order_for_slash_root() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.slash_catalog = crate::gateway_events::slash_hints_from_event(
            &serde_json::from_str(
                r#"{
                    "type": "slash.catalog",
                    "data": {
                        "commands": [
                            {"name": "help", "usage": "/help", "summary": "Show slash-command help."},
                            {"name": "setup", "usage": "/setup", "summary": "Show setup guidance."},
                            {"name": "auth", "usage": "/auth [login|logout|status]", "summary": "Manage auth.", "subcommands": ["login", "logout", "status"]},
                            {"name": "clear", "usage": "/clear", "summary": "Clear the transcript.", "requires_confirmation": true}
                        ]
                    }
                }"#,
            )
            .expect("catalog fixture parses"),
        );
        app.input = "/".to_owned();
        app.input_cursor = app.input.len();

        let rendered = render_app_frame(&app, 104, 28);

        assert!(rendered.contains("4 of 4"));
        assert!(
            rendered.find("/help").expect("help visible")
                < rendered.find("/setup").expect("setup visible")
        );
        assert!(
            rendered.find("/setup").expect("setup visible")
                < rendered
                    .find("/auth [login|logout|status]")
                    .expect("auth visible")
        );
        assert!(rendered.contains("/clear"));
        assert!(rendered.contains("⚠ confirms"));
        assert!(rendered.contains("▸"));
    }

    #[test]
    fn visual_frame_regression_preserves_evidence_overlay_rows() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = Some(ActiveOverlay::Evidence);
        app.input = "Continue analysis".to_owned();
        app.input_cursor = app.input.len();

        let rows = render_app_frame_rows(&app, 120, 80);
        let overlay_row = rows
            .iter()
            .position(|row| row.contains("▌EVIDENCE"))
            .expect("evidence overlay title is visible");
        let input_row = rows
            .iter()
            .position(|row| row.contains("Continue analysis"))
            .expect("input remains visible below overlay");

        assert!(input_row > overlay_row);
        assert!(rows.iter().any(|row| row.contains("filter")));
        assert!(rows.iter().any(|row| row.contains("items")));
        assert!(rows.iter().any(|row| row.contains("Ctrl-R runs")));
        assert!(
            rows.iter()
                .any(|row| row.contains("receipt_run_review_desktop_plan"))
        );
    }

    #[test]
    fn visual_frame_regression_preserves_memory_overlay_hierarchy() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = Some(ActiveOverlay::Memory);

        let rows = render_app_frame_rows(&app, 120, 34);

        assert!(rows.iter().any(|row| row.contains("▌MEMORY")));
        assert!(rows.iter().any(|row| row.contains("Provider")));
        assert!(rows.iter().any(|row| row.contains("Model")));
        assert!(rows.iter().any(|row| row.contains("Last prompt")));
        assert!(rows.iter().any(|row| row.contains("type to narrow")));
        assert!(rows.iter().any(|row| row.contains("Ctrl-E evidence")));
    }

    #[test]
    fn visual_frame_regression_preserves_runs_overlay_detail() {
        let mut app = app_from_fixture(CLAUDE_CODE_STREAM);
        app.active_overlay = Some(ActiveOverlay::Runs);

        let rows = render_app_frame_rows(&app, 128, 36);

        assert!(rows.iter().any(|row| row.contains("▌RUNS")));
        assert!(rows.iter().any(|row| row.contains("receipt(s)")));
        assert!(rows.iter().any(|row| row.contains("tool(s)")));
        assert!(rows.iter().any(|row| row.contains("Run:")));
        assert!(rows.iter().any(|row| row.contains("Status:")));
        assert!(rows.iter().any(|row| row.contains("Ctrl-L filter")));
    }

    #[test]
    fn overlay_detail_lines_style_headings_labels_and_lists() {
        let lines = overlay_detail_lines("Run\nStatus: completed\n\n- receipt_1");
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(rendered.contains("Run"));
        assert!(rendered.contains("Status: completed"));
        assert!(rendered.contains("- receipt_1"));
        assert_eq!(lines[0].spans[0].style.fg, Some(crate::theme::accent()));
        assert_eq!(lines[1].spans[0].style.fg, Some(crate::theme::mute()));
        assert_eq!(lines[1].spans[1].style.fg, Some(crate::theme::primary()));
    }

    #[test]
    fn visual_frame_regression_preserves_approval_modal_rows() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.record_event(
            &serde_json::from_str(
                r#"{
                    "type": "approval.requested",
                    "data": {
                        "approval_id": "approval_edit_1",
                        "message": "Edit src/lib.rs?",
                        "origin": "claude-code",
                        "tool": "Edit",
                        "target": "src/lib.rs",
                        "risk": "writes source files",
                        "preview": "- old\n+ new"
                    }
                }"#,
            )
            .expect("approval fixture parses"),
        );
        app.active_overlay = Some(ActiveOverlay::Approvals);
        app.input = "Review approval context".to_owned();
        app.input_cursor = app.input.len();
        assert!(
            app.overlay_text()
                .expect("approval overlay text")
                .contains("+ new")
        );

        let rows = render_app_frame_rows(&app, 120, 50);
        let modal_row = rows
            .iter()
            .position(|row| row.contains("Approval"))
            .expect("approval modal title is visible");
        let input_row = rows
            .iter()
            .position(|row| row.contains("Review approval context"))
            .expect("input remains visible below modal");

        assert!(input_row > modal_row);
        assert!(rows.iter().any(|row| row.contains("via Claude Code")));
        assert!(rows.iter().any(|row| row.contains("Source request")));
        assert!(rows.iter().any(|row| row.contains("Craik context")));
        assert!(rows.iter().any(|row| row.contains("Warning:")));
        assert!(rows.iter().any(|row| row.contains("[Ctrl-A] approve")));
        assert!(
            rows.iter()
                .any(|row| row.contains('+') && row.contains("new"))
        );
    }

    #[test]
    fn visual_frame_regression_covers_code_and_pending_approval() {
        let mut app = InteractiveApp::for_test_with_messages([]);
        app.transcript.push(TranscriptEntry::assistant(
            "Assistant",
            "```rust\nfn main() {\n    let value = 42;\n}\n```",
        ));
        app.record_event(
            &serde_json::from_str(
                r#"{
                    "type": "approval.requested",
                    "data": {
                        "approval_id": "approval_edit_1",
                        "message": "Edit src/lib.rs?",
                        "tool": "Edit",
                        "target": "src/lib.rs",
                        "reason": "apply requested change"
                    }
                }"#,
            )
            .expect("approval fixture parses"),
        );
        app.active_overlay = None;

        let rendered = render_app_frame(&app, 120, 34);

        assert!(rendered.contains("fn main"));
        assert!(rendered.contains("let value"));
        assert!(rendered.contains("Approval pending"));
        assert!(rendered.contains("approval_edit_1"));
    }

    #[test]
    fn slash_input_gets_extra_panel_height_for_suggestions() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        assert_eq!(input_panel_height(&app), 3);
        app.input = "/r".to_owned();
        assert_eq!(input_panel_height(&app), 3);
        app.search_active = true;
        assert_eq!(input_panel_height(&app), 4);
    }

    #[test]
    fn prompt_input_height_grows_with_multiline_content() {
        let mut app = InteractiveApp::for_test_with_messages([]);

        assert_eq!(input_panel_height(&app), 3);
        app.input = "one\ntwo\nthree\nfour".to_owned();

        assert_eq!(input_panel_height(&app), 6);
        assert_eq!(input_title(&app), "");
        assert!(!input_title(&app).contains("Enter sends"));
    }

    #[test]
    fn prompt_input_rows_are_vertically_centered_in_composer() {
        assert_eq!(centered_input_row_offset(3, 1), 1);
        assert_eq!(centered_input_row_offset(6, 4), 1);
        assert_eq!(centered_input_row_offset(3, 3), 0);

        let lines = vertically_center_input_lines(
            vec![Line::from("Message craik or type / for commands")],
            1,
        );

        assert!(lines[0].spans.is_empty());
        assert_eq!(lines[1].to_string(), "Message craik or type / for commands");
    }

    #[test]
    fn terminal_setup_does_not_capture_mouse_or_enter_alternate_screen() {
        let source = include_str!("main.rs");

        assert!(!source.contains(&["Enter", "AlternateScreen"].concat()));
        assert!(!source.contains(&["Enable", "MouseCapture"].concat()));
        assert!(!source.contains(&["Disable", "MouseCapture"].concat()));
    }

    #[test]
    fn native_transcript_flushes_to_terminal_scrollback() {
        let backend = TestBackend::new(48, 5);
        let mut terminal = Terminal::with_options(
            backend,
            TerminalOptions {
                viewport: Viewport::Inline(2),
            },
        )
        .expect("inline terminal is created");
        let mut state = super::NativeTranscriptState::default();
        let mut app = InteractiveApp::for_test_with_messages([]);
        for index in 0..5 {
            app.transcript.push(TranscriptEntry::assistant(
                "Assistant",
                &format!("scrollback line {index}"),
            ));
        }
        app.input = "next prompt".to_owned();
        app.input_cursor = app.input.len();

        flush_native_transcript(&mut terminal, &mut state, &app)
            .expect("native transcript flushes");
        terminal
            .draw(|frame| draw_native_live_frame(frame, &app))
            .expect("live viewport renders");
        let scrollback = buffer_rows(terminal.backend().scrollback()).join("\n");
        let viewport = buffer_rows(terminal.backend().buffer()).join("\n");

        assert_eq!(state.flushed_entries, app.transcript.len());
        assert!(scrollback.contains("scrollback line 0"));
        assert!(scrollback.contains("scrollback line 3"));
        assert!(viewport.contains("next prompt"));
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
        render_app_frame_rows(app, width, height).join("\n")
    }

    fn render_app_frame_rows(app: &InteractiveApp, width: u16, height: u16) -> Vec<String> {
        let backend = TestBackend::new(width, height);
        let mut terminal = Terminal::new(backend).expect("test terminal is created");
        terminal
            .draw(|frame| draw_interactive_frame(frame, app))
            .expect("interactive frame renders");
        buffer_rows(terminal.backend().buffer())
    }

    fn buffer_rows(buffer: &ratatui::buffer::Buffer) -> Vec<String> {
        let width = buffer.area.width as usize;
        buffer
            .content()
            .chunks(width)
            .map(|row| row.iter().map(|cell| cell.symbol()).collect::<String>())
            .collect()
    }

    fn render_app_frame_with_theme(
        app: &InteractiveApp,
        width: u16,
        height: u16,
        mode: ThemeMode,
    ) -> String {
        with_mode_for_test(mode, || render_app_frame(app, width, height))
    }
}
