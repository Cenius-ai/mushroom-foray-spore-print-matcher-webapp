#!/usr/bin/env bash
# Mushroom Foray Spore Print Matcher — install, migrate, seed. Exits when done.
# Only project-level dependencies are installed: no sudo, no system packages.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export GRADIO_ANALYTICS_ENABLED=False
export HF_HUB_DISABLE_TELEMETRY=1

echo "==> [1/4] Python tooling"
"$PYTHON" -m pip install --upgrade --quiet pip setuptools wheel

echo "==> [2/4] Project dependencies"
"$PYTHON" -m pip install --quiet -r requirements.txt

echo "==> [3/4] Session secret (generated once, kept in .env)"
if [ ! -f .env ]; then
  : > .env
fi
if ! grep -q '^SESSION_SECRET=.' .env 2>/dev/null; then
  secret=$("$PYTHON" -c "import secrets; print(secrets.token_hex(32))")
  printf 'SESSION_SECRET=%s\n' "$secret" >> .env
fi

echo "==> [4/4] Schema + demo data"
"$PYTHON" seed.py

echo "==> Import self-check"
"$PYTHON" -c "import app; print('    app imports cleanly')"

echo
echo "Setup complete."
echo "Start the app with:  ${PYTHON} app.py      (http://localhost:7860)"
echo "Demo sign-in:        cenius@cenius.ai / cenius   (also: demo / demo1234)"
