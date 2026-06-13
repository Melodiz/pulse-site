#!/bin/sh
# fetch.sh — pull digest documents Ivan sent to the bot into incoming/.
#
# v1 design (locked): PULL-on-demand. Nothing scheduled receives — a CC
# session runs this via the "process new files" command. Telegram retains
# updates ~24h; a document not pulled within a day is lost (acceptable).
#
# Usage:  fetch.sh [env_file]
#   $1  path to the env file holding BOT_TOKEN (default below). CHAT_ID is
#       not needed for receiving and is not required here.
#
# State (the only new VPS state this adds), alongside the script:
#   <botdir>/offset            last update_id+1, so files aren't re-fetched
#   <botdir>/incoming/<name>.md downloaded documents
#
# Token hygiene (KB convention, same as remind.sh): the getUpdates / getFile
# / file-download URLs all embed the bot token. They are built in variables
# and NEVER echoed; curl stderr (which can leak the URL) is captured to a
# temp file and discarded. Only a file count + saved names are printed.
#
# Exit codes: 0 = ok (incl. "no updates"); 1 = API/curl failure;
#             3 = env file missing; 4 = BOT_TOKEN empty.

set -u

envfile="${1:-/home/melodiz/bots/pulse_bot/env}"
botdir=$(unset CDPATH; cd -- "$(dirname -- "$0")" && pwd)
incoming="$botdir/incoming"
offsetfile="$botdir/offset"

# --- load token (never printed) ----------------------------------------
if [ ! -f "$envfile" ]; then
  echo "fetch.sh: env file not found: $envfile" >&2
  exit 3
fi
set -a
# shellcheck disable=SC1090  # path is a runtime argument, not statically known
. "$envfile"
set +a
if [ -z "${BOT_TOKEN:-}" ]; then
  echo "fetch.sh: BOT_TOKEN empty in env file: $envfile" >&2
  exit 4
fi

mkdir -p "$incoming"

# --- read persisted offset (digits only; default 0) --------------------
offset=0
if [ -f "$offsetfile" ]; then
  offset=$(cat "$offsetfile" 2>/dev/null || echo 0)
  case "$offset" in
    ''|*[!0-9]*) offset=0 ;;
  esac
fi

base="https://api.telegram.org"
api="${base}/bot${BOT_TOKEN}"                    # embeds token — NEVER echo

# --- getUpdates (URL in var; stderr discarded) -------------------------
errf=$(mktemp)
updates=$(curl --silent --show-error --get \
  --data-urlencode "offset=${offset}" \
  --data-urlencode "timeout=0" \
  "${api}/getUpdates" 2>"$errf")
rc=$?
rm -f "$errf"
if [ "$rc" -ne 0 ]; then
  echo "fetch.sh: getUpdates curl failed (exit $rc)" >&2
  exit 1
fi

ok=$(printf '%s' "$updates" | jq -r '.ok' 2>/dev/null || echo false)
if [ "$ok" != "true" ]; then
  desc=$(printf '%s' "$updates" | jq -r '.description // "unknown error"' 2>/dev/null || echo "parse error")
  echo "fetch.sh: getUpdates ok:false — $desc" >&2
  exit 1
fi

# Highest update_id across ALL updates (document or not) -> advances offset
# so consumed, non-document messages are not re-fetched either.
maxid=$(printf '%s' "$updates" | jq -r '[.result[].update_id] | max // empty')

# Documents only: update_id <TAB> file_id <TAB> file_name, one per line.
docsfile=$(mktemp)
printf '%s' "$updates" | jq -r '
  .result[]
  | (.message // .channel_post // {}) as $m
  | select($m.document != null)
  | [ (.update_id|tostring), $m.document.file_id, ($m.document.file_name // "") ]
  | @tsv
' > "$docsfile"

count=0
savedlist=""
tab=$(printf '\t')
while IFS="$tab" read -r uid fid fname; do
  [ -z "${uid:-}" ] && continue

  # getFile -> file_path
  errf=$(mktemp)
  gf=$(curl --silent --show-error --get \
    --data-urlencode "file_id=${fid}" \
    "${api}/getFile" 2>"$errf")
  grc=$?
  rm -f "$errf"
  if [ "$grc" -ne 0 ]; then
    echo "fetch.sh: getFile curl failed for update $uid (exit $grc)" >&2
    continue
  fi
  fpath=$(printf '%s' "$gf" | jq -r '.result.file_path // empty')
  if [ -z "$fpath" ]; then
    echo "fetch.sh: no file_path for update $uid (skipped)" >&2
    continue
  fi

  # Sanitize saved name: basename only (strip path separators), drop control
  # chars, default to <update_id>, ensure a .md extension.
  saved=$(printf '%s' "$fname" | sed 's#.*[/\\]##' | tr -d '\000-\037')
  [ -z "$saved" ] && saved="$uid"
  case "$saved" in
    *.md) : ;;
    *)    saved="${saved}.md" ;;
  esac

  # Download the file (URL embeds the token — NEVER printed). --fail so an
  # HTTP error body is not saved as a bogus .md; stderr discarded.
  fileurl="${base}/file/bot${BOT_TOKEN}/${fpath}"
  errf=$(mktemp)
  if curl --silent --show-error --fail -o "${incoming}/${saved}" "$fileurl" 2>"$errf"; then
    rm -f "$errf"
    count=$((count + 1))
    savedlist="${savedlist}${saved}
"
  else
    drc=$?
    rm -f "$errf"
    echo "fetch.sh: download failed for update $uid (exit $drc)" >&2
  fi
done < "$docsfile"
rm -f "$docsfile"

# --- advance offset to highest seen +1 ---------------------------------
if [ -n "$maxid" ]; then
  echo $((maxid + 1)) > "$offsetfile"
fi

# --- report: count + saved names only (no URLs, no token) --------------
echo "fetch: ${count} file(s) downloaded"
if [ "$count" -gt 0 ]; then
  printf '%s' "$savedlist" | sed 's/^/  - /'
fi
exit 0
