"""Worked examples for fees, matching, grading and display consistency."""
import datetime as dt, unittest
from moneyhunter import fees as F, grading as G, matching as M, comps as CP, embeds as E, config as C, intel as I

def comp(match, cat, low=65, high=70, age=1, sold=None):
    return CP.Comp(match, cat, low, high, "e", "s", None, "", sold, None, None, dt.date.today() - dt.timedelta(days=age))

class Fees(unittest.TestCase):
    def test_bpf_worked_examples(self):   # eBay help 5595 examples
        self.assertEqual(F.ebay_buyer_protection(5), 0.45)
        self.assertEqual(F.ebay_buyer_protection(20), 1.50)
        self.assertEqual(F.ebay_buyer_protection(100), 4.70)   # 0.10 + 1.40 + 3.20
    def test_private_list_price_inverts_bpf(self):
        lp = F.private_list_price(104.70); self.assertAlmostEqual(lp, 100.0, delta=0.01)
    def test_business_fee_trainers_65(self):
        # 11.9% of £65 = 7.735, + £0.40 per order, + 0.35% regulatory = 0.2275 -> £8.36
        self.assertEqual(F.ebay_business_fee(65, "trainers"), 8.36)
    def test_depop_paypal(self):
        self.assertEqual(F.platform_fee("depop", 40), 1.46)      # 2.9% + 30p
        self.assertEqual(F.platform_fee("fb", 40), 1.46)         # PayPal G&S 2.9% + 30p
        self.assertEqual(F.platform_fee("fb_cash", 40), 0.0)
        self.assertEqual(F.platform_fee("vinted", 40), 0.0)
    def test_net_worked_example(self):
        # sell £65 trainers, buy £30: fee 8.36, post 3.52, pack 0.50, returns 1.95 -> 20.67
        b = F.net_profit(65, 30, "ebay_business", "trainers", C.postage_for("trainers"), C.PACKAGING, C.RETURNS_ALLOWANCE)
        self.assertEqual(b.net, 20.67)
    def test_vinted_buyer_pays_postage(self):
        b = F.net_profit(40, 20, "vinted", "trainers", 3.52, 0.5, 0.03); self.assertEqual(b.postage, 0.0)

class Matching(unittest.TestCase):
    def setUp(self):
        self.c = [comp("samba og", "trainers"), comp("dcd796", "tools"), comp("mario kart 8 deluxe", "gaming", 24, 26),
                  comp("elden ring ps5", "gaming", 17, 19), comp("76449", "lego", 28, 35), comp("sauvage 100ml", "fragrance", 60, 70)]
    def ok(self, t, desc=""): return M.find(t, self.c, desc)[0] is not None
    def test_adult_matches(self): self.assertTrue(self.ok("adidas Samba OG Trainers - White"))
    def test_kids_rejected(self):
        for t in ["Girls Samba OG Trainers - Black", "Samba OG Junior", "Kids adidas Samba OG", "Samba OG Trainers UK 3"]:
            self.assertFalse(self.ok(t), t)
        self.assertFalse(self.ok("Samba OG Trainers - Black", "Available in sizes 10 younger - 2 older"))
    def test_bundle_multipack_preorder_used(self):
        for t in ["Mario Kart 8 Deluxe bundle", "2 x Mario Kart 8 Deluxe", "Mario Kart 8 Deluxe - Pre Order",
                  "Mario Kart 8 Deluxe (Pre-owned)", "Elden Ring PS5 Grade A refurbished"]:
            self.assertFalse(self.ok(t), t)
    def test_editions_platforms(self):
        self.assertTrue(self.ok("Mario Kart 8 Deluxe (Nintendo Switch)"))
        self.assertFalse(self.ok("Mario Kart 8 Deluxe Nintendo Switch 2 Edition"))
        self.assertFalse(self.ok("Elden Ring Shadow of the Erdtree Deluxe Edition PS5"))
        self.assertFalse(self.ok("Elden Ring PS4"))
    def test_tools_body_only(self):
        self.assertTrue(self.ok("DeWalt DCD796N 18V Combi Drill Body Only"))
        self.assertFalse(self.ok("DeWalt DCD796P2 Combi Drill Kit 2 x 5Ah Batteries"))
    def test_fragrance_ml(self):
        self.assertTrue(self.ok("Dior Sauvage EDT 100ml"))
        self.assertFalse(self.ok("Dior Sauvage EDT 60ml"))
        self.assertFalse(self.ok("Dior Sauvage EDT"))
    def test_word_boundaries(self): self.assertFalse(self.ok("Samba dog toy OGX"))

class Grading(unittest.TestCase):
    def deal(self, **k):
        base = dict(title="Samba OG", url="u", buy_price=32.5, category="trainers", source="t", target=65, stretch=70, comp_age_days=2)
        base.update(k); return G.Deal(**base)
    def test_worst_includes_fees_when_floor_unverified(self):
        r = G.grade(self.deal(), 200)
        # floor est = £32.50 sold on eBay: fee 4.60 + post 3.52 + pack 0.50 + returns 0.98 -> −£9.60, not £0.00
        self.assertLess(r.worst, 0); self.assertFalse(r.worst_verified)
        self.assertIn("(est.)", E.worst_text(r))
    def test_stale_comps_never_verify(self):
        r = G.grade(self.deal(buy_price=25, comp_age_days=45), 200); self.assertEqual(r.grade, "REJECT")
        self.assertIn("Sold prices older than 30 days", E.gates_failed(r))
    def test_unknown_age_is_stale(self):
        self.assertEqual(G.grade(self.deal(buy_price=25, comp_age_days=None), 200).grade, "REJECT")
    def test_a_needs_min_comps(self):
        d = self.deal(buy_price=30, floor=34, floor_verified=True, sold_90d=4, sell_through=120, days_to_sell=5)
        self.assertNotEqual(G.grade(d, 200).grade[0], "A")
        d.sold_90d = 20; self.assertEqual(G.grade(d, 200).grade[0], "A")
    def test_days_to_sell_display(self):
        self.assertEqual(E.dts_text(None), "No data yet")
        r = G.grade(self.deal(), 200)
        self.assertIn("house rule", E.exit_text(r.plan, r.worst_verified))
        self.assertIn("not verified", E.exit_text(r.plan, r.worst_verified))
    def test_max_buy_round_down_and_consistent(self):
        r = G.grade(self.deal(), 200); mb = E.max_buy(r)
        r2 = G.grade(self.deal(buy_price=mb), 200)
        self.assertGreaterEqual(r2.ev_net + 1e-9, E.COMMUNITY_MIN_NET - 0.01)

class Intel(unittest.TestCase):
    def test_retailer(self):
        self.assertEqual(I.retailer("Argos")["rating"], "trusted")
        self.assertEqual(I.retailer("eBay")["rating"], "caution")
    def test_fake(self):
        self.assertEqual(I.fake_risk("trainers", "Unknown Shop")["level"], "high")
        self.assertEqual(I.fake_risk("lego", "Argos")["level"], "low")

class CompsFile(unittest.TestCase):
    def test_every_comp_has_a_date(self):
        for c in CP.load(): self.assertIsNotNone(c.as_of, c.match)



class Hub(unittest.TestCase):
    def test_trending_filter(self):
        from moneyhunter import hub
        bad = [("Kikkoman Soy Sauce 1 Litre", "other"), ("LEGO Star Wars Skywalker Saga - PC Game Steam", "lego"),
               ("Fairy Dishwasher Tablets 130", "other"), ("Equalizer 4K - To Buy Prime Video", "gaming")]
        for t, c in bad: self.assertFalse(hub.resellable({"title": t, "category": c}), t)
        self.assertTrue(hub.resellable({"title": "LEGO 76449 Hogwarts", "category": "lego"}))
    def test_sell_needed(self):
        from moneyhunter import hub, fees as F
        be, tgt, post = hub.sell_needed(48, "trainers")
        n = lambda p: F.net_profit(p, 48, "ebay_business", "trainers", post, 0.5, 0.03).net
        self.assertGreaterEqual(n(be), 0); self.assertLess(n(be - 0.05), 0)
        self.assertGreaterEqual(n(tgt), 48 * 0.40)
if __name__ == "__main__": unittest.main()
