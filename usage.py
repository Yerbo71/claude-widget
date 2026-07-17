#!/usr/bin/env python3
"""Read Claude Code usage limits from the account API and expose them to the widget.

Run directly (cron) to append a snapshot during business hours. Import to read
the log or trigger an on-demand refresh from the widget's "Refresh" button.

Historically this scraped the interactive `/usage` TUI over a PTY. Claude Code
2.1.x broke that path (the TUI now reports "Failed to load usage data" in a
headless session), so we instead call the same account endpoint the TUI uses —
https://api.anthropic.com/api/oauth/usage — with the OAuth token Claude Code
already stores in ~/.claude/.credentials.json. No quota is spent and there is no
fragile terminal parsing.
"""

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# All widget data is self-contained under ~/.claude-widget; nothing is written
# elsewhere in $HOME so the widget never touches external folders.
DATA_DIR = Path.home() / ".claude-widget"
LOG_FILE = DATA_DIR / "usage_log.json"
DEBUG_FILE = DATA_DIR / "usage_debug.txt"
CONFIG_FILE = DATA_DIR / "config.json"
NOTIFY_STATE_FILE = DATA_DIR / "notify_state.json"
ICON_FILE = Path(__file__).resolve().with_name("icon.svg")

KEYS = ["Current session", "Weekly All models", "Weekly Sonnet only", "Weekly Claude Design"]

DEFAULT_CONFIG = {"notifyEnabled": True, "notifyThreshold": 90}

# Claude Code stores its account OAuth token here; the same token authorizes the
# usage endpoint below. CLAUDE_CREDENTIALS overrides the path if needed.
CREDENTIALS_FILE = Path(os.environ.get("CLAUDE_CREDENTIALS", Path.home() / ".claude" / ".credentials.json"))
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code's public OAuth client
API_BETA = "oauth-2025-04-20"
HTTP_TIMEOUT = 15


def read_config() -> dict:
    """User settings (notification toggle + threshold), merged over defaults."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            cfg.update(stored)
    except (OSError, json.JSONDecodeError):
        pass
    cfg["notifyEnabled"] = bool(cfg.get("notifyEnabled", True))
    try:
        thr = int(cfg.get("notifyThreshold", 90))
    except (TypeError, ValueError):
        thr = 90
    cfg["notifyThreshold"] = max(1, min(100, thr))
    return cfg


def write_config(cfg: dict) -> dict:
    """Validate and persist user settings; returns the normalized config."""
    incoming = cfg if isinstance(cfg, dict) else {}
    enabled = bool(incoming.get("notifyEnabled", DEFAULT_CONFIG["notifyEnabled"]))
    try:
        thr = int(incoming.get("notifyThreshold", DEFAULT_CONFIG["notifyThreshold"]))
    except (TypeError, ValueError):
        thr = DEFAULT_CONFIG["notifyThreshold"]
    normalized = {"notifyEnabled": enabled, "notifyThreshold": max(1, min(100, thr))}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def is_business_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.hour < 9:
        return False
    if now.hour > 18 or (now.hour == 18 and now.minute > 0):
        return False
    return True


def _local_tz_name() -> str | None:
    """Best-effort IANA name of the machine's timezone (e.g. 'Asia/Almaty').

    The frontend counts a reset down against this zone, so returning a stable
    IANA name keeps the countdown correct regardless of the browser's own clock.
    """
    try:
        tz = Path("/etc/timezone")
        if tz.exists():
            name = tz.read_text(encoding="utf-8").strip()
            if name:
                return name
    except OSError:
        pass
    try:
        real = os.path.realpath("/etc/localtime")
        if "/zoneinfo/" in real:
            return real.split("/zoneinfo/")[-1]
    except OSError:
        pass
    return None


def _load_oauth() -> dict:
    """Return the claudeAiOauth block from Claude Code's credentials file."""
    data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict) or not oauth.get("accessToken"):
        raise RuntimeError("No Claude OAuth token found — sign in with `claude` first.")
    return oauth


def _refresh_token(oauth: dict) -> dict:
    """Exchange the refresh token for a fresh access token and persist it.

    Written atomically and only after the response is validated, so a failed or
    malformed refresh never corrupts the credentials Claude Code itself relies on.
    Returns the updated oauth block. Raises on any failure.
    """
    refresh = oauth.get("refreshToken")
    if not refresh:
        raise RuntimeError("Access token expired and no refresh token is available.")
    body = json.dumps(
        {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": OAUTH_CLIENT_ID}
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        tok = json.loads(resp.read().decode("utf-8"))
    access = tok.get("access_token")
    if not access:
        raise RuntimeError("Token refresh returned no access_token.")

    data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    block = data.setdefault("claudeAiOauth", {})
    block["accessToken"] = access
    if tok.get("refresh_token"):
        block["refreshToken"] = tok["refresh_token"]
    if tok.get("expires_in"):
        block["expiresAt"] = int(time.time() * 1000) + int(tok["expires_in"]) * 1000
    tmp = CREDENTIALS_FILE.with_suffix(CREDENTIALS_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CREDENTIALS_FILE)
    return block


def _api_usage(token: str) -> dict:
    req = urllib.request.Request(
        USAGE_URL,
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": API_BETA},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_usage_raw() -> dict:
    """Fetch the raw usage JSON from the account API, refreshing the token if needed."""
    oauth = _load_oauth()
    expires_at = oauth.get("expiresAt")
    if isinstance(expires_at, (int, float)) and expires_at <= time.time() * 1000 + 60_000:
        oauth = _refresh_token(oauth)
    try:
        return _api_usage(oauth["accessToken"])
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):  # token rejected — refresh once and retry
            oauth = _refresh_token(oauth)
            return _api_usage(oauth["accessToken"])
        raise


def _pct_str(value) -> str:
    """Round a 0–100 utilization to the widget's 'N%' string, or 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{int(round(float(value)))}%"
    except (TypeError, ValueError):
        return "N/A"


def _limit_percent(data: dict, kind: str):
    for lim in data.get("limits") or []:
        if lim.get("kind") == kind and lim.get("percent") is not None:
            return lim["percent"]
    return None


def _reset_local(iso: str | None) -> str | None:
    """Convert an API 'resets_at' ISO timestamp to a local wall-clock 'HH:MM'."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M")
    except (ValueError, TypeError):
        return None


def parse_usage(data: dict) -> dict:
    """Map the account usage JSON onto the widget's log schema."""
    five_hour = data.get("five_hour") or {}
    seven_day = data.get("seven_day") or {}
    seven_day_sonnet = data.get("seven_day_sonnet") or {}

    session_pct = _limit_percent(data, "session")
    if session_pct is None:
        session_pct = five_hour.get("utilization")
    all_pct = _limit_percent(data, "weekly_all")
    if all_pct is None:
        all_pct = seven_day.get("utilization")
    # "Sonnet only" historically tracked the model-scoped weekly limit; the API
    # now exposes it as a scoped weekly limit (whichever premium model applies).
    scoped_pct = seven_day_sonnet.get("utilization")
    if scoped_pct is None:
        scoped_pct = _limit_percent(data, "weekly_scoped")

    design = _pct_str((data.get("seven_day_cowork") or {}).get("utilization"))
    if design == "N/A":
        design = "0%"

    out = {
        "Current session": _pct_str(session_pct),
        "Weekly All models": _pct_str(all_pct),
        "Weekly Sonnet only": _pct_str(scoped_pct),
        "Weekly Claude Design": design,
        "Session reset": _reset_local(five_hour.get("resets_at")),
        "Weekly reset": _reset_local(seven_day.get("resets_at")),
    }
    tz = _local_tz_name()
    if tz:
        out["Reset tz"] = tz
    return out


def scrape_usage(retries: int = 3) -> dict:
    """Read usage limits from the account API. Retries transient failures.

    Kept the historical name (the widget/on-demand refresh call it) even though
    it no longer scrapes a terminal. Returns the parsed schema, or all-N/A values
    if every attempt fails, so the widget degrades gracefully instead of crashing.
    """
    last_err = None
    for attempt in range(max(1, retries)):
        try:
            data = fetch_usage_raw()
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                DEBUG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return parse_usage(data)
        except Exception as exc:  # network/auth hiccup — retry, then give up cleanly
            last_err = exc
            if attempt < retries - 1:
                time.sleep(3)
    print(f"  usage fetch failed: {last_err}")
    return {
        "Current session": "N/A",
        "Weekly All models": "N/A",
        "Weekly Sonnet only": "N/A",
        "Weekly Claude Design": "0%",
        "Session reset": None,
        "Weekly reset": None,
    }


def read_log() -> list:
    try:
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def append_log(entry: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entries = read_log()
    entries.append(entry)
    LOG_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry_from(values: dict) -> dict:
    now = datetime.now()
    return {"Дата": now.strftime("%d.%m.%Y"), "Время": now.strftime("%-H:%M"), **values}


def _send_notification(title: str, body: str) -> None:
    """Fire a desktop notification via notify-send. No-op if it's unavailable.

    Sets DISPLAY/DBUS_SESSION_BUS_ADDRESS so it also works from cron, where the
    session bus address is otherwise absent and the notification would silently
    go nowhere.
    """
    if not shutil.which("notify-send"):
        return
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")
    cmd = ["notify-send", "-a", "Claude Usage", "-u", "critical"]
    if ICON_FILE.exists():
        cmd += ["-i", str(ICON_FILE)]
    cmd += [title, body]
    try:
        subprocess.run(cmd, env=env, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def _read_notify_state() -> dict:
    try:
        state = json.loads(NOTIFY_STATE_FILE.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_notify_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTIFY_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def notify_if_needed(entry: dict) -> None:
    """Notify when the session limit crosses the threshold (rising edge).

    Re-arms once usage drops back below the threshold, so each session cycle can
    notify once instead of every scrape while above the line.
    """
    cfg = read_config()
    if not cfg.get("notifyEnabled"):
        return
    pct = _pct(entry.get("Current session"))
    if pct is None:
        return
    threshold = cfg["notifyThreshold"]
    state = _read_notify_state()
    already = bool(state.get("sessionNotified"))
    if pct >= threshold:
        if not already:
            reset = entry.get("Session reset")
            body = f"Лимит текущей сессии превысил {threshold}%."
            if reset:
                body += f" Сброс в {reset}."
            _send_notification(f"Claude: сессия {pct}%", body)
            _write_notify_state({**state, "sessionNotified": True})
    elif already:
        _write_notify_state({**state, "sessionNotified": False})


def refresh_usage() -> dict:
    """On-demand scrape (widget button); appends to the log and returns the entry."""
    entry = _entry_from(scrape_usage(retries=3))
    append_log(entry)
    try:
        notify_if_needed(entry)
    except Exception:  # a notify failure must never break the scrape/log
        pass
    return entry


def _time_key(s: str) -> tuple:
    try:
        h, m = s.split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return (0, 0)


def get_usage_latest() -> dict:
    """Latest snapshot plus today's intraday series (for a sparkline)."""
    entries = read_log()
    if not entries:
        return {"latest": None, "series": [], "keys": KEYS}
    today = datetime.now().strftime("%d.%m.%Y")
    series = [e for e in entries if e.get("Дата") == today]
    series.sort(key=lambda e: _time_key(e.get("Время", "")))
    return {"latest": entries[-1], "series": series, "keys": KEYS}


# ---------------------------------------------------------------------------
# Design-shaped views: ring percentages and per-day peak session %.
# ---------------------------------------------------------------------------

def _pct(s) -> int | None:
    if s is None:
        return None
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None


def get_rings() -> dict:
    """Latest limit percentages for the three rings + a freshness label."""
    data = get_usage_latest()
    latest = data.get("latest") or {}
    updated = ((latest.get("Дата") or "") + " · " + (latest.get("Время") or "")).strip(" ·")
    return {
        "session": _pct(latest.get("Current session")),
        "all": _pct(latest.get("Weekly All models")),
        "sonnet": _pct(latest.get("Weekly Sonnet only")),
        "design": _pct(latest.get("Weekly Claude Design")),
        "sessionReset": latest.get("Session reset"),
        "weeklyReset": latest.get("Weekly reset"),
        "resetTz": latest.get("Reset tz"),
        "updated": updated or None,
    }


def get_usage_daily() -> dict:
    """{ 'DD.MM': peak Current-session % } across the whole log."""
    peak: dict[str, int] = {}
    for e in read_log():
        full = e.get("Дата")
        if not full:
            continue
        key = ".".join(full.split(".")[:2])  # DD.MM.YYYY -> DD.MM
        p = _pct(e.get("Current session"))
        if p is None:
            continue
        if key not in peak or p > peak[key]:
            peak[key] = p
    return peak


def main() -> None:
    if not is_business_hours():
        print(f"[{datetime.now():%d.%m.%Y %H:%M}] Outside business hours, skipping.")
        return
    print(f"[{datetime.now():%d.%m.%Y %H:%M}] Fetching usage...")
    entry = refresh_usage()
    print(f"Saved: {entry}")


if __name__ == "__main__":
    main()
