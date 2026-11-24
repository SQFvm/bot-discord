use sqfvm::Mode;

pub fn mode(name: &str) -> Option<Mode> {
    Some(match name {
        "sqf" => Mode::Sqf,
        "sqc" => Mode::Sqc,
        "sqf2sqc" => Mode::SqfToSqc,
        "assembly" => Mode::Assembly,
        "preprocess" => Mode::Preprocess,
        _ => return None,
    })
}

pub fn mode_name(mode: Mode) -> &'static str {
    match mode {
        Mode::Sqf => "sqf",
        Mode::Sqc => "sqc",
        Mode::SqfToSqc => "sqf2sqc",
        Mode::Assembly => "assembly",
        Mode::Preprocess => "preprocess",
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WikiView {
    Brief,
    Full,
    Sqc,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Command<'a> {
    Eval(Mode, String),
    Wiki(WikiView, &'a str),
    Help(&'a str),
    Rebuild,
    Restart,
}

fn fence(input: &str) -> Option<(Mode, &str)> {
    let inner = input.trim().strip_prefix("```")?.strip_suffix("```")?;
    let (label, code) = inner.split_once(char::is_whitespace).unwrap_or((inner, ""));
    Some((mode(label)?, code.trim()))
}

pub fn has_fence(input: &str) -> bool {
    fence(input).is_some()
}

fn source(input: &str, id: u64) -> (Option<Mode>, String) {
    let clean = input
        .replace(&format!("<@{id}>"), "")
        .replace(&format!("<@!{id}>"), "");
    match fence(&clean) {
        Some((mode, body)) => (Some(mode), body.to_owned()),
        None => (None, clean.trim().to_owned()),
    }
}

pub fn route(input: &str, id: u64, dm: bool, sqf_channel: bool) -> Option<Command<'_>> {
    let input = input.trim();
    if let Some(command) = input.strip_prefix('!') {
        let (name, args) = command
            .split_once(char::is_whitespace)
            .unwrap_or((command, ""));
        let args = args.trim();
        if let Some(mode) = mode(name) {
            let (_, code) = source(args, id);
            return Some(Command::Eval(mode, code));
        }
        match name {
            "biki" => return Some(Command::Wiki(WikiView::Brief, args)),
            "biki_full" => return Some(Command::Wiki(WikiView::Full, args)),
            "biki_sqc" => return Some(Command::Wiki(WikiView::Sqc, args)),
            "help" => return Some(Command::Help(args)),
            "rebuild" => return Some(Command::Rebuild),
            "restart" => return Some(Command::Restart),
            _ => {}
        }
    }
    let mentioned = input.contains(&format!("<@{id}>")) || input.contains(&format!("<@!{id}>"));
    if dm || mentioned || sqf_channel {
        let (mode, code) = source(input, id);
        if !code.is_empty() && (dm || mentioned || mode.is_some()) {
            return Some(Command::Eval(mode.unwrap_or(Mode::Sqf), code));
        }
    }
    None
}

pub const HELP: &str = "Use !sqf, !sqc, !sqf2sqc, !assembly, or !preprocess followed by code. You can also DM me, mention me, or send a tagged code block in a channel starting with sqf or sqc.\n\nUse !biki <command> for a description, !biki_full for syntax and examples, or !biki_sqc for examples translated to SQC.\n\nAdmins can use !rebuild to update SQF-VM and !restart to restart the bot.";

pub fn help(command: &str) -> &'static str {
    match command.trim_start_matches('!') {
        "" => HELP,
        "sqf" => "!sqf <code> evaluates SQF.",
        "sqc" => "!sqc <code> evaluates SQC.",
        "sqf2sqc" => "!sqf2sqc <code> translates SQF to SQC.",
        "assembly" => "!assembly <code> executes SQF-VM assembly.",
        "preprocess" => "!preprocess <code> returns preprocessed source.",
        "biki" => "!biki <command> shows the Biki description.",
        "biki_full" => "!biki_full <command> shows syntax and examples.",
        "biki_sqc" => "!biki_sqc <command> shows syntax and SQC examples.",
        "rebuild" => "!rebuild updates and rebuilds SQF-VM (admins only).",
        "restart" => "!restart restarts the bot (admins only).",
        _ => "Unknown command. Use !help to list commands.",
    }
}

// Discord counts UTF-16 code units. Avoid splitting a character or code fence.
pub fn clipped(text: &str, limit: usize) -> String {
    if text.encode_utf16().count() <= limit {
        return text.to_owned();
    }
    let mut left = limit.saturating_sub(1);
    let mut out: String = text
        .chars()
        .take_while(|ch| {
            if ch.len_utf16() > left {
                return false;
            }
            left -= ch.len_utf16();
            true
        })
        .collect();
    if limit > 0 {
        out.push('…');
    }
    out
}

pub fn code_block(text: &str, language: &str, limit: usize) -> String {
    if text.is_empty() {
        return "```\n```".into();
    }
    let prefix = format!("```{language}\n");
    let body = text.replace("``", "`\u{200b}`");
    format!("{prefix}{}\n```", clipped(&body, limit - prefix.len() - 4))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dispatch() {
        for (text, dm, channel, expected) in [
            ("!sqf2sqc\t1", false, false, Some((Mode::SqfToSqc, "1"))),
            ("<@!42> 2", false, false, Some((Mode::Sqf, "2"))),
            ("3 <@42>", false, false, Some((Mode::Sqf, "3"))),
            ("<@42> ```sqc\n3;```", false, false, Some((Mode::Sqc, "3;"))),
            ("4", true, false, Some((Mode::Sqf, "4"))),
            (
                "```preprocess\r\n5\r\n```",
                false,
                true,
                Some((Mode::Preprocess, "5")),
            ),
            ("!sqc ```sqf\n6```", true, true, Some((Mode::Sqc, "6"))),
            ("<@142> 7", false, false, None),
            ("```sqf\n8```", false, false, None),
            ("hello", false, true, None),
            ("<@42>", false, false, None),
        ] {
            assert_eq!(
                route(text, 42, dm, channel),
                expected.map(|(m, s)| Command::Eval(m, s.into())),
                "{text}"
            );
        }
        assert_eq!(
            route("!biki_full a && b", 42, true, true),
            Some(Command::Wiki(WikiView::Full, "a && b"))
        );
    }
    #[test]
    fn discord_limits() {
        let block = code_block(&("```".to_owned() + &"😀".repeat(1500)), "sqf", 2000);
        assert!(block.encode_utf16().count() <= 2000);
        assert_eq!(block.matches("```").count(), 2);
        assert!(block.ends_with("…\n```"));
    }
}
