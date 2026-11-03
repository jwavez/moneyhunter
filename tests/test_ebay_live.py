import unittest, datetime as dt
from moneyhunter.comps import Comp
from moneyhunter.scanners import ebay
from moneyhunter import matching as M

def comp(): return Comp("samba og", "trainers", 65, 70, "x", "old 1 Sep 2026", None, "", 10, None, None, dt.date(2026, 9, 1))

class T(unittest.TestCase):
    def test_strict_and_conservative(self):
        items = [{"title": f"Adidas Samba OG UK9 new", "price": p} for p in (60, 62, 64, 66, 68, 90)]
        items += [{"title": "Samba OG kids UK3", "price": 10}, {"title": "Samba OG bundle x2", "price": 5}]
        c = ebay.active_comp(comp(), items, M.check, dt.date(2026, 11, 3))
        self.assertIsNotNone(c); self.assertIsNone(c.sold_90d)
        self.assertLessEqual(c.low, 65); self.assertGreater(c.low, 50)   # kids/bundle rejected
        self.assertEqual(c.as_of, dt.date(2026, 11, 3)); self.assertIn("ACTIVE", c.evidence)
        self.assertLessEqual(c.high, 70); self.assertGreaterEqual(c.high, c.low)
    def test_too_few(self):
        self.assertIsNone(ebay.active_comp(comp(), [{"title": "samba og", "price": 60}] * 4, M.check))
