use crate::{
    commands::{self, Command, WikiView, clipped, code_block},
    vm::Runtime,
    wiki::{Page, Wiki},
};
use anyhow::{Context as _, Result};
use serenity::{all::*, async_trait};
use sqfvm::Mode;
use std::{collections::HashSet, sync::Arc};
use tokio::sync::Notify;

pub struct Bot {
    pub runtime: Runtime,
    pub wiki: Arc<Wiki>,
    pub admins: HashSet<u64>,
    pub name: String,
    pub restart: Arc<Notify>,
}

#[async_trait]
impl EventHandler for Bot {
    async fn ready(&self, ctx: Context, mut ready: Ready) {
        eprintln!("Connected as {} ({})", ready.user.name, ready.user.id);
        if self.name.is_empty() || ready.user.name == self.name {
            return;
        }
        if let Err(error) = ready
            .user
            .edit(&ctx, EditProfile::new().username(&self.name))
            .await
        {
            eprintln!("Could not update bot name: {error}");
        }
    }

    async fn message(&self, ctx: Context, msg: Message) {
        if msg.author.bot {
            return;
        }
        if let Err(error) = self.handle(&ctx, &msg).await {
            eprintln!("Message {}: {error:#}", msg.id);
            if let Err(send_error) = msg
                .channel_id
                .say(&ctx, clipped(&format!("Error: {error}"), 2000))
                .await
            {
                eprintln!("Could not reply to message {}: {send_error}", msg.id);
            }
        }
    }
}

impl Bot {
    async fn handle(&self, ctx: &Context, msg: &Message) -> Result<()> {
        let dm = msg.guild_id.is_none();
        let id = ctx.cache.current_user().id.get();
        let sqf_channel = if !dm && commands::has_fence(&msg.content) {
            let name = msg.channel_id.name(ctx).await?;
            name.starts_with("sqf") || name.starts_with("sqc")
        } else {
            false
        };
        let Some(command) = commands::route(&msg.content, id, dm, sqf_channel) else {
            return Ok(());
        };
        match command {
            Command::Eval(mode, source) => {
                let _typing = msg.channel_id.start_typing(&ctx.http);
                let output = self.runtime.eval(mode, &source).await?;
                let lang = if mode == Mode::SqfToSqc { "sqc" } else { "sqf" };
                msg.channel_id
                    .say(ctx, code_block(&output, lang, 2000))
                    .await?;
            }
            Command::Wiki(view, name) => {
                if name.is_empty() {
                    msg.channel_id
                        .say(ctx, "Include a command name, for example `!biki hint`.")
                        .await?;
                } else {
                    let _typing = msg.channel_id.start_typing(&ctx.http);
                    let name = name.trim_matches('"');
                    match self
                        .wiki
                        .page(name)
                        .await
                        .context("could not fetch the Biki command")?
                    {
                        None => {
                            msg.channel_id.say(ctx, "Unknown command!").await?;
                        }
                        Some(page) => self.send_page(ctx, msg.channel_id, page, view).await?,
                    }
                }
            }
            Command::Help(name) => {
                let help = commands::help(name);
                if dm
                    || msg
                        .author
                        .direct_message(ctx, CreateMessage::new().content(help))
                        .await
                        .is_err()
                {
                    msg.channel_id.say(ctx, help).await?;
                }
            }
            Command::Rebuild if self.admins.contains(&msg.author.id.get()) => {
                let mut progress = msg
                    .channel_id
                    .say(ctx, "Updating and rebuilding SQF-VM…")
                    .await?;
                let message = match self.runtime.rebuild().await {
                    Ok(()) => "SQF-VM has been rebuilt!".to_owned(),
                    Err(error) => {
                        eprintln!("SQF-VM rebuild failed: {error:#}");
                        format!("SQF-VM rebuild failed: {error}")
                    }
                };
                progress
                    .edit(ctx, EditMessage::new().content(clipped(&message, 2000)))
                    .await?;
            }
            Command::Restart if self.admins.contains(&msg.author.id.get()) => {
                msg.channel_id.say(ctx, "Restarting discord bots…").await?;
                self.restart.notify_one();
            }
            Command::Rebuild | Command::Restart => {}
        }
        Ok(())
    }

    async fn send_page(
        &self,
        ctx: &Context,
        channel: ChannelId,
        page: Page,
        view: WikiView,
    ) -> Result<()> {
        let title = clipped(&page.title, 256);
        let description = clipped(&page.description, 4096);
        let header = CreateEmbed::new().title(&title).url(page.url().as_str());
        let mut embed = header.clone().description(&description);
        if view != WikiView::Brief {
            let mut fields = Vec::new();
            for (i, syntax) in page.syntax.iter().enumerate() {
                fields.push((format!("Syntax {}", i + 1), clipped(syntax, 1024)));
            }
            for (i, example) in page.examples.iter().enumerate() {
                let code = if view == WikiView::Sqc {
                    code_block(
                        &self.runtime.eval(Mode::SqfToSqc, example).await?,
                        "sqc",
                        1024,
                    )
                } else {
                    code_block(example, "sqf", 1024)
                };
                fields.push((format!("Example {}", i + 1), code));
            }
            // Each Discord message has a shared 6,000-unit embed text budget.
            let footer = clipped(&page.footer, 1200);
            let overhead = title.encode_utf16().count() + footer.encode_utf16().count();
            let mut used = overhead + description.encode_utf16().count();
            let mut count = 0;
            for (name, value) in fields {
                let size = name.encode_utf16().count() + value.encode_utf16().count();
                if count == 25 || used + size > 6000 {
                    channel
                        .send_message(ctx, CreateMessage::new().embed(embed))
                        .await?;
                    embed = header.clone();
                    used = overhead;
                    count = 0;
                }
                embed = embed.field(name, value, false);
                used += size;
                count += 1;
            }
            embed = embed.footer(CreateEmbedFooter::new(footer));
        }
        channel
            .send_message(ctx, CreateMessage::new().embed(embed))
            .await?;
        Ok(())
    }
}
