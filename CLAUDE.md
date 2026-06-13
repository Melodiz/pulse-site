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
- **Update `docs/index.html`**: add the new entry, then **sort the entire digest
  list by date, newest first** — insertion order is irrelevant, re-sort the full
  `<ul class="digest-list">` on every render (ties: keep stable). Each entry:
  NEWS/TRENDS tag (+ FIXTURE badge if applicable), date, title (RU+EN), item count.

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

Run this exact block **after a successful push** (set `DIGEST` + `PAGE_URL` to the
digest you just rendered). It is self-contained and prints only a parsed result.

```bash
# --- Telegram notify — never prints the token, the URL, or the curl command ---
set -a; [ -f .env ] && . ./.env; set +a
DIGEST="News 2026-06-11"                                            # source + date of this run
PAGE_URL="https://melodiz.github.io/pulse-site/2026-06-11-news.html"
if [ -z "${BOT_TOKEN:-}" ] || [ -z "${CHAT_ID:-}" ]; then
  echo "notify: skipped (.env absent or BOT_TOKEN/CHAT_ID unset)"
else
  API_URL="https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"   # contains token — NEVER echo
  TEXT="AI-Tech Field Pulse — ${DIGEST} rendered: ${PAGE_URL}"
  RESP=$(curl --silent --show-error \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${TEXT}" \
    "$API_URL" 2>/tmp/notify.err); CURL_RC=$?
  if [ $CURL_RC -ne 0 ]; then
    echo "notify: curl failed (exit $CURL_RC)"                     # do NOT print stderr — it may contain the URL
  elif [ "$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("ok"))')" = "True" ]; then
    MID=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["message_id"])')
    echo "notify: ok:true (message_id ${MID})"
  else
    DESC=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("description",""))')
    echo "notify: ok:false — ${DESC}"                              # Telegram's description never contains the token
  fi
  rm -f /tmp/notify.err
fi
```

- **The notify URL embeds the token** (`…/bot<TOKEN>/sendMessage`). NEVER print the
  curl command or the URL — build it in a variable (`API_URL`), pass it positionally,
  and report only the parsed result (`ok:true` + `message_id`, or `ok:false` + the
  Telegram `description`). Telegram echoes the token in no response field; curl's
  stderr can, so it is captured to a file and discarded, never printed.
- **NEVER `cat .env` / `echo $BOT_TOKEN` / `echo $CHAT_ID`.** Reference `.env` by path.
- If `.env` is absent or either var is empty: skip with the printed note above.

## Report format (every run ends with this)

- Files written
- Parse warnings / synthesis notes (incl. any new type → color mappings)
- Push result
- Live URL
- Notify: ok:true + message_id / ok:false + description / skipped (no .env) —
  never the token, the URL, or the curl command

## Bot reminders (cron-only)

`bot/` holds the render-reminder mechanism. **v1 runs no daemon** — reminders are
cron + `curl` to Telegram `sendMessage`, nothing listening, no inbound ports.

- `bot/remind.sh` — POSIX sh; `remind.sh [env_file] <text>` sends one reminder and
  prints only the parsed result. Same token hygiene as the notify block: the URL
  embeds the token, so it's built in a variable and never echoed; curl stderr is
  discarded (it can leak the URL).
- `bot/crontab.pulse` — the delimited crontab block (MSK server-local time):
  Mon = News, Tue/Fri = DL Pulse, first Mon/month = Trends.
- `bot/env.example` — placeholders only. The **real env is hand-placed by Ivan** at
  `~/bots/pulse_bot/env` on the VPS (mode 600) and at repo-root `.env` locally;
  neither is committed (both gitignored). Nothing under `bot/` ever carries a real token.
- Deploy = `./bot/deploy.sh` (ships `remind.sh` + `crontab.pulse` to `yandex-vps`,
  scoped to `~/bots/pulse_bot/`, installs the crontab block idempotently). Gated on
  Ivan placing the token first.

## Repo map

    docs/            Pages root: index.html, <date>-<source>.html pages, assets/
    inbox/           digest MD drop (input)
    bot/             reminder mechanism: remind.sh, crontab.pulse, env.example, deploy.sh
    bot/env          VPS-only, gitignored, hand-placed (mode 600): BOT_TOKEN, CHAT_ID
    .env             local only, gitignored: BOT_TOKEN, CHAT_ID
