mod commands;
mod discord;
mod vm;
mod wiki;

use anyhow::{Context, Result, bail, ensure};
use serenity::all::{ClientBuilder, CreateAllowedMentions, GatewayIntents, HttpBuilder};
use std::{collections::HashSet, env, path::PathBuf, process::ExitCode, sync::Arc, time::Duration};
use tokio::sync::Notify;

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(code),
        Err(error) => {
            eprintln!("{error:#}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<u8> {
    let runtime = vm::Runtime::from_env();
    let mut args = env::args_os().skip(1);
    if let Some(arg) = args.next() {
        if arg == "--eval" {
            let mode = args
                .next()
                .and_then(|m| commands::mode(m.to_str()?))
                .context("expected sqf, sqc, sqf2sqc, assembly, or preprocess after --eval")?;
            let path = args.next().map(PathBuf::from);
            ensure!(
                args.next().is_none(),
                "unexpected argument after the library path"
            );
            return vm::run_worker(path.as_deref().unwrap_or(runtime.library()), mode);
        }
        bail!("usage: sqf-discord [--eval MODE [LIBRARY]]");
    }
    run_bot(runtime)
}

fn admins(value: &str) -> Result<HashSet<u64>> {
    value
        .split(',')
        .map(str::trim)
        .filter(|id| !id.is_empty())
        .map(|id| {
            id.parse()
                .context("DISCORD_ADMINS must contain comma-separated numeric user IDs")
        })
        .collect()
}

#[tokio::main]
async fn run_bot(runtime: vm::Runtime) -> Result<u8> {
    let token = env::var("DISCORD_TOKEN").context("set DISCORD_TOKEN to the Discord bot token")?;
    ensure!(!token.trim().is_empty(), "DISCORD_TOKEN is empty");
    let admins =
        admins(&env::var("DISCORD_ADMINS").unwrap_or_else(|_| "105784568346324992".into()))?;
    let name = env::var("DISCORD_BOT_NAME").unwrap_or_else(|_| "SQF".into());
    let restart = Arc::new(Notify::new());
    let wiki = Arc::new(wiki::Wiki::new()?);
    let bot = discord::Bot {
        runtime,
        wiki: wiki.clone(),
        admins,
        name,
        restart: restart.clone(),
    };
    let intents = GatewayIntents::GUILDS
        | GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::DIRECT_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT;
    let http = HttpBuilder::new(token.trim())
        .default_allowed_mentions(CreateAllowedMentions::new())
        .build();
    let mut client = ClientBuilder::new_with_http(http, intents)
        .event_handler(bot)
        .await?;
    let refresh = tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(3600));
        loop {
            interval.tick().await;
            if let Err(error) = wiki.refresh().await {
                eprintln!("Biki index refresh failed: {error:#}");
            }
        }
    });
    let shards = client.shard_manager.clone();
    let code = tokio::select! {
        result = client.start() => { result?; return Ok(0); },
        signal = tokio::signal::ctrl_c() => { signal?; 0 },
        () = restart.notified() => 75,
    };
    refresh.abort();
    shards.shutdown_all().await;
    Ok(code)
}
