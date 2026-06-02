#!/usr/bin/env python3
"""Scrape Claude Code /usage limits via PTY and expose them to the widget.

Run directly (cron) to append a snapshot during business hours. Import to read
the log or trigger an on-demand refresh from the widget's "Refresh" button.
"""

import fcntl
import json
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import termios
import time
from datetime import datetime
from pathlib import Path

LOG_FILE = Path.home() / "claude_usage_log.json"
DEBUG_FILE = Path.home() / "claude_usage_debug.txt"

KEYS = ["Current session", "Weekly All models", "Weekly Sonnet only", "Weekly Claude Design"]


def claude_bin() -> str:
    candidate = Path.home() / ".local" / "bin" / "claude"
    if candidate.exists():
        return str(candidate)
    return shutil.which("claude") or str(candidate)


def is_business_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.hour < 9:
        return False
    if now.hour > 18 or (now.hour == 18 and now.minute > 0):
        return False
    return True


def _set_pty_size(fd: int, rows: int = 24, cols: int = 220) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _read_for(fd: int, seconds: float) -> bytes:
    out = b""
    deadline = time.time() + seconds
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                out += os.read(fd, 4096)
            except OSError:
                break
    return out


def _strip_ansi(raw: bytes) -> str:
    clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw.decode("utf-8", errors="ignore"))
    clean = re.sub(r"\x1b[>=78]", "", clean)
    clean = re.sub(r"\x1b\][^\x07]*\x07", "", clean)
    return clean


def _try_capture() -> str:
    master, slave = pty.openpty()
    _set_pty_size(master)
    _set_pty_size(slave)

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["HOME"] = str(Path.home())
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", str(Path.home() / ".Xauthority"))

    proc = subprocess.Popen(
        [claude_bin()],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
        env=env,
    )

    try:
        startup_out = b""
        for _ in range(20):  # up to 10s for the TUI to render and go idle
            chunk = _read_for(master, 0.5)
            startup_out += chunk
            if startup_out and not chunk:
                break

        if proc.poll() is not None:
            return f"[PROC EXITED early]\n{_strip_ansi(startup_out)}"

        startup_clean = _strip_ansi(startup_out)

        if "trust" in startup_clean.lower():
            os.write(master, b"1\r")
            time.sleep(3)
            _read_for(master, 3)

        if "Tips" in startup_clean or "What" in startup_clean or "getting started" in startup_clean.lower():
            os.write(master, b"\x1b")
            time.sleep(0.5)
            _read_for(master, 0.5)

        os.write(master, b"/usage\r")

        output = b""
        deadline = time.time() + 20
        while time.time() < deadline:
            output += _read_for(master, 1)
            if b"used" in output and b"week" in output.lower():
                time.sleep(1)
                output += _read_for(master, 2)
                break
    finally:
        try:
            os.write(master, b"/exit\r")
            time.sleep(0.5)
        except OSError:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master)
        os.close(slave)

    return _strip_ansi(output)


def _parse_percent(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return m.group(1) + "%" if m else "N/A"


def parse_usage(raw: str) -> dict:
    design = _parse_percent(raw, r"Claude\s*Design[^%]*?(\d+)\s*%\s*used")
    if design == "N/A":
        design = "0%"
    return {
        "Current session": _parse_percent(raw, r"Curre[a-z]*\s*session[^%]*?(\d+)\s*%\s*used"),
        "Weekly All models": _parse_percent(raw, r"all\s*models[^%]*?(\d+)\s*%\s*used"),
        "Weekly Sonnet only": _parse_percent(raw, r"Sonnet\s*only[^%]*?(\d+)\s*%\s*used"),
        "Weekly Claude Design": design,
    }


def scrape_usage(retries: int = 3) -> dict:
    """Spawn Claude, read /usage, return parsed percentages. Costs session quota."""
    raw = ""
    for attempt in range(retries):
        raw = _try_capture()
        try:
            DEBUG_FILE.write_text(raw, encoding="utf-8")
        except OSError:
            pass
        if "used" in raw and "week" in raw.lower():
            break
        time.sleep(5)
    return parse_usage(raw)


def read_log() -> list:
    try:
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def append_log(entry: dict) -> None:
    entries = read_log()
    entries.append(entry)
    LOG_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry_from(values: dict) -> dict:
    now = datetime.now()
    return {"Дата": now.strftime("%d.%m.%Y"), "Время": now.strftime("%-H:%M"), **values}


def refresh_usage() -> dict:
    """On-demand scrape (widget button); appends to the log and returns the entry."""
    entry = _entry_from(scrape_usage(retries=3))
    append_log(entry)
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


def get_usage_history() -> dict:
    """Per-day latest snapshot, newest day first."""
    by_day: dict[str, dict] = {}
    for e in read_log():
        day = e.get("Дата")
        if not day:
            continue
        prev = by_day.get(day)
        if prev is None or _time_key(e.get("Время", "")) >= _time_key(prev.get("Время", "")):
            by_day[day] = e

    def day_key(d: str) -> tuple:
        try:
            dd, mm, yy = d.split(".")
            return (int(yy), int(mm), int(dd))
        except (ValueError, AttributeError):
            return (0, 0, 0)

    rows = sorted(by_day.values(), key=lambda e: day_key(e.get("Дата", "")), reverse=True)
    return {"rows": rows, "keys": KEYS}


def main() -> None:
    if not is_business_hours():
        print(f"[{datetime.now():%d.%m.%Y %H:%M}] Outside business hours, skipping.")
        return
    print(f"[{datetime.now():%d.%m.%Y %H:%M}] Capturing /usage...")
    entry = refresh_usage()
    print(f"Saved: {entry}")


if __name__ == "__main__":
    main()
