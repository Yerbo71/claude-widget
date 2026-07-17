#!/usr/bin/env python3
"""Desktop widget window (pywebview) showing Claude usage limits and token stats."""

import threading
from pathlib import Path

import webview

import tokens
import usage

WEB_DIR = Path(__file__).resolve().parent / "web"
INDEX = WEB_DIR / "index.html"

WIDTH = 452  # 420px card + 16px body padding on each side
INIT_HEIGHT = 640  # a sensible first paint; the frontend corrects it on boot
MIN_HEIGHT = 200
MAX_HEIGHT = 1600


class Api:
    def __init__(self) -> None:
        self.window = None  # set after the window is created

    def autosize(self, height) -> None:
        """Resize the window to hug the card, so it behaves like a native widget
        instead of a fixed frame. Called by the frontend whenever content height
        changes (tab switch, collapse, data load). Width stays fixed."""
        win = self.window
        if win is None:
            return
        try:
            h = max(MIN_HEIGHT, min(MAX_HEIGHT, int(round(float(height)))))
        except (TypeError, ValueError):
            return
        try:
            win.resize(WIDTH, h)
        except Exception:
            pass

    def get_rings(self) -> dict:
        return usage.get_rings()

    def get_tokens(self, period: str = "day") -> dict:
        return tokens.get_tokens(period)

    def get_history_data(self, span: int = 14) -> list:
        """Per-day token series with the matching peak session % attached."""
        daily = usage.get_usage_daily()
        rows = tokens.get_series(int(span))
        for r in rows:
            r["limit"] = daily.get(r["d"])
        return rows

    def refresh_usage(self) -> dict:
        """Blocking on-demand /usage scrape. Runs off the GUI thread, so the
        frontend can await it while showing a spinner. Returns fresh rings."""
        try:
            usage.refresh_usage()
        except Exception as exc:  # surface scrape failures to the UI
            return {"error": str(exc), **usage.get_rings()}
        return usage.get_rings()

    def get_settings(self) -> dict:
        return usage.read_config()

    def set_settings(self, cfg: dict) -> dict:
        return usage.write_config(cfg)


def _seal_history() -> None:
    # Persist completed days to the history store even if the user never opens
    # the History tab, so data survives Claude Code's log rotation.
    try:
        tokens.get_history(1)
    except Exception:
        pass


def main() -> None:
    threading.Thread(target=_seal_history, daemon=True).start()
    api = Api()
    api.window = webview.create_window(
        "Claude Usage",
        str(INDEX),
        js_api=api,
        width=WIDTH,
        height=INIT_HEIGHT,
        min_size=(WIDTH, MIN_HEIGHT),
        on_top=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
