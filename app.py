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
    webview.create_window(
        "Claude Usage",
        str(INDEX),
        js_api=Api(),
        width=452,
        height=720,
        min_size=(420, 560),
        on_top=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
