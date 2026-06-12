# pulse-site — render pipeline

Static reading layer for AI digests on GitHub Pages. Hand-written HTML/CSS/vanilla JS
in `docs/` (the published root). Digests arrive as markdown in `inbox/`; a Claude Code
session renders each one into a digest page. The word **"render"** alone is a complete
instruction: perform a render run as specified below.

Live site: https://melodiz.github.io/pulse-site/

## A render run

1. Find unrendered digests (see Input contract). Zero → report "nothing to render", stop.
2. For each: parse it (Parse rules), build the page (Rendering), update the index.
3. Verify locally (Verification), commit + push (Deploy), notify (Telegram).
4. End with the run report (Report format). Never skip the report.

## Input contract

- Digests are MD files in `inbox/` with **free-form filenames** — identify each file's
  date and source from its *content* (title and log block), never from the filename.
- **Stateless detection**: an inbox MD is unrendered iff no `docs/<date>-<source>*.html`
  exists matching its date+source. (The `*` covers historical `-fixture` suffixes:
  `2026-06-08-news-fixture.html` is the rendered page of the news fixture MD;
  `2026-06-11-news.html` is the rendered page of the May 14–June 11 source-material MD.)
- **Source A — News** (weekly). Body sections: "Model signals" (optional),
  "Industry news", "Modality state" (optional), "Log block". Free-form extra sections
  (TL;DR, caveats, below-threshold items) may also appear.
- **Source B — Trends** (monthly). Per-trend update sections, a "replacement state
  lines" block, "Log block".
- **THE LOG BLOCK IS THE CANONICAL ITEM ENUMERATION.** One line = one card, in order:

      RUN <id> | <DATE> | <link> | <short item> | <type> | <feedback>

  Body sections supply each card's full text — match them to log lines by content.
  Non-card material (TL;DR, replacement state lines, caveats…) renders as non-graded
  collapsible sections, not cards.

## Parse rules (hard-won — keep all)

- Tolerate small format drift (heading wording, section order, extra prose).
  On real ambiguity or parse failure — a body section you can't match to a log line,
  a log line you can't read — **STOP and ask the owner. Never guess silently.**
- **Missing log block**: stop and ask. If synthesis is approved: one line per body
  item, in body order; append the block to the inbox MD marked as
  `<!-- log block synthesized at render time -->` so source and page stay in sync.
- **Type vocabulary is open-ended** (seen so far: release, controversy, paper, result,
  deal, policy, plan, trend). A new type needs a `tag-<type>` class: add one color line
  to the kicker palette in `docs/assets/style.css`, pick a sensible existing color
  variable, and note the mapping in the run report. This is the only permitted asset
  change — bump `?v=` on the pages when you make it.
- **Multiple links** in one body section: the first *complete* link is canonical.
  A truncated link (contains `…` or `...`) is not complete — take the next one.
  Bare domains get `https://` prefixed, nothing else rewritten.
- **No per-line dates** in the source: use the digest period's **end date** everywhere
  (filename, log lines, index entry).
- **`data-log` attributes hold the source log line HTML-escaped** (`&` → `&amp;`,
  `<` → `&lt;`, `"` → `&quot;`). The browser unescapes on read, so the exported
  ungraded line is byte-identical to the source MD line — verify this (see
  Verification). Prefer avoiding `"` inside short items when synthesizing.

## Rendering

- Content is EN as given. Produce the **full RU translation yourself** — natural,
  not word-for-word; established English terms (tool routing, open-weights,
  post-training…) stay in English. **RU is the default view**; both languages are in
  the page as `lang="ru"`/`lang="en"` tagged elements.
- **Clone the structure of `docs/2026-06-11-news.html`** — it is the reference
  anatomy: masthead (source line, RU/EN toggle, h1, date), optional intro block,
  cards (`details`/`summary`, title + `tag tag-<type>` kicker, body paragraphs,
  compact source link, grade buttons + note input in `.card-actions`), extra
  sections, feedback panel, `<meta name="robots" content="noindex">`.
- **Do NOT restyle.** `docs/assets/style.css` and `docs/assets/app.js` are shared and
  the design is locked. Style changes are spec-level decisions — they go back to the
  orchestrator project, not into a render run. Bump `?v=` only if an asset actually
  changed (it shouldn't, except the new-type color rule above).
- File naming: `docs/<date>-<source>.html`, `<source>` ∈ {`news`, `trends`}.
- **Update `docs/index.html`**: new entry on top of the list — NEWS/TRENDS tag,
  date, title (RU+EN), item count.

## Verification (before pushing)

- Serve locally (`python3 -m http.server --directory docs`) and curl the new page → 200.
- Card count == log-block line count; both languages present; noindex present.
- Round-trip one escaped `data-log` (node: parse the attribute, compare to the source
  line — must be byte-identical).
- No fixed widths > 380px introduced (you didn't touch CSS, so this only fails if you did).

## Deploy

- Commit with a message naming the digest (e.g. `Render trends 2026-07-08`).
- Push over **SSH** (`origin` = `git@github.com:Melodiz/pulse-site.git`).
  **Do not assume `gh` exists** — it usually doesn't.
- Live URL: `https://melodiz.github.io/pulse-site/<file>.html`. Poll until it serves
  (Pages deploys take ~30–90 s; first probe often 404s or serves stale content).

## Telegram notify

- If `.env` exists at repo root (it defines `BOT_TOKEN` and `CHAT_ID`): source it and
  curl `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage` with `chat_id` and a
  short message containing the new page URL. Report only the HTTP status.
- **NEVER print, echo, or log the token** — no `cat .env`, no `echo $BOT_TOKEN`, no
  pasting the resolved URL into output. Reference `.env` by path only.
- If `.env` is absent: skip, and say so in the report (bot wiring is a later stage).

## Report format (every run ends with this)

- Files written
- Parse warnings / synthesis notes (incl. any new type → color mappings)
- Push result
- Live URL
- Notify: sent (HTTP status) / skipped (no .env)

## Repo map

    docs/            Pages root: index.html, <date>-<source>.html pages, assets/
    inbox/           digest MD drop (input)
    bot/             reserved for the Telegram bot (later stage)
    .env             local only, gitignored: BOT_TOKEN, CHAT_ID (may not exist yet)
