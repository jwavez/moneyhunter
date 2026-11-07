"""Comps store: sold-price ranges you verify (Terapeak / eBay sold search / PriceCharting).
Each row's date is read from its source ("fetched 2026-11-02" or "6 Oct 2026").
Rows older than C.MAX_COMP_AGE_DAYS are stale: they never produce a BUY or VERIFY grade."""
import csv, os, re, datetime as dt
from dataclasses import dataclass, field
from typing import Optional
from . import matching as M

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "comps.csv")
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}

@dataclass
class Comp:
    match: str; category: str; low: float; high: float; evidence: str; source: str
    floor: Optional[float]; floor_source: str
    sold_90d: Optional[int]; sell_through: Optional[float]; days_to_sell: Optional[float]
    as_of: Optional[dt.date] = None

    evidence_type: str = "legacy_reference"
    identity: dict = field(default_factory=dict)
    floor_as_of: Optional[dt.date] = None
    velocity_as_of: Optional[dt.date] = None
    source_urls: list = field(default_factory=list)
    offers: list = field(default_factory=list)

    def age_days(self, today: dt.date = None) -> Optional[int]:
        return None if self.as_of is None else ((today or dt.date.today()) - self.as_of).days

def _f(x): return float(x) if x not in ("", None) else None

def parse_date(s: str) -> Optional[dt.date]:
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", s or "")
    if m: return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(\d{1,2}) ([A-Za-z]{3})[a-z]* (20\d\d)", s or "")
    if m and m[2].lower() in MONTHS: return dt.date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    return None

def load(path: str = PATH, evidence_path=None) -> list:
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out.append(Comp(r["match"].lower(), r["category"], float(r["low"]), float(r["high"]),
                            r["sold_evidence"], r["source"], _f(r["floor"]), r["floor_source"],
                            int(r["sold_90d"]) if r["sold_90d"] else None, _f(r["sell_through"]), _f(r["days_to_sell"]),
                            parse_date(r.get("as_of") or "") or parse_date(r["source"])))
    # Reviewed evidence is authoritative, but legacy CSV remains reference-only for migration.
    from . import evidence
    if evidence_path is None:
        evidence_path = os.path.join(os.path.dirname(path), "evidence.json")
    reviewed = evidence.load(evidence_path)
    return reviewed + out

def find(title: str, comps: list, extra: str = "") -> Optional[Comp]:
    return M.find(title, comps, extra)[0]

def find_with_reason(title: str, comps: list, extra: str = ""):
    return M.find(title, comps, extra)
