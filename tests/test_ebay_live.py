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

class Filters(unittest.TestCase):
    def C(self, m, cat, lo=10, hi=20): return Comp(m, cat, lo, hi, "x", "s", None, "", None, None, None, None)
    def test_kids_decimal_size(self):
        c = self.C("samba og", "trainers")
        self.assertIn("kids", M.check("adidas Samba OG Black Trainers UK 4.5 US 5", "", c))
        self.assertIn("kids", M.check("Adidas Samba OG - U.K. 3.5 - NEW", "", c))
        self.assertEqual(M.check("adidas Samba OG Trainers UK 9.5", "", c), "")
    def test_lego(self):
        c = self.C("76449", "lego")
        self.assertEqual(M.check("LEGO Harry Potter 76449 Chomping Monster Book 518pcs NEW", "", c), "")
        self.assertNotEqual(M.check("FRIDGE MAGNET - Graford, 76449", "", c), "")
        self.assertNotEqual(M.check("519Pcs Harry Potter Book Of Monsters 76449 Building Blocks", "", c), "")
        self.assertNotEqual(M.check("LEGO Harry Potter Sets 76449 and 76424 Sealed", "", c), "")
        self.assertNotEqual(M.check("LEGO 76449 Book of Monsters - Box Damage", "", c), "")
    def test_tools(self):
        c = self.C("dcd796", "tools")
        self.assertEqual(M.check("DEWALT DCD796N 18V XR BL Cordless Combi Drill (Body Only)", "", c), "")
        for bad in ("DEWALT n438603 CHUCK & GEARBOX FOR A DCD796", "Dewalt DCD796 Cordless Brushless Drill 2000RPM Impact Driver Power Tool",
                    "NEW 20V Dewalt DCD796 Compact Cordless", "Dewalt DCK266 18v Brushless DCD796 Combi Drill DCF887",
                    "DeWALT DCD796 BARE UNIT + DT70712 MIXED BIT SET", "Dewalt DCD796N Combi Drill With Tool Bag"):
            self.assertNotEqual(M.check(bad, "", c), "", bad)
    def test_outliers(self):
        items = [{"title": "Adidas Samba OG UK9", "price": p} for p in (20, 60, 62, 64, 66, 68, 200)]
        c = ebay.active_comp(comp(), items, M.check, dt.date(2026, 11, 3))
        self.assertIn("5 matched", c.evidence)
