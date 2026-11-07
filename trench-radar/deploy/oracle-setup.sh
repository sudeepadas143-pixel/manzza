#!/usr/bin/env bash
# TRENCH//RADAR on any Ubuntu 24.04 server: a cheap VPS (e.g. RackNerd 1 GB), Oracle Cloud, etc.
# Installs the app, runs it as a service that survives reboots, sets a dashboard password,
# and makes it reachable privately from your devices through Tailscale (HTTPS, no open ports).
#
# Run on the server:   bash oracle-setup.sh
# Re-running is safe: it updates the code and keeps your settings and data.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/sudeepadas143-pixel/manzza.git}"
BRANCH="${BRANCH:-claude/trench-radar}"
DIR="$HOME/trench-radar-app"
APP="$DIR/trench-radar"
SVC=trench-radar

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
# cheap VPSs often log you in as root, and minimal images may not have sudo
if [ "$(id -u)" -eq 0 ]; then sudo() { "$@"; }; fi

# the app peaks around 0.5-0.9 GB; on a 1 GB server a swap file keeps a busy moment from killing it
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 2000 ] && ! swapon --show | grep -q .; then
  say "Adding a 2 GB swap file (this server has ${MEM_MB} MB of memory)"
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  sudo chmod 600 /swapfile && sudo mkswap -q /swapfile && sudo swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

say "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq git python3 python3-venv python3-pip curl ca-certificates >/dev/null
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || {
  echo "Python $PYV found; TRENCH//RADAR needs 3.12+. Use the Ubuntu 24.04 image."; exit 1; }

say "Getting the code ($BRANCH)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q "$BRANCH" && git -C "$DIR" reset -q --hard "origin/$BRANCH"
else
  # if the repo is ever made private, GitHub will ask for a username and a read-only access token
  git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$DIR"
fi

say "Installing Python dependencies"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

say "Settings"
ENV="$APP/.env"
if [ ! -f "$ENV" ]; then
  cp "$APP/.env.example" "$ENV"
  TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
  {
    echo ""
    echo "# written by deploy/oracle-setup.sh"
    echo "# Tailscale serves the dashboard; nothing listens publicly"
    echo "DASHBOARD_HOST=127.0.0.1"
    echo "DASHBOARD_PORT=8787"
    echo "DASHBOARD_TOKEN=$TOKEN"
  } >> "$ENV"
  chmod 600 "$ENV"
  echo "Created $ENV with a new dashboard password."
else
  echo "Keeping existing $ENV."
fi
TOKEN=$(grep -E '^DASHBOARD_TOKEN=' "$ENV" | tail -1 | cut -d= -f2-)

say "Service (starts on boot, restarts on crash)"
sudo tee /etc/systemd/system/$SVC.service >/dev/null <<UNIT
[Unit]
Description=TRENCH//RADAR
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m radar serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable -q --now $SVC
sudo systemctl restart $SVC
sleep 5
curl -fs -o /dev/null http://127.0.0.1:8787/ && echo "Dashboard is running on the server." || {
  echo "The service did not start. Logs:"; sudo journalctl -u $SVC -n 40 --no-pager; exit 1; }

say "Tailscale (private access from your phone and PC)"
if ! command -v tailscale >/dev/null; then curl -fsSL https://tailscale.com/install.sh | sh; fi
if ! tailscale status >/dev/null 2>&1; then
  echo "Open the link below and sign in with the same account you use on your phone:"
  sudo tailscale up
fi
sudo tailscale serve --bg 8787 >/dev/null
URL=$(tailscale serve status 2>/dev/null | grep -oE 'https://[^ ]+' | head -1)

say "Done"
echo "Open on any device signed in to your Tailscale account:"
echo "    ${URL:-https://<this-machine>.<your-tailnet>.ts.net}"
echo "Dashboard password:"
echo "    $TOKEN"
echo
echo "iPhone: open the link in Safari, enter the password, then Share > Add to Home Screen."
echo "Android: open it in Chrome, enter the password, then menu > Add to Home screen."
echo "Add API keys later by editing $ENV, then: sudo systemctl restart $SVC"
echo "Logs: sudo journalctl -u $SVC -f"
