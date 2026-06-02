#!/usr/bin/env python3
"""Desktop widget window (pywebview) showing Claude usage limits and token stats."""

import threading
from pathlib import Path

import webview

import tokens
import usage

WEB_DIR = Path(__file__).resolve().parent / "web"
INDEX = WEB_DIR / "index.html"


class Api:
    def get_token_today(self) -> dict:
        return tokens.get_today()

    def get_token_history(self) -> list:
        return tokens.get_history(30)

    def get_usage_latest(self) -> dict:
        return usage.get_usage_latest()

    def get_usage_history(self) -> dict:
        return usage.get_usage_history()

    def refresh_usage(self) -> dict:
        """Blocking on-demand /usage scrape. Runs off the GUI thread, so the
        frontend can await it while showing a spinner."""
        try:
            usage.refresh_usage()
        except Exception as exc:  # surface scrape failures to the UI
            return {"error": str(exc), **usage.get_usage_latest()}
        return usage.get_usage_latest()


def _seal_history() -> None:
    # Persist completed days to the history store even if the user never opens
    # the History tab, so data survives Claude Code's log rotation.
    try:
        tokens.get_history(1)
    except Exception:
        pass


def main() -> None:
    threading.Thread(target=_seal_history, daemon=True).start()
    webview.create_window(
        "Claude Usage",
        str(INDEX),
        js_api=Api(),
        width=440,
        height=680,
        min_size=(360, 480),
        on_top=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
