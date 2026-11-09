"""Alert seen-list with optional last_delivered_price (Task 17).

Legacy seen.json is a flat list of key strings. New writes may use schema_version 2:
  {"schema_version": 2, "keys": [...], "last_delivered_price": {key: float}}
Existing string entries are never mass-migrated with fabricated prices.
"""
from __future__ import annotations
import json
from pathlib import Path
from .evidence import atomic_write

PRICE_CHANGE_THRESHOLD = 0.10


def decide_watch(*, key_in_seen: bool, last_delivered_price, current_price, priced: bool):
    """Pure decision for WATCH / priced-card seen suppression (Task 17)."""
    if not priced:
        return {
            "would_deliver": False,
            "reason": "unpriced_always_suppressed",
            "record_price": False,
            "is_repost": False,
            "pct_change": None,
        }
    try:
        cur = float(current_price)
    except (TypeError, ValueError):
        return {
            "would_deliver": False,
            "reason": "invalid_current_price",
            "record_price": False,
            "is_repost": False,
            "pct_change": None,
        }
    if not key_in_seen:
        return {
            "would_deliver": True,
            "reason": "first_delivery",
            "record_price": True,
            "is_repost": False,
            "pct_change": None,
        }
    if last_delivered_price is None:
        return {
            "would_deliver": False,
            "reason": "no_baseline_suppress_and_record",
            "record_price": True,
            "is_repost": False,
            "pct_change": None,
        }
    try:
        last = float(last_delivered_price)
    except (TypeError, ValueError):
        return {
            "would_deliver": False,
            "reason": "no_baseline_suppress_and_record",
            "record_price": True,
            "is_repost": False,
            "pct_change": None,
        }
    if not (last > 0) or cur < 0:
        return {
            "would_deliver": False,
            "reason": "invalid_baseline",
            "record_price": True,
            "is_repost": False,
            "pct_change": None,
        }
    pct = abs(cur - last) / last
    if pct >= PRICE_CHANGE_THRESHOLD:
        return {
            "would_deliver": True,
            "reason": "price_change_ge_10pct",
            "record_price": True,
            "is_repost": True,
            "pct_change": pct,
        }
    return {
        "would_deliver": False,
        "reason": "price_change_under_10pct",
        "record_price": False,
        "is_repost": False,
        "pct_change": pct,
    }


class SeenState:
    """Set-like membership for alert keys plus optional last_delivered_price map."""

    def __init__(self, keys=None, prices=None):
        self._keys = set(keys or [])
        self._prices = {}
        for k, v in (prices or {}).items():
            try:
                self._prices[k] = float(v)
            except (TypeError, ValueError):
                continue

    def __contains__(self, key):
        return key in self._keys

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def __or__(self, other):
        keys = set(self._keys) | set(other)
        return SeenState(keys, self._prices)

    def add(self, key):
        self._keys.add(key)

    def last_delivered_price(self, key):
        return self._prices.get(key)

    def record_price(self, key, price):
        self._keys.add(key)
        self._prices[key] = float(price)

    def decide(self, key, current_price, *, priced: bool):
        return decide_watch(
            key_in_seen=key in self._keys,
            last_delivered_price=self._prices.get(key),
            current_price=current_price,
            priced=priced,
        )

    def to_json(self):
        """Serialize. Use v2 whenever any price baseline exists; else legacy list."""
        keys = sorted(self._keys)
        if not self._prices:
            return keys
        prices = {k: self._prices[k] for k in keys if k in self._prices}
        return {
            "schema_version": 2,
            "keys": keys,
            "last_delivered_price": prices,
        }

    def save(self, path):
        atomic_write(path, self.to_json())

    @classmethod
    def load(cls, path):
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text())
        return cls.from_json(data)

    @classmethod
    def from_json(cls, data):
        if isinstance(data, list):
            if not all(isinstance(k, str) for k in data):
                raise ValueError("invalid alert state")
            return cls(data, {})
        if isinstance(data, dict) and data.get("schema_version") == 2:
            keys = data.get("keys") or []
            prices = data.get("last_delivered_price") or {}
            if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
                raise ValueError("invalid alert state keys")
            if not isinstance(prices, dict):
                raise ValueError("invalid alert state prices")
            return cls(keys, prices)
        raise ValueError("invalid alert state")


def coerce_seen(seen):
    if isinstance(seen, SeenState):
        return seen
    if isinstance(seen, set):
        return SeenState(seen, {})
    if isinstance(seen, list):
        return SeenState.from_json(seen)
    if seen is None:
        return SeenState()
    raise TypeError(f"unsupported seen type: {type(seen)!r}")
