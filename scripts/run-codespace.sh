#!/usr/bin/env bash
# Start FaceFinder inside a GitHub Codespace.
#
# Works out the public URL from the codespace's own environment, so the
# OAuth redirect URI and PUBLIC_BASE_URL always agree - getting those two
# out of step is the usual reason sign-in fails.
set -euo pipefail

PORT="${PORT:-8000}"

if [ -z "${CODESPACE_NAME:-}" ]; then
  echo "Not running in a Codespace (CODESPACE_NAME is unset)."
  echo "For local use, set PUBLIC_BASE_URL=http://localhost:${PORT} yourself."
  exit 1
fi

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
export PUBLIC_BASE_URL="https://${CODESPACE_NAME}-${PORT}.${DOMAIN}"

missing=0
for v in GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
  if [ -z "${!v:-}" ]; then
    echo "MISSING: $v"
    missing=1
  fi
done
if [ "$missing" = "1" ]; then
  cat <<'MSG'

Set these once as Codespaces secrets, not in the repo:
  https://github.com/settings/codespaces  ->  New secret
  Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, grant them to this
  repository, then rebuild or reopen the codespace.
MSG
  exit 1
fi

# A stable per-codespace session key. Sessions live in signed cookies, so a
# key that changed on every start would sign everyone out on every restart.
if [ -z "${SESSION_SECRET:-}" ]; then
  KEYFILE="$HOME/.facefinder-session-key"
  [ -f "$KEYFILE" ] || (umask 077; head -c 32 /dev/urandom | base64 > "$KEYFILE")
  export SESSION_SECRET="$(cat "$KEYFILE")"
fi

cat <<MSG
------------------------------------------------------------------
FaceFinder

  app URL      : ${PUBLIC_BASE_URL}
  redirect URI : ${PUBLIC_BASE_URL}/oauth2/callback

Two things to do before signing in:

1. Add that redirect URI in Google Cloud Console
     APIs & Services -> Credentials -> your OAuth client
     -> Authorised redirect URIs -> ADD URI

2. Make port ${PORT} public, or classmates get a GitHub login wall
     PORTS tab -> right-click port ${PORT} -> Port Visibility -> Public

------------------------------------------------------------------
MSG

# Via python -m rather than the console script: a pip --user install puts
# the uvicorn binary in ~/.local/bin, which is not always on PATH.
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
