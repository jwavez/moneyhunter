import unittest
from moneyhunter.fees import platform_fee, ebay_business_fee
from moneyhunter import grading as G, benefits as B

class T(unittest.TestCase):
    def test_fees(self):
        self.assertEqual(platform_fee("vinted", 50), 0.0)
        self.assertEqual(platform_fee("depop", 50), round(50*0.029+0.30, 2))
        self.assertAlmostEqual(ebay_business_fee(50, "sportswear"), round(50*0.119+0.40+50*0.0035, 2))
        self.assertAlmostEqual(ebay_business_fee(120, "trainers"), round(120*0.07+0.40+120*0.0035, 2))
        self.assertAlmostEqual(ebay_business_fee(800, "tools"), round(750*0.069+50*0.03+0.40+800*0.0035, 2))
    def test_grade_a(self):
        d = G.Deal("Samba OG", "u", 30, "trainers", "t", target=65, stretch=70, floor=32, floor_verified=True, sold_90d=20, sell_through=120, days_to_sell=5, comp_age_days=1)
        r = G.grade(d, 200); self.assertTrue(r.grade.startswith("A"), r.reasons)
    def test_reject_low_profit(self):
        d = G.Deal("x", "u", 60, "trainers", "t", target=65, stretch=70)
        self.assertEqual(G.grade(d, 200).grade, "REJECT")
    def test_capital(self):
        self.assertEqual(B.capital_effect(5000)["monthly_reduction"], 0.0)
        self.assertEqual(B.capital_effect(6300)["monthly_reduction"], 8.70)   # gov.uk worked example
        self.assertIsNone(B.capital_effect(16001)["monthly_reduction"])
    def test_uc_mif(self):
        r = B.uc_period(500, 400, mif=1000, start_up=False); self.assertEqual(r["earnings_counted"], 1000)
        r = B.uc_period(300, 500); self.assertEqual(r["loss_carried_forward"], 200)

if __name__ == "__main__": unittest.main()
