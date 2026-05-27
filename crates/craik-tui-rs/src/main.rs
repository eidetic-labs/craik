use anyhow::Context;
use craik_tui_rs::{parse_gateway_events, render_replay_text, summarize_gateway_events};
use ratatui::{
    Terminal,
    backend::TestBackend,
    widgets::{Block, Borders, Paragraph},
};
use std::{env, fs, io};

fn main() -> anyhow::Result<()> {
    let input = match env::args().nth(1) {
        Some(path) => {
            fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?
        }
        None => io::read_to_string(io::stdin()).context("failed to read stdin")?,
    };
    let events = parse_gateway_events(&input)?;
    let summary = summarize_gateway_events(&events);
    let rendered = render_replay_text(&summary);

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
