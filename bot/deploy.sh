#!/bin/sh
# deploy.sh — v2 deploy of the pulse_bot long-polling daemon to the VPS.
#
# RETIRES v1 (cron + remind.sh + fetch.sh). Before the daemon polls, the v1 cron
# block MUST be removed or you get a 409 (only one getUpdates poller per token).
# That cron removal is done as a separate, verified step (see CLAUDE.md / stage notes),
# NOT by this script.
#
# Usage:
#   ./deploy.sh            # deploy files + deps + install/reload unit (does NOT start)
#   ./deploy.sh --start    # also enable + (stop->wait->start) the service + health check
#
# Scope: writes only under ~/bots/pulse_bot/ on the remote, plus installing the
# unit file at /etc/systemd/system/pulse-bot.service (the daemon install itself).
# It NEVER ships env or data/, NEVER uses --delete, and NEVER touches wireguard,
# routing, other bot dirs, or ~/dev. The bot token is never printed.
#
# Transport: ssh alias `yandex-vps`, key auth assumed. systemd actions use sudo.

set -eu

HOST="yandex-vps"
REMOTE_DIR="bots/pulse_bot"                       # relative to remote $HOME
UNIT="pulse-bot.service"
CONDA_PY="\$HOME/miniconda3/envs/bots/bin/python"
CONDA_PIP="\$HOME/miniconda3/envs/bots/bin/pip"
SCRIPT_DIR=$(unset CDPATH; cd -- "$(dirname -- "$0")" && pwd)

START=0
[ "${1:-}" = "--start" ] && START=1

echo "deploy: target ${HOST}:~/${REMOTE_DIR}/ (env + data/ never shipped)"

# --- 1. ensure writable state dirs exist (inside ~ only) ----------------------
# shellcheck disable=SC2029
ssh "$HOST" "mkdir -p \"\$HOME/${REMOTE_DIR}/data/incoming\" \"\$HOME/${REMOTE_DIR}/data/.cache\""

# --- 2. rsync code + unit + requirements (NOT env, NOT data/, NO --delete) -----
rsync -av --chmod=F644 \
  "${SCRIPT_DIR}/pulse_bot.py" \
  "${SCRIPT_DIR}/requirements.txt" \
  "${SCRIPT_DIR}/pulse_bot.service" \
  "${HOST}:${REMOTE_DIR}/"

# --- 3. install deps into the shared conda env (idempotent) -------------------
# shellcheck disable=SC2029
ssh "$HOST" "${CONDA_PIP} install -q -r \"\$HOME/${REMOTE_DIR}/requirements.txt\" && \
  ${CONDA_PY} -c 'import telegram; print(\"PTB\", telegram.__version__)'"

# --- 4. install/refresh the systemd unit (needs sudo) + daemon-reload ---------
if ! ssh "$HOST" "sudo -n true" 2>/dev/null; then
  echo "deploy: ERROR — passwordless sudo unavailable on ${HOST}; cannot install the unit." >&2
  echo "deploy: install it by hand:  sudo cp ~/${REMOTE_DIR}/${UNIT} /etc/systemd/system/ && sudo systemctl daemon-reload" >&2
  exit 3
fi
# shellcheck disable=SC2029
ssh "$HOST" "sudo cp \"\$HOME/${REMOTE_DIR}/${UNIT}\" \"/etc/systemd/system/${UNIT}\" && sudo systemctl daemon-reload"
echo "deploy: unit installed + daemon-reloaded."

if [ "$START" -eq 0 ]; then
  echo "deploy: files staged. To start:  ./deploy.sh --start   (or: sudo systemctl enable --now ${UNIT})"
  exit 0
fi

# --- 5. enable + (stop -> wait -> start) to avoid a long-poll 409 overlap -----
# A redeploy can briefly overlap the old long-poll; stop, wait out the poll
# window, then start so the new poller never 409s the old one.
# shellcheck disable=SC2029
ssh "$HOST" "sudo systemctl enable ${UNIT}; sudo systemctl stop ${UNIT} 2>/dev/null || true; sleep 12; sudo systemctl start ${UNIT}"

# --- 6. health check: status + journal tail; flag 409 / token leaks -----------
echo "deploy: --- health check ---"
# shellcheck disable=SC2029
ssh "$HOST" "sleep 3
  systemctl --no-pager --full status ${UNIT} | sed -n '1,12p'
  echo '--- last 30 journal lines ---'
  journalctl -u ${UNIT} -n 30 --no-pager
  echo '--- 409 / token scan ---'
  if journalctl -u ${UNIT} -n 200 --no-pager | grep -qi '409\\|Conflict'; then
    echo 'WARNING: 409 conflict in logs — another poller is active'; else echo 'OK: no 409 in logs'; fi
  if journalctl -u ${UNIT} -n 200 --no-pager | grep -qiE 'bot[0-9]{6,}:'; then
    echo 'WARNING: a token-like string appears in logs'; else echo 'OK: no token-like string in logs'; fi"
echo "deploy: done."
