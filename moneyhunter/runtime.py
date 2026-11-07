"""Public operational state only; no ledger, credentials or personal bankroll."""
import datetime as dt
import hashlib
import json
from pathlib import Path
from .evidence import atomic_write
from . import config as C

def now(): return dt.datetime.now(dt.timezone.utc)
def stamp(value): return value.isoformat(timespec="seconds")
def key(raw): return hashlib.sha256(raw["url"].split("?")[0].encode()).hexdigest()[:24]

def load(path):
    if not Path(path).exists(): return {"schema_version": 1, "items": {}, "ask_cache": {}}
    with open(path) as f: state = json.load(f)
    if not isinstance(state, dict) or state.get("schema_version") != 1 or not isinstance(state.get("items"), dict) or not isinstance(state.get("ask_cache"), dict):
        raise ValueError("invalid scan state; refusing to overwrite")
    return state

def observe(raws, state, when=None):
    when = when or now(); ts = stamp(when)
    counts = {"new": 0, "rescanned": 0, "price_changed": 0}
    for raw in raws:
        k = key(raw); old = state["items"].get(k)
        counts["rescanned" if old else "new"] += 1
        if old and old.get("price") != raw["price"]: counts["price_changed"] += 1
        state["items"][k] = {"first_seen": old.get("first_seen", ts) if old else ts, "last_seen": ts,
                              "price": raw["price"], "observations": (old.get("observations", 0) if old else 0) + 1}
    last = state.get("last_success")
    counts["previous_success"] = last
    counts["gap_minutes"] = round((when-dt.datetime.fromisoformat(last)).total_seconds()/60, 1) if last else None
    cutoff = stamp(when-dt.timedelta(days=45))
    state["items"] = {k:v for k,v in state["items"].items() if v.get("last_seen", "") >= cutoff}
    state["last_attempt"] = ts
    return counts

def save(path, state): atomic_write(path, state)
