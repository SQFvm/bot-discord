use anyhow::{Context, Result, anyhow};
use reqwest::{Client, Url};
use scraper::{ElementRef, Html, Node, Selector};
use serde::Deserialize;
use std::{collections::HashSet, time::Duration};
use tokio::sync::RwLock;

const API: &str = "https://community.bistudio.com/wikidata/api.php";

pub struct Wiki {
    http: Client,
    commands: RwLock<Option<HashSet<String>>>,
}

#[derive(Deserialize)]
struct ApiError {
    code: String,
    info: String,
}

#[derive(Deserialize)]
struct CategoryResponse {
    query: Option<Members>,
    #[serde(rename = "continue")]
    next: Option<Continuation>,
    error: Option<ApiError>,
}
#[derive(Deserialize)]
struct Members {
    categorymembers: Vec<Member>,
}
#[derive(Deserialize)]
struct Member {
    title: String,
}
#[derive(Deserialize)]
struct Continuation {
    cmcontinue: String,
    #[serde(rename = "continue")]
    token: String,
}

#[derive(Deserialize)]
struct PageResponse {
    parse: Option<Parsed>,
    error: Option<ApiError>,
}
#[derive(Deserialize)]
struct Parsed {
    title: String,
    text: String,
}

impl Wiki {
    pub fn new() -> Result<Self> {
        let http = Client::builder()
            .timeout(Duration::from_secs(10))
            .user_agent("SQF-VM Discord bot (https://github.com/SQFvm/bot-discord)")
            .build()?;
        Ok(Self {
            http,
            commands: RwLock::new(None),
        })
    }

    pub async fn refresh(&self) -> Result<()> {
        let mut names = HashSet::new();
        let mut next: Option<Continuation> = None;
        loop {
            let mut request = self.http.get(API).query(&[
                ("action", "query"),
                ("format", "json"),
                ("formatversion", "2"),
                ("list", "categorymembers"),
                ("cmtitle", "Category:Arma 3: Scripting Commands"),
                ("cmlimit", "500"),
                ("cmtype", "page"),
            ]);
            if let Some(cursor) = next {
                request = request.query(&[
                    ("cmcontinue", cursor.cmcontinue),
                    ("continue", cursor.token),
                ]);
            }
            let response: CategoryResponse =
                request.send().await?.error_for_status()?.json().await?;
            if let Some(err) = response.error {
                return Err(anyhow!(err.info));
            }
            names.extend(
                response
                    .query
                    .context("missing category members")?
                    .categorymembers
                    .into_iter()
                    .map(|m| m.title),
            );
            next = response.next;
            if next.is_none() {
                break;
            }
        }
        *self.commands.write().await = Some(names);
        Ok(())
    }

    pub async fn page(&self, title: &str) -> Result<Option<Page>> {
        if self
            .commands
            .read()
            .await
            .as_ref()
            .is_some_and(|names| !names.contains(title))
        {
            return Ok(None);
        }
        let response: PageResponse = self
            .http
            .get(API)
            .query(&[
                ("format", "json"),
                ("action", "parse"),
                ("page", title),
                ("prop", "text"),
                ("formatversion", "2"),
            ])
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        if let Some(err) = response.error {
            if matches!(err.code.as_str(), "missingtitle" | "invalidtitle") {
                return Ok(None);
            }
            return Err(anyhow!(err.info));
        }
        let page = response.parse.context("missing Biki page")?;
        Ok(Page::from_html(page.title, &page.text))
    }
}

#[derive(Debug)]
pub struct Page {
    pub title: String,
    pub description: String,
    pub syntax: Vec<String>,
    pub examples: Vec<String>,
    pub footer: String,
}

fn selector(css: &str) -> Selector {
    Selector::parse(css).expect("valid static Biki CSS selector")
}

fn text(element: ElementRef<'_>) -> String {
    let mut value = String::new();
    for node in element.descendants() {
        match node.value() {
            Node::Text(t) => value.push_str(t),
            Node::Element(e) if e.name() == "br" => value.push('\n'),
            _ => {}
        }
    }
    value.trim().to_owned()
}

impl Page {
    fn from_html(title: String, html: &str) -> Option<Self> {
        let document = Html::parse_fragment(html);
        let command = document.select(&selector("._description.cmd")).next()?;
        let description = text(
            command
                .select(&selector("dl > dt:first-child + dd"))
                .next()?,
        );
        let mut syntax = Vec::new();
        for block in command.select(&selector("dl.syntax")) {
            let mut lines = Vec::new();
            for part in block.child_elements() {
                match part.value().name() {
                    "dt" => lines.push(format!("**{}**", text(part))),
                    "dd" => lines.push(text(part)),
                    _ => {}
                }
            }
            syntax.push(lines.join("\n"));
        }
        let examples = command
            .select(&selector("dt[id^='Example_'] + dd"))
            .map(|dd| {
                let code: Vec<_> = dd
                    .select(&selector(".sqfhighlighter-scroller, pre"))
                    .map(text)
                    .collect();
                if code.is_empty() {
                    text(dd)
                } else {
                    code.join("\n")
                }
            })
            .collect();
        let links = |css| {
            command
                .select(&selector(css))
                .map(text)
                .collect::<Vec<_>>()
                .join(", ")
        };
        let footer = format!(
            "See also: {}\nGroups: {}",
            links(".seealso a"),
            links(".groups a")
        );
        Some(Self {
            title,
            description,
            syntax,
            examples,
            footer,
        })
    }

    pub fn url(&self) -> Url {
        let mut url = Url::parse("https://community.bistudio.com/wiki").unwrap();
        url.path_segments_mut()
            .unwrap()
            .push(&self.title.replace(' ', "_"));
        url
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    #[ignore = "contacts the Bohemia Interactive Community Wiki"]
    async fn live_page() {
        let wiki = Wiki::new().unwrap();
        wiki.refresh().await.unwrap();
        let page = wiki.page("hint").await.unwrap().unwrap();
        assert!(!page.description.is_empty());
        assert!(!page.syntax.is_empty());
        assert!(page.examples.iter().any(|code| code.contains("hint")));
    }
    #[test]
    fn rendered_command_with_alternate_syntax() {
        let page = Page::from_html("a && b".into(), r#"<div class="_description cmd">
            <dl><dt>Description:</dt><dd>First<br>second.</dd><dt>Groups:</dt>
            <dd class="groups"><a>Logic</a><a>Other</a></dd></dl>
            <dl class="syntax"><dt>Syntax:</dt><dd><a>a</a> &amp;&amp; b</dd></dl>
            <dl class="syntax"><dt>Parameters:</dt><dd>one</dd><dd>two</dd></dl>
            <dl><dt id="Example_1"></dt><dd>Example:<div class="sqfhighlighter-scroller">true &amp;&amp; <a>false</a></div></dd></dl>
            <dd class="seealso"><a>and</a></dd></div>"#).unwrap();
        assert_eq!(page.description, "First\nsecond.");
        assert_eq!(page.examples, ["true && false"]);
        assert_eq!(page.syntax.len(), 2);
        assert!(page.syntax[1].contains("one\ntwo"));
        assert!(page.footer.contains("Logic, Other"));
        assert_eq!(
            page.url().as_str(),
            "https://community.bistudio.com/wiki/a_&&_b"
        );
    }
}
