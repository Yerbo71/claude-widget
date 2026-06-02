#!/usr/bin/env bash
# All-in-one installer for the Claude Usage widget.
# Sets up system deps, a venv with pywebview, the usage cron, and a desktop launcher.
set -euo pipefail

APP_NAME="claude-widget"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/$APP_NAME"
VENV="$DEST/.venv"
CRON_MARKER="# claude-widget-usage"
DATA_DIR="$HOME/.claude-widget"
USAGE_LOG="$DATA_DIR/usage_cron.log"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*" >&2; }

# Report where we die so install failures are never silent.
trap 'rc=$?; [ "$rc" -ne 0 ] && warn "install.sh aborted at line ${BASH_LINENO[0]:-$LINENO} (exit $rc)"' ERR

# ---------------------------------------------------------------------------
# 1. System dependencies (apt-based distros).
# ---------------------------------------------------------------------------
install_system_deps() {
  local pkgs=(python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 libgtk-3-0)
  # WebKit gir package name differs by Ubuntu version: probe 4.1, then 4.0.
  if apt-cache show gir1.2-webkit2-4.1 >/dev/null 2>&1; then
    pkgs+=(gir1.2-webkit2-4.1)
  elif apt-cache show gir1.2-webkit2-4.0 >/dev/null 2>&1; then
    pkgs+=(gir1.2-webkit2-4.0)
  else
    warn "No gir1.2-webkit2-4.x candidate found; the window may not render."
  fi
  say "Installing system packages: ${pkgs[*]}"
  sudo apt-get update -y
  sudo apt-get install -y "${pkgs[@]}"
}

if command -v apt-get >/dev/null 2>&1; then
  install_system_deps
else
  warn "Non-apt distro detected. Ensure these are installed: python3-venv, PyGObject (gi),"
  warn "GTK3 and WebKit2GTK GObject-introspection bindings. Continuing anyway."
fi

# ---------------------------------------------------------------------------
# 2. Copy application files.
# ---------------------------------------------------------------------------
say "Installing app to $DEST"
mkdir -p "$DEST"
cp -f "$SRC_DIR/app.py" "$SRC_DIR/tokens.py" "$SRC_DIR/usage.py" "$SRC_DIR/icon.svg" "$DEST/"
rm -rf "$DEST/web"
cp -r "$SRC_DIR/web" "$DEST/web"

# ---------------------------------------------------------------------------
# 3. Run wrapper + desktop launcher + autostart entry.
#    Created early (before venv/pip/cron) so the app-menu icon always appears,
#    even if a later step fails on this machine.
# ---------------------------------------------------------------------------
cat > "$DEST/run.sh" <<EOF
#!/usr/bin/env bash
cd "$DEST"
exec "$VENV/bin/python" "$DEST/app.py"
EOF
chmod +x "$DEST/run.sh"

APPS="$HOME/.local/share/applications"
AUTO="$HOME/.config/autostart"
mkdir -p "$APPS" "$AUTO"
DESKTOP_FILE="$APPS/$APP_NAME.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Usage
Comment=Claude usage limits & token statistics
Exec=$DEST/run.sh
Icon=$DEST/icon.svg
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
cp -f "$DESKTOP_FILE" "$AUTO/$APP_NAME.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
say "Desktop launcher installed: $DESKTOP_FILE"

# ---------------------------------------------------------------------------
# 4. Virtualenv (with system site-packages so it can use gi/WebKit) + pywebview.
# ---------------------------------------------------------------------------
say "Creating venv at $VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
say "Installing pywebview"
"$VENV/bin/python" -m pip install pywebview

# ---------------------------------------------------------------------------
# 5. Usage-scraper cron (idempotent). Replaces any prior tracker line.
#    Weekdays 9-18, every 30 min. Marker comment lets us dedupe on re-install.
# ---------------------------------------------------------------------------
mkdir -p "$DATA_DIR"
CRON_CMD="*/30 9-18 * * 1-5 DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus $VENV/bin/python $DEST/usage.py >> $USAGE_LOG 2>&1 $CRON_MARKER"
if command -v crontab >/dev/null 2>&1; then
  existing="$(crontab -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "$existing" \
      | grep -v -F "$CRON_MARKER" \
      | grep -v -F "claude_usage_tracker.py" || true)"
  printf '%s\n' "$filtered" "$CRON_CMD" | grep -v '^$' | crontab -
  say "Cron installed (weekdays 09:00-18:00, every 30 min)"
else
  warn "crontab not found; skipping usage cron (the widget still works)."
fi

say "Done. Launch 'Claude Usage' from the app menu, or run: $DEST/run.sh"
