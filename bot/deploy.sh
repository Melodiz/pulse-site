#!/bin/sh
# deploy.sh — Phase 2 deploy of the pulse reminder to the VPS.
#
# DO NOT run this until Ivan has hand-placed the token at
# ~/bots/pulse_bot/env (mode 600) on the box. This script never creates,
# reads, or ships that env file.
#
# What it does, scoped ENTIRELY to ~/bots/pulse_bot/ on the remote:
#   1. ensure ~/bots/pulse_bot/ exists
#   2. rsync ONLY remind.sh + crontab.pulse there (never the env file)
#   3. chmod +x remind.sh
#   4. install the crontab block idempotently — replace the delimited
#      "# >>> pulse reminders >>>" … "# <<< pulse reminders <<<" section,
#      leaving every other crontab entry untouched
#   5. health check: fire remind.sh once, report the parsed result
#
# GUARD: no --delete anywhere, and every remote path is under
# ~/bots/pulse_bot/ — this script must never touch anything outside it.
# Transport: ssh alias `yandex-vps`, key auth assumed. Cron-only; no
# service, no inbound ports.

set -eu

HOST="yandex-vps"            # ssh alias, key auth assumed
REMOTE_DIR="bots/pulse_bot"  # relative to remote $HOME -> ~/bots/pulse_bot
SCRIPT_DIR=$(unset CDPATH; cd -- "$(dirname -- "$0")" && pwd)

# In the ssh lines below, ${REMOTE_DIR} is meant to expand CLIENT-side (it's a
# local constant) while \$HOME is escaped to expand on the SERVER. That is the
# intended split, so SC2029 (client-side expansion note) is silenced per-line.

echo "deploy: target ${HOST}:~/${REMOTE_DIR}/ (env file NOT shipped — hand-placed)"

# --- 1. ensure the remote dir exists (inside $HOME only) ---------------
# shellcheck disable=SC2029
ssh "$HOST" "mkdir -p \"\$HOME/${REMOTE_DIR}\""

# --- 2. rsync the two files (NOT env, NO --delete) ---------------------
rsync -av --chmod=F644 \
  "${SCRIPT_DIR}/remind.sh" "${SCRIPT_DIR}/crontab.pulse" \
  "${HOST}:${REMOTE_DIR}/"

# --- 3. make remind.sh executable --------------------------------------
# shellcheck disable=SC2029
ssh "$HOST" "chmod +x \"\$HOME/${REMOTE_DIR}/remind.sh\""

# --- 4. install the crontab block idempotently -------------------------
# Strip any prior pulse block (delimiters inclusive), append the fresh one
# from crontab.pulse, reinstall. Other crontab entries are preserved.
ssh "$HOST" "sh -s" <<'REMOTE'
set -eu
dir="$HOME/bots/pulse_bot"
begin="# >>> pulse reminders >>>"
end="# <<< pulse reminders <<<"
existing=$(crontab -l 2>/dev/null || true)
cleaned=$(printf '%s\n' "$existing" | awk -v b="$begin" -v e="$end" '
  $0==b {skip=1}
  skip==0 {print}
  $0==e {skip=0}
')
block=$(cat "$dir/crontab.pulse")
printf '%s\n%s\n' "$cleaned" "$block" | crontab -
echo "deploy: crontab block installed (other entries preserved)"
REMOTE

# --- 5. health check: one reminder, parsed result only -----------------
echo "deploy: health check —"
# shellcheck disable=SC2029
ssh "$HOST" "\$HOME/${REMOTE_DIR}/remind.sh \"\$HOME/${REMOTE_DIR}/env\" 'pulse deploy health check'"

echo "deploy: done."
