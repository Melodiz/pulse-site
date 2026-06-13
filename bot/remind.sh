#!/bin/sh
# remind.sh — fire a one-way Telegram reminder via the Bot API sendMessage.
#
# v1 design (locked): NO daemon on the VPS. This script is invoked by cron
# only (see crontab.pulse). Reminders are fire-and-forget; no reply handling.
#
# Usage:  remind.sh [env_file] <reminder_text>
#   $1  path to the env file holding BOT_TOKEN + CHAT_ID.
#       Default: /home/melodiz/bots/pulse_bot/env  (mode 600, hand-placed
#       by Ivan on the VPS — never in git).
#   $2  the reminder text to send.
#
# Token hygiene (KB convention): the sendMessage URL embeds the bot token.
# This script NEVER echoes the URL or the curl command. curl's stderr can
# leak the URL, so it is captured to a temp file and discarded. Only the
# parsed API result (+ a timestamp) is printed.
#
# Exit codes: 0 = ok:true; 1 = send/parse failure; 2 = no text;
#             3 = env file missing; 4 = BOT_TOKEN/CHAT_ID empty.

set -u

# --- args ---------------------------------------------------------------
envfile="${1:-/home/melodiz/bots/pulse_bot/env}"
text="${2:-}"

if [ -z "$text" ]; then
  echo "remind.sh: no reminder text given (arg \$2)" >&2
  exit 2
fi

if [ ! -f "$envfile" ]; then
  echo "remind.sh: env file not found: $envfile" >&2
  exit 3
fi

# --- load secrets (never printed) --------------------------------------
set -a
# shellcheck disable=SC1090  # path is a runtime argument, not statically known
. "$envfile"
set +a

if [ -z "${BOT_TOKEN:-}" ] || [ -z "${CHAT_ID:-}" ]; then
  echo "remind.sh: BOT_TOKEN or CHAT_ID empty in env file: $envfile" >&2
  exit 4
fi

# --- send (api_url holds the token — NEVER echo it) --------------------
api_url="https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"
errfile=$(mktemp)
resp=$(curl --silent --show-error \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${text}" \
  "$api_url" 2>"$errfile")
rc=$?
rm -f "$errfile"   # stderr may contain the URL — discard, never print

ts=$(date '+%Y-%m-%d %H:%M:%S %Z')

if [ "$rc" -ne 0 ]; then
  # do NOT print curl stderr — it can contain the token-bearing URL
  echo "$ts remind: curl failed (exit $rc)" >&2
  exit 1
fi

# Telegram returns single-line JSON; parse with sed (no python/jq dep on VPS).
ok=$(printf '%s' "$resp" | sed -n 's/.*"ok":\([a-z]*\).*/\1/p')
if [ "$ok" = "true" ]; then
  mid=$(printf '%s' "$resp" | sed -n 's/.*"message_id":\([0-9]*\).*/\1/p')
  echo "$ts remind: ok:true (message_id ${mid})"
  exit 0
else
  desc=$(printf '%s' "$resp" | sed -n 's/.*"description":"\([^"]*\)".*/\1/p')
  echo "$ts remind: ok:false — ${desc}" >&2
  exit 1
fi
