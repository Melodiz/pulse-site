#!/usr/bin/env python3
"""pulse_bot — interactive Telegram daemon for the AI-Tech Field Pulse digest feed (v2).

Long-polling daemon (no inbound ports; port 22 only). Replaces the v1 cron+curl
setup (remind.sh / fetch.sh / crontab.pulse are RETIRED — see CLAUDE.md).

Reads BOT_TOKEN and CHAT_ID (the owner / OWNER_CHAT_ID) from the environment, which
systemd populates from EnvironmentFile=~/bots/pulse_bot/env (mode 600). The token is
NEVER logged: httpx is pinned to WARNING so its INFO request logs (which embed the
token in the URL) are suppressed.

Features
  /start, /help          — explain the feed, how to subscribe/unsubscribe.
  /subscribe /unsubscribe — open to anyone; manage chat_id in the subscriber store.
  Broadcast              — send a text+URL to all subscribers, pruning chat_ids that
                           return 403 (blocked the bot), never aborting the batch.
  Reminders (MSK)        — Mon 09:00 "News run", Tue+Fri 09:00 "DL Pulse run",
                           first Monday 09:05 "Trends run"; broadcast to subscribers.
  Digest broadcast       — watch data/broadcast_queue.json ({source,date,url,title});
                           CC drops it via ssh/rsync, the bot broadcasts then clears it
                           (no inbound port needed).
  Feedback courier       — OWNER replies (to anything) are appended to
                           data/feedback_inbox.jsonl ({ts,text}); non-owner replies are
                           ignored silently. CC pulls + cleans this file.
  File ingest            — OWNER-sent .md documents are saved to data/incoming/ for
                           CC's "process new files" (replaces fetch.sh's getUpdates poll).

State lives under data/ (the only writable subtree under the hardened unit):
  data/subscribers.json        list of {chat_id, first_seen}
  data/feedback_inbox.jsonl    one {ts,text} per owner reply
  data/broadcast_queue.json    CC-written trigger (+ .processing while claimed)
  data/incoming/<name>.md      owner-sent digest documents

Verified against python-telegram-bot v22.8 (Python 3.10+).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from telegram import LinkPreviewOptions, Update
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

# --------------------------------------------------------------------------- config
MSK = ZoneInfo("Europe/Moscow")

BOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PULSE_DATA_DIR", BOT_DIR / "data"))
SUBS_FILE = DATA_DIR / "subscribers.json"
FEEDBACK_FILE = DATA_DIR / "feedback_inbox.jsonl"
QUEUE_FILE = DATA_DIR / "broadcast_queue.json"
QUEUE_CLAIM = QUEUE_FILE.with_name(QUEUE_FILE.name + ".processing")
INCOMING_DIR = DATA_DIR / "incoming"

BROADCAST_POLL_SECONDS = 15

# PTB run_daily day-of-week convention (CHANGED in v20.0): 0=Sunday .. 6=Saturday.
# NOTE: this is the OPPOSITE of Python's datetime.weekday() (Monday=0). Every job
# callback below ALSO re-checks the weekday with stdlib weekday() as a hard guard,
# so a convention slip cannot fire a reminder on the wrong day.
PTB_MON, PTB_TUE, PTB_FRI = 1, 2, 5

REMINDER_NEWS = "🗞 News run — time to render this week's news digest."
REMINDER_DLPULSE = "🧠 DL Pulse run — time to render the deep-learning pulse digest."
REMINDER_TRENDS = "📈 Trends run — first Monday: time for the monthly trends digest."

HELP_TEXT = (
    "AI-Tech Field Pulse — Ivan's AI/tech digest feed.\n\n"
    "I post a link each time a new digest is published, and send a few render "
    "reminders during the week.\n\n"
    "Commands:\n"
    "  /subscribe — start receiving new digests + reminders\n"
    "  /unsubscribe — stop receiving them\n"
    "  /help — show this message\n\n"
    "Digests live at https://melodiz.github.io/pulse-site/"
)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _RedactingFormatter(logging.Formatter):
    """Defense-in-depth: scrub any 'bot<id>:<secret>' token from the FULL formatted
    record (message AND traceback), independent of per-logger levels."""

    _TOKEN = re.compile(r"bot\d{4,}:[A-Za-z0-9_-]{20,}")

    def format(self, record: logging.LogRecord) -> str:
        return self._TOKEN.sub("bot<REDACTED>", super().format(record))


logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
for _handler in logging.getLogger().handlers:
    _handler.setFormatter(_RedactingFormatter(_LOG_FORMAT))
# TOKEN HYGIENE: httpx logs each request URL (which embeds the bot token) at INFO.
# Pin it to WARNING so the token never reaches the journal; the redacting formatter
# above is the backstop for any other path (including exception tracebacks). Same for
# the noisy apscheduler scheduler logger.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("pulse_bot")


# ----------------------------------------------------------------------- persistence
def _atomic_write_json(path: Path, data: Any) -> None:
    """Crash-safe JSON write: temp in the same dir -> flush+fsync -> os.replace -> dir fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        tmp_path = None  # ownership transferred by the rename
        dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _append_jsonl(path: Path, record: Any) -> None:
    """Append one JSON object per line (single-writer daemon, so plain append is safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def load_subscribers() -> dict[int, dict]:
    if not SUBS_FILE.exists():
        return {}
    try:
        raw = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        log.exception("could not parse %s; starting with an empty subscriber set", SUBS_FILE)
        return {}
    if not isinstance(raw, list):
        log.error("%s is not a list; starting with an empty subscriber set", SUBS_FILE)
        return {}
    subs: dict[int, dict] = {}
    dropped = 0
    for entry in raw:
        try:
            chat_id = int(entry["chat_id"])  # type: ignore[index]
        except (TypeError, KeyError, ValueError):
            dropped += 1  # one bad row must not nuke the whole store
            continue
        first_seen = entry.get("first_seen") if isinstance(entry, dict) else None
        subs[chat_id] = {"chat_id": chat_id, "first_seen": first_seen}
    if dropped:
        log.warning("skipped %d malformed subscriber row(s)", dropped)
    return subs


def save_subscribers(subs: dict[int, dict]) -> None:
    _atomic_write_json(SUBS_FILE, list(subs.values()))


# ------------------------------------------------------------------------- broadcast
async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    """Send text to every subscriber; prune those who blocked the bot. Never aborts the batch."""
    subs: dict[int, dict] = context.bot_data["subscribers"]
    dead: list[int] = []
    sent = 0
    for chat_id in list(subs):
        try:
            await context.bot.send_message(chat_id, text)
            sent += 1
        except Forbidden:
            dead.append(chat_id)  # 403: user blocked the bot -> prune
        except RetryAfter as exc:
            delay = exc.retry_after  # int now; documented to become timedelta in a future major
            secs = delay.total_seconds() if isinstance(delay, dt.timedelta) else float(delay)
            await asyncio.sleep(secs + 1)
            try:
                await context.bot.send_message(chat_id, text)
                sent += 1
            except Forbidden:
                dead.append(chat_id)  # blocked during the retry -> still prune
            except TelegramError:
                log.warning("retry after rate-limit still failed for one subscriber")
        except TelegramError:
            log.exception("send_message failed for one subscriber (continuing)")
    if dead:
        for chat_id in dead:
            subs.pop(chat_id, None)
        save_subscribers(subs)
        log.info("pruned %d blocked subscriber(s)", len(dead))
    log.info("broadcast delivered to %d/%d subscriber(s)", sent, sent + len(dead))
    return sent


def format_broadcast(payload: dict) -> str:
    title = (payload.get("title") or "new digest").strip()
    url = (payload.get("url") or "").strip()
    source = (payload.get("source") or "").strip()
    date = (payload.get("date") or "").strip()
    head = "📡 AI-Tech Field Pulse"
    tail = " ".join(p for p in (source, date) if p)
    if tail:
        head = f"{head} — {tail}"
    return "\n".join(p for p in (head, title, url) if p)


# ----------------------------------------------------------------------- command handlers
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    subs: dict[int, dict] = context.bot_data["subscribers"]
    if chat_id in subs:
        await update.effective_message.reply_text("You're already subscribed ✓")
        return
    subs[chat_id] = {"chat_id": chat_id, "first_seen": dt.datetime.now(MSK).isoformat()}
    save_subscribers(subs)
    log.info("new subscriber (now %d total)", len(subs))
    await update.effective_message.reply_text(
        "Subscribed ✓ You'll get new digests and weekly render reminders. /unsubscribe to stop."
    )


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    subs: dict[int, dict] = context.bot_data["subscribers"]
    if subs.pop(chat_id, None) is not None:
        save_subscribers(subs)
        log.info("subscriber left (now %d total)", len(subs))
        await update.effective_message.reply_text("Unsubscribed. Come back anytime with /subscribe.")
    else:
        await update.effective_message.reply_text("You weren't subscribed.")


# ----------------------------------------------------------------------- owner-only handlers
async def on_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Feedback courier: capture OWNER text replies into feedback_inbox.jsonl. Others ignored silently."""
    if update.effective_chat.id != context.bot_data["owner_id"]:
        return  # silently ignore replies from anyone who isn't the owner
    msg = update.effective_message
    text = (msg.text or "").strip()
    if not text:
        return
    record = {"ts": dt.datetime.now(MSK).isoformat(), "text": text}
    try:
        _append_jsonl(FEEDBACK_FILE, record)
    except OSError:
        log.exception("failed to append feedback")
        await msg.reply_text("⚠️ Couldn't save that — try again.")
        return
    log.info("feedback captured (%d chars)", len(text))
    await msg.reply_text("Feedback logged ✓")


def _sanitize_md_name(name: str | None, fallback: str) -> str:
    """Basename only (strip path separators / control chars); ensure a .md extension."""
    candidate = (name or "").strip()
    candidate = re.sub(r".*[\\/]", "", candidate)            # strip any directory components
    candidate = re.sub(r"[\x00-\x1f]", "", candidate)        # strip control chars
    candidate = candidate.lstrip(". -")                      # no leading dot/dash/space (dotfiles, CLI-flag footguns)
    if not candidate:
        candidate = fallback
    if not candidate.lower().endswith(".md"):
        candidate += ".md"
    return candidate


async def on_owner_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """File ingest: OWNER-sent documents are saved to data/incoming/ for CC to pull."""
    if update.effective_chat.id != context.bot_data["owner_id"]:
        return  # owner only
    msg = update.effective_message
    doc = msg.document
    if doc is None:
        return
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    name = _sanitize_md_name(doc.file_name, fallback=f"digest-{update.update_id}")
    dest = INCOMING_DIR / name
    tmp = INCOMING_DIR / (name + ".part")
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(custom_path=str(tmp))
        os.replace(tmp, dest)  # only a fully-downloaded file ever appears as a finished .md
    except (TelegramError, OSError):
        log.exception("failed to download owner document")
        try:
            tmp.unlink(missing_ok=True)  # never leave a partial file for CC to pull
        except OSError:
            pass
        await msg.reply_text("⚠️ Download failed — try resending.")
        return
    log.info("saved owner document to incoming/%s", name)
    await msg.reply_text(f"Saved “{name}” to incoming ✓ Run “process new files” to render it.")


# ------------------------------------------------------------------------- jobs (MSK)
async def notify_owner(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Single send to the OWNER only — run reminders go here, NOT to subscribers."""
    try:
        await context.bot.send_message(context.bot_data["owner_id"], text)
        log.info("owner reminder sent")
    except TelegramError:
        log.exception("failed to send owner reminder")


async def job_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    if dt.datetime.now(MSK).date().weekday() != 0:  # stdlib: Monday == 0
        return
    await notify_owner(context, REMINDER_NEWS)


async def job_dlpulse(context: ContextTypes.DEFAULT_TYPE) -> None:
    if dt.datetime.now(MSK).date().weekday() not in (1, 4):  # stdlib: Tue == 1, Fri == 4
        return
    await notify_owner(context, REMINDER_DLPULSE)


async def job_trends(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = dt.datetime.now(MSK).date()
    if today.weekday() != 0 or today.day > 7:  # first Monday of the month
        return
    await notify_owner(context, REMINDER_TRENDS)


async def job_poll_broadcast_queue(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Claim-by-rename the trigger file, broadcast it, then clear. Race-safe for one process."""
    target: Path | None = None
    if QUEUE_CLAIM.exists():
        target = QUEUE_CLAIM  # recover a claim left by a previous crashed run
    elif QUEUE_FILE.exists():
        try:
            os.replace(QUEUE_FILE, QUEUE_CLAIM)
            target = QUEUE_CLAIM
        except OSError:
            return
    if target is None:
        return
    try:
        raw = target.read_text(encoding="utf-8").strip()
    except OSError:
        log.exception("could not read broadcast trigger")
        return
    if not raw:
        target.unlink(missing_ok=True)  # empty trigger: nothing to do
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("malformed broadcast_queue.json — discarding")
        target.unlink(missing_ok=True)  # bad file: discard so the loop doesn't spin on it
        return
    try:
        await broadcast(context, format_broadcast(payload))
    except Exception:
        # Leave the claim in place so the next poll retries (at-least-once delivery):
        # a possible duplicate beats a silently dropped digest if a send is interrupted
        # (e.g. CancelledError on a systemd stop).
        log.exception("broadcast send failed; will retry on next poll")
        return
    log.info("digest broadcast sent: %s", payload.get("url", ""))
    target.unlink(missing_ok=True)  # cleared only after a clean send


# ------------------------------------------------------------------------------ boot
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Last-resort handler so handler/job exceptions are logged (and token-scrubbed), not silent."""
    log.error("unhandled error while processing an update/job", exc_info=context.error)


async def _post_init(app: Application) -> None:
    # Ensure no stale webhook blocks long polling (getUpdates won't work with a webhook set).
    info = await app.bot.get_webhook_info()
    if info.url:
        await app.bot.delete_webhook(drop_pending_updates=True)
        log.warning("removed a pre-existing webhook so long polling can run")
    me = await app.bot.get_me()
    log.info("pulse_bot online as @%s; %d subscriber(s)", me.username, len(app.bot_data["subscribers"]))


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"pulse_bot: required env var {name} is missing/empty (check EnvironmentFile)")
    return value


def main() -> None:
    token = _require_env("BOT_TOKEN")
    try:
        owner_id = int(_require_env("CHAT_ID"))
    except ValueError:
        raise SystemExit("pulse_bot: CHAT_ID must be an integer chat id")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    # Anchor every job/time to Moscow time (zoneinfo, not pytz) and disable link
    # previews globally (the v22 replacement for the removed disable_web_page_preview).
    defaults = Defaults(tzinfo=MSK, link_preview_options=LinkPreviewOptions(is_disabled=True))
    app = (
        ApplicationBuilder()
        .token(token)
        .defaults(defaults)
        .post_init(_post_init)
        .build()
    )

    app.bot_data["owner_id"] = owner_id
    app.bot_data["subscribers"] = load_subscribers()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    # Owner text replies -> feedback. (Documents are not TEXT, so they fall through to the next handler.)
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT & ~filters.COMMAND, on_owner_reply))
    # Owner-sent documents -> incoming/.
    app.add_handler(MessageHandler(filters.Document.ALL, on_owner_document))
    app.add_error_handler(on_error)

    jq = app.job_queue  # available because python-telegram-bot[job-queue] is installed
    nine = dt.time(hour=9, minute=0, tzinfo=MSK)
    nine_oh_five = dt.time(hour=9, minute=5, tzinfo=MSK)
    jq.run_daily(job_news, time=nine, days=(PTB_MON,), name="news")
    jq.run_daily(job_dlpulse, time=nine, days=(PTB_TUE, PTB_FRI), name="dlpulse")
    jq.run_daily(job_trends, time=nine_oh_five, days=(PTB_MON,), name="trends")
    jq.run_repeating(job_poll_broadcast_queue, interval=BROADCAST_POLL_SECONDS, first=5, name="broadcast_queue")

    log.info("starting long polling")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
