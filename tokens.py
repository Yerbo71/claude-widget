#!/usr/bin/env python3
"""Parse Claude Code session logs into token stats bucketed by a 09:00-anchored day."""

import glob
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
DATA_DIR = Path.home() / ".claude-widget"
HISTORY_FILE = DATA_DIR / "token_history.json"
RESET_HOUR = 9
RECENT_HOURS = 36  # files older than this can't contain the current bucket
SKIP_MODELS = {"<synthetic>"}  # local/synthetic messages carry no real token usage

# path -> (mtime, size, [records]); avoids re-reading unchanged files.
_FILE_CACHE: dict[str, tuple[float, int, list[dict]]] = {}


def _local_tz():
    return datetime.now().astimezone().tzinfo


def logical_day(ts_utc: datetime):
    """Map an aware UTC timestamp to its 09:00->09:00 local-day bucket date."""
    local = ts_utc.astimezone(_local_tz())
    return (local - timedelta(hours=RESET_HOUR)).date()


def current_logical_day() -> str:
    return logical_day(datetime.now(timezone.utc)).isoformat()


def _parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _iter_jsonl_files():
    if not PROJECTS_DIR.exists():
        return []
    return [Path(p) for p in glob.glob(str(PROJECTS_DIR / "**" / "*.jsonl"), recursive=True)]


def _parse_file(path: Path) -> list[dict]:
    """Read one .jsonl, returning records deduped within the file by message id."""
    records: dict[str, dict] = {}
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") != "assistant":
                    continue
                msg = e.get("message") or {}
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                model = msg.get("model") or "unknown"
                if model in SKIP_MODELS:
                    continue
                mid = msg.get("id") or e.get("requestId") or e.get("uuid")
                if not mid:
                    continue
                ts = _parse_ts(e.get("timestamp"))
                if ts is None:
                    continue
                records[mid] = {
                    "id": mid,
                    "day": logical_day(ts).isoformat(),
                    "model": model,
                    "input": int(usage.get("input_tokens") or 0),
                    "output": int(usage.get("output_tokens") or 0),
                    "cache_read": int(usage.get("cache_read_input_tokens") or 0),
                    "cache_creation": int(usage.get("cache_creation_input_tokens") or 0),
                }
    except OSError:
        return []
    return list(records.values())


def _get_records(path: Path) -> list[dict]:
    try:
        st = path.stat()
    except OSError:
        return []
    key = str(path)
    cached = _FILE_CACHE.get(key)
    if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2]
    recs = _parse_file(path)
    _FILE_CACHE[key] = (st.st_mtime, st.st_size, recs)
    return recs


def _empty_day(day: str) -> dict:
    return {
        "day": day,
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "total": 0,
        "narrow": 0,
        "messages": 0,
        "byModel": {},
    }


def _add(day: dict, r: dict) -> None:
    for k in ("input", "output", "cache_read", "cache_creation"):
        day[k] += r[k]
    total = r["input"] + r["output"] + r["cache_read"] + r["cache_creation"]
    day["total"] += total
    day["narrow"] += r["input"] + r["output"]
    day["messages"] += 1
    m = day["byModel"].setdefault(
        r["model"],
        {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "total": 0, "messages": 0},
    )
    for k in ("input", "output", "cache_read", "cache_creation"):
        m[k] += r[k]
    m["total"] += total
    m["messages"] += 1


def _aggregate(only_recent_hours=None) -> dict:
    seen: set[str] = set()
    days: dict[str, dict] = {}
    cutoff = None
    if only_recent_hours is not None:
        cutoff = datetime.now().timestamp() - only_recent_hours * 3600
    for path in _iter_jsonl_files():
        if cutoff is not None:
            try:
                if path.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
        for r in _get_records(path):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            d = days.setdefault(r["day"], _empty_day(r["day"]))
            _add(d, r)
    return days


def _load_store() -> dict:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_store(store: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_today() -> dict:
    """Fast: token totals for the current 09:00-anchored bucket only."""
    today = current_logical_day()
    days = _aggregate(only_recent_hours=RECENT_HOURS)
    return days.get(today) or _empty_day(today)


def get_history(limit: int = 30) -> list[dict]:
    """Past buckets, newest first.

    Claude Code rotates old .jsonl files away, so completed days are sealed into
    a persistent store. Days still present in the logs overwrite the stored copy
    (more accurate), then the store is saved so history survives log rotation.
    """
    today = current_logical_day()
    days = _aggregate()
    store = _load_store()
    for day, d in days.items():
        if day != today:  # only seal completed days
            store[day] = d
    _save_store(store)
    past = [d for day, d in store.items() if day != today]
    past.sort(key=lambda d: d["day"], reverse=True)
    return past[:limit]


# ---------------------------------------------------------------------------
# Design-shaped views: effective input, prettified model names, period totals.
# ---------------------------------------------------------------------------

_FAMILY_COLOR = {"opus": "var(--opus)", "sonnet": "var(--sonnet)", "haiku": "var(--haiku)"}
_PALETTE = ["#5B8DEF", "#E0B450", "#A979E0", "#56B6C2", "#C9614B"]


def _eff_in(d: dict) -> int:
    """Effective input: the prompt lives in the cache fields, raw input is tiny."""
    return d["input"] + d["cache_read"] + d["cache_creation"]


def _family(model: str) -> str:
    low = model.lower()
    for fam in ("opus", "sonnet", "haiku"):
        if fam in low:
            return fam
    return ""


def _pretty_name(model: str) -> str:
    name = re.sub(r"^claude-", "", model)
    name = re.sub(r"-\d{8}$", "", name)  # drop trailing yyyymmdd build stamp
    parts = [p for p in name.split("-") if p]
    if not parts:
        return model
    family = parts[0].capitalize()
    version = ".".join(parts[1:])
    return f"Claude {family}" + (f" {version}" if version else "")


def model_meta(model: str) -> dict:
    fam = _family(model)
    if fam:
        return {"key": fam, "name": _pretty_name(model), "color": _FAMILY_COLOR[fam]}
    idx = sum(ord(c) for c in model) % len(_PALETTE)
    return {"key": model, "name": _pretty_name(model), "color": _PALETTE[idx]}


def _merge_days(day_dicts: list[dict]) -> dict:
    out = _empty_day("")
    for d in day_dicts:
        for k in ("input", "output", "cache_read", "cache_creation", "total", "narrow", "messages"):
            out[k] += d.get(k, 0)
        for model, m in (d.get("byModel") or {}).items():
            dst = out["byModel"].setdefault(
                model,
                {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "total": 0, "messages": 0},
            )
            for k in ("input", "output", "cache_read", "cache_creation", "total", "messages"):
                dst[k] += m.get(k, 0)
    return out


def _recent_logical_days(n: int) -> list[str]:
    today = logical_day(datetime.now(timezone.utc))
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


def _design_tokens(d: dict, period: str) -> dict:
    models = []
    for model, m in (d.get("byModel") or {}).items():
        meta = model_meta(model)
        m_cache = m["cache_read"] + m["cache_creation"]
        models.append(
            {
                "key": meta["key"],
                "name": meta["name"],
                "color": meta["color"],
                "in": m["input"],
                "cache": m_cache,
                "out": m["output"],
                "req": m["messages"],
                "total": m["input"] + m_cache + m["output"],
            }
        )
    models.sort(key=lambda x: x["total"], reverse=True)
    cache = d["cache_read"] + d["cache_creation"]
    return {
        "period": period,
        "in": d["input"],
        "cache": cache,
        "out": d["output"],
        "total": d["input"] + cache + d["output"],
        "messages": d["messages"],
        "models": models,
    }


def get_tokens(period: str = "day") -> dict:
    """Token totals shaped for the widget: period sums + per-model breakdown."""
    if period == "week":
        days = _aggregate(only_recent_hours=180)
        wanted = set(_recent_logical_days(7))
        merged = _merge_days([d for k, d in days.items() if k in wanted])
        return _design_tokens(merged, "week")
    return _design_tokens(get_today(), "day")


def get_series(limit: int = 14) -> list[dict]:
    """Per-day in/out series (ascending) for the history chart, with DD.MM labels."""
    today_day = current_logical_day()
    days = dict(_load_store())
    for k, d in _aggregate(only_recent_hours=180).items():
        days[k] = d  # logs are more accurate than the sealed store
    days[today_day] = get_today()

    out = []
    for k in sorted(days.keys())[-limit:]:
        d = days[k]
        try:
            label = date.fromisoformat(k).strftime("%d.%m")
        except ValueError:
            label = k
        eff_in = _eff_in(d)
        out.append({"date": k, "d": label, "in": eff_in, "out": d["output"], "total": eff_in + d["output"]})
    return out


if __name__ == "__main__":
    import pprint
    print("current logical day:", current_logical_day())
    print("\n== TODAY ==")
    pprint.pprint(get_today())
    print("\n== HISTORY (5) ==")
    for d in get_history(5):
        print(d["day"], "total=", d["total"], "in=", d["input"], "out=", d["output"],
              "models=", list(d["byModel"]))
    print("\n== TOKENS day ==")
    pprint.pprint(get_tokens("day"))
    print("\n== TOKENS week ==")
    pprint.pprint(get_tokens("week"))
    print("\n== SERIES (7) ==")
    for s in get_series(7):
        print(s["d"], "in=", s["in"], "out=", s["out"], "total=", s["total"])
