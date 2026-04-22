#!/bin/sh
set -eu

: "${JARVIS_SN13_LISTENER_WALLET_NAME:?}"
: "${JARVIS_SN13_LISTENER_WALLET_HOTKEY:?}"
: "${JARVIS_SN13_LISTENER_WALLET_PATH:?}"
: "${JARVIS_SN13_LISTENER_NETWORK:?}"
: "${JARVIS_SN13_LISTENER_CAPTURE_DIR:?}"
: "${JARVIS_SN13_DB_PATH:?}"
: "${JARVIS_SN13_LISTENER_PORT:?}"

set -- \
  /app/.venv/bin/python \
  /app/subnets/sn13/listener/listener.py \
  --wallet "${JARVIS_SN13_LISTENER_WALLET_NAME}" \
  --hotkey "${JARVIS_SN13_LISTENER_WALLET_HOTKEY}" \
  --wallet-path "${JARVIS_SN13_LISTENER_WALLET_PATH}" \
  --network "${JARVIS_SN13_LISTENER_NETWORK}" \
  --db-path "${JARVIS_SN13_DB_PATH}" \
  --capture-dir "${JARVIS_SN13_LISTENER_CAPTURE_DIR}" \
  --axon-port "${JARVIS_SN13_LISTENER_PORT}" \
  --axon-ip "${JARVIS_SN13_LISTENER_IP:-0.0.0.0}"

if [ -n "${JARVIS_SN13_LISTENER_EXTERNAL_IP:-}" ]; then
  set -- "$@" --axon-external-ip "${JARVIS_SN13_LISTENER_EXTERNAL_IP}"
fi

if [ -n "${JARVIS_SN13_LISTENER_EXTERNAL_PORT:-}" ]; then
  set -- "$@" --axon-external-port "${JARVIS_SN13_LISTENER_EXTERNAL_PORT}"
fi

if [ -n "${JARVIS_SN13_LISTENER_MAX_WORKERS:-}" ]; then
  set -- "$@" --max-workers "${JARVIS_SN13_LISTENER_MAX_WORKERS}"
fi

case "${JARVIS_SN13_LISTENER_OFFLINE:-0}" in
  1|true|TRUE|yes|YES|on|ON)
    set -- "$@" --offline
    ;;
esac

exec "$@"
