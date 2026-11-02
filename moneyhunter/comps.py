"""Comps store: sold-price ranges you verify (Terapeak / eBay sold search).
Seeded only with sourced ranges. Add rows as you check items; fill floor (CeX cash
price checked same day), sold_90d, sell_through and days_to_sell to unlock A grades."""
import csv, os
from dataclasses import dataclass
from typing import Optional

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "comps.csv")

@dataclass
class Comp:
    match: str; category: str; low: float; high: float; evidence: str; source: str
    floor: Optional[float]; floor_source: str
    sold_90d: Optional[int]; sell_through: Optional[float]; days_to_sell: Optional[float]

def _f(x): return float(x) if x not in ("", None) else None

def load(path: str = PATH) -> list:
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out.append(Comp(r["match"].lower(), r["category"], float(r["low"]), float(r["high"]),
                            r["sold_evidence"], r["source"], _f(r["floor"]), r["floor_source"],
                            int(r["sold_90d"]) if r["sold_90d"] else None, _f(r["sell_through"]), _f(r["days_to_sell"])))
    return out

def find(title: str, comps: list) -> Optional[Comp]:
    t = title.lower()
    best = None
    for c in comps:
        if c.category == "gaming" and "oled" not in c.match and any(k in t for k in ("console", "oled", "bundle")):
            continue  # a game comp must not price a console bundle
        if all(w in t for w in c.match.split()):
            if best is None or len(c.match) > len(best.match):
                best = c
    return best
