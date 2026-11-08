"""Synthetic fixtures only: none of these observations are real market evidence.
All network and delivery are mocked/disabled. No test sends a Discord message.
"""
import contextlib
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from moneyhunter import cli, comps, config, discord, embeds, evidence, grading, hub, runtime, tier_sync
from moneyhunter.scanners import ebay, hotukdeals

TODAY = dt.date.today()

def record():
    identity = {"condition": "new", "variant": "white", "sku": "synthetic-99", "size": "9", "gender": "men"}
    obs = [{"url": f"https://www.ebay.co.uk/itm/synthetic-fixture-{i}", "sold_at": TODAY.isoformat(),
            "listed_at": (TODAY-dt.timedelta(days=3)).isoformat(), "price": 65+i, "currency": "GBP",
            "kind": "sold", "identity": identity.copy()} for i in range(5)]
    return {"id": "synthetic-test-only", "match": "synthetic trainers", "category": "trainers", "identity": identity,
            "reviewed": True, "reviewed_at": TODAY.isoformat(), "observations": obs,
            "velocity": {"observed_at": TODAY.isoformat(), "active": 4, "url": "https://www.ebay.co.uk/sch/synthetic-fixture"},
            "floor": {"amount": 25, "exit_cost": 1, "currency": "GBP", "kind": "cash", "observed_at": TODAY.isoformat(),
                      "url": "https://uk.webuy.com/product-detail/synthetic-fixture", "identity": identity.copy()},
            "offers": [{"url": "https://www.hotukdeals.com/deals/synthetic-fixture", "source_url": "https://retailer.example/synthetic-fixture",
                        "observed_at": TODAY.isoformat(), "price": 20, "delivery": 0, "online": True, "in_stock": True, "identity": identity.copy()}]}

def raw():
    return {"title": "Synthetic trainers synthetic-99 white men UK 9", "url": record()["offers"][0]["url"], "price": 20,
            "category": "trainers", "merchant": "Fixture retailer", "delivery": "Free delivery", "inbound_delivery": 0,
            "online_eligible": True, "desc": "", "heat": 0}

class EvidenceHelpers:
    def comp(self, r=None):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"evidence.json"
            p.write_text(json.dumps({"schema_version": 1, "records": [r or record()]}))
            return evidence.load(p)
class Evidence(EvidenceHelpers, unittest.TestCase):
    def test_valid_ingestion_computes_observed_values(self):
        c = self.comp()[0]
        self.assertEqual((c.low, c.high, c.sold_90d, c.floor, c.days_to_sell), (66, 67, 5, 24, 3))
        self.assertEqual(c.evidence_type, "sold")
    def test_reject_asks_and_voucher_and_missing_identity(self):
        for field, change in [("observations", lambda r: r["observations"][0].update(kind="active_ask")),
                              ("floor", lambda r: r["floor"].update(kind="voucher")),
                              ("identity", lambda r: r["identity"].pop("sku"))]:
            r = record(); change(r)
            with self.subTest(field=field), self.assertRaises(ValueError): evidence.validate(r)
    def test_reject_duplicate_sales_future_nonfinite_wrong_currency(self):
        mutations = [lambda r: r["observations"].append(r["observations"][0]),
                     lambda r: r["observations"][0].update(sold_at=(TODAY+dt.timedelta(days=1)).isoformat()),
                     lambda r: r["observations"][0].update(price=float("nan")),
                     lambda r: r["observations"][0].update(price=-1),
                     lambda r: r["observations"][0].update(currency="USD"),
                     lambda r: r.update(reviewed=False),
                     lambda r: r.update(buyer_email="private@example.com"),
                     lambda r: r["observations"][0].update(url="https://example.com/sale?token=SECRET")]
        for mutate in mutations:
            r = record(); mutate(r)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError): evidence.validate(r)
    def test_atomic_merge_is_idempotent_and_bad_import_preserves_store(self):
        with tempfile.TemporaryDirectory() as td:
            incoming, store = Path(td)/"incoming.json", Path(td)/"store.json"
            incoming.write_text(json.dumps({"schema_version": 1, "records": [record()]}))
            self.assertEqual(evidence.ingest(incoming, store), 1)
            evidence.ingest(incoming, store); self.assertEqual(len(evidence.read_records(store)), 1)
            old = store.read_bytes(); incoming.write_text('{"schema_version": 999, "records": []}')
            with self.assertRaises(ValueError): evidence.ingest(incoming, store)
            self.assertEqual(store.read_bytes(), old)
    def test_stale_sales_not_rejuvenated(self):
        r = record()
        for o in r["observations"]: o.update(sold_at=(TODAY-dt.timedelta(days=40)).isoformat(), listed_at=None)
        self.assertEqual(self.comp(r), [])
    def test_missing_listing_dates_do_not_invent_velocity(self):
        r = record(); r["observations"][0].pop("listed_at")
        self.assertIsNone(self.comp(r)[0].days_to_sell)

class Grades(EvidenceHelpers, unittest.TestCase):
    def deal(self, r=None):
        return cli.build_deal(raw(), self.comp(r)[0])
    def test_complete_real_shape_can_buy_not_permanently_impossible(self):
        d = self.deal(); d.availability = "live"
        self.assertEqual(grading.grade(d, 200).grade[0], "A")
    def test_asks_never_buy_or_verify_even_with_plausible_numbers(self):
        d = self.deal(); d.availability = "live"; d.evidence_type = "active_ask"
        self.assertEqual(grading.grade(d, 200).grade, "REJECT")
    def test_reviewed_sold_with_missing_velocity_or_floor_can_only_verify(self):
        r = record(); r.pop("floor"); r.pop("velocity")
        d = self.deal(r); d.availability = "live"
        self.assertEqual(grading.grade(d, 200).grade[0], "B")
    def test_generic_matching_does_not_cross_exact_variants(self):
        from moneyhunter import matching
        c = self.comp()[0]
        self.assertTrue(matching.check("Synthetic trainers synthetic-99 white men UK 8", "", c))
        self.assertTrue(matching.check("Synthetic trainers synthetic-99 white men UK 9 refurbished", "", c))
        self.assertEqual(matching.check(raw()["title"], "", c), "")
    def test_small_adult_sizes_not_automatically_kids(self):
        from moneyhunter import matching
        c = comps.Comp("samba og", "trainers", 65, 70, "reference", "s", None, "", None, None, None, TODAY)
        self.assertEqual(matching.check("Womens Adidas Samba OG UK 4.5", "", c), "")
        self.assertIn("kids", matching.check("Kids Adidas Samba OG UK 4.5", "", c))
    def test_unknown_delivery_stock_online_offer_identity_block_signals(self):
        for name, value in [("delivery_known", False), ("availability", "unknown"), ("online_eligible", False), ("offer_verified", False)]:
            d = self.deal(); d.availability = "live"; setattr(d, name, value)
            with self.subTest(name=name): self.assertEqual(grading.grade(d, 200).grade, "REJECT")
    def test_floor_and_velocity_have_separate_clocks(self):
        for name in ("floor_age_days", "velocity_age_days"):
            d = self.deal(); d.availability = "live"; setattr(d, name, 40)
            self.assertNotEqual(grading.grade(d, 200).grade[0], "A")
    def test_stale_or_missing_sold_evidence_never_signal(self):
        for age in (None, -1, 31):
            d = self.deal(); d.availability = "live"; d.comp_age_days = age
            self.assertEqual(grading.grade(d, 200).grade, "REJECT")
    def test_paid_inbound_delivery_changes_net_and_cap(self):
        r = record(); r["offers"][0]["delivery"] = 45
        d = self.deal(r); d.availability = "live"
        result = grading.grade(d, 200)
        self.assertEqual(result.cost, 65)
        self.assertEqual(result.grade, "REJECT")
    def test_quote_cannot_override_contradictory_title(self):
        c = self.comp()[0]
        for title in ("Unrelated product", "Synthetic trainers synthetic-99 white men UK 8", "Synthetic trainers synthetic-99 black men UK 9", "Synthetic trainers synthetic-99 white womens UK 9", "Synthetic trainers synthetic-99 white men UK 9 refurbished"):
            r = raw(); r["title"] = title
            self.assertFalse(cli.build_deal(r, c).offer_verified, title)
    def test_offer_price_and_age_must_still_match(self):
        r = record(); r["offers"][0]["price"] = 19
        self.assertFalse(self.deal(r).offer_verified)
        r = record(); r["offers"][0]["observed_at"] = (TODAY-dt.timedelta(days=2)).isoformat()
        self.assertFalse(self.deal(r).offer_verified)
    def test_expiry_unknown_expired_and_budget_fail_closed(self):
        for status in ("live", "expired", "unknown"):
            d = self.deal(); pairs = [(d, grading.grade(d, 200))]
            with patch.object(hotukdeals, "live_status", return_value=status):
                self.assertEqual(cli.drop_expired(pairs), 1)
            self.assertEqual(pairs[0][1].grade[0], "A" if status == "live" else "R")
        d = self.deal(); pairs = [(d, grading.grade(d, 200))]
        with patch.object(cli, "LIVE_CHECKS", 0), patch.object(hotukdeals, "live_status") as call:
            cli.drop_expired(pairs); call.assert_not_called()
        self.assertEqual(pairs[0][1].grade, "REJECT")
    def test_legacy_rows_cannot_signal(self):
        c = comps.Comp("synthetic trainers", "trainers", 66, 67, "legacy guide", "old", 30, "", 20, 120, 3, TODAY)
        d = cli.build_deal(raw(), c); d.availability = "live"
        self.assertEqual(grading.grade(d, 200).grade, "REJECT")
    def test_floor_is_not_no_loss_when_exit_costs_exceed_quote(self):
        r = record(); r["floor"].update(amount=25, exit_cost=10)
        d = self.deal(r); d.availability = "live"
        self.assertLess(grading.grade(d, 200).worst, 0)
        self.assertNotEqual(grading.grade(d, 200).grade[0], "A")

class Sources(unittest.TestCase):
    def test_console_accessories_do_not_price_as_console(self):
        from moneyhunter import matching
        c = comps.Comp("switch oled", "gaming", 200, 250, "reference", "s", None, "", None, None, None, TODAY)
        for title in ("Switch OLED replacement screen", "Switch OLED shell housing", "Switch OLED screen protector"):
            self.assertTrue(matching.check(title, "", c), title)
    def test_delivery_unknown_free_and_paid_conditional(self):
        self.assertIsNone(hotukdeals.delivery_cost("£20 trainers"))
        self.assertIsNone(hotukdeals.delivery_cost("Free delivery over £50"))
        self.assertIsNone(hotukdeals.delivery_cost("Free delivery with Prime"))
        self.assertEqual(hotukdeals.delivery_cost("£20 + £3.99 delivery"), 3.99)
        self.assertEqual(hotukdeals.delivery_cost("£20 free delivery"), 0)
    def test_offline_preorder_unavailable_never_eligible(self):
        for title in ("C&C Only Limited Stores", "in-store only", "pre order", "out of stock", "Click and collect only"):
            self.assertFalse(hotukdeals.online_status(title), title)
    def test_expiry_network_failure_is_unknown_and_cached(self):
        hotukdeals._STATUS.clear()
        with patch("urllib.request.urlopen", side_effect=OSError("offline")) as call:
            self.assertEqual(hotukdeals.live_status("https://www.hotukdeals.com/deals/fixture"), "unknown")
            self.assertFalse(hotukdeals.is_live("https://www.hotukdeals.com/deals/fixture"))
            self.assertEqual(call.call_count, 1)
    def test_all_routes_share_bounded_page_checks(self):
        hotukdeals._STATUS.clear()
        with patch.object(hotukdeals, "CHECK_BUDGET", 2), patch("urllib.request.urlopen", side_effect=OSError("fixture")) as call:
            for n in range(10): self.assertEqual(hotukdeals.live_status(f"https://www.hotukdeals.com/fixture/{n}"), "unknown")
            self.assertEqual(call.call_count, 2)
        hotukdeals._STATUS.clear()
    def test_full_title_dedupe_keeps_variants(self):
        a = "One two three four five six seven eight variant white"
        b = "One two three four five six seven eight variant black"
        self.assertNotEqual(hotukdeals.dedupe_key(a, 20), hotukdeals.dedupe_key(b, 20))
    def test_filtered_feed_items_are_explicitly_counted(self):
        xml=b'<rss><channel><item><title>Unpriced item</title><link>https://www.hotukdeals.com/fixture-no-price</link></item></channel></rss>'
        with patch.object(config,"FEEDS",{"tools":["fixture"]}),patch.object(hotukdeals,"_fetch",return_value=xml):
            self.assertEqual(hotukdeals.scan(),[])
        self.assertEqual(hotukdeals.LAST_DIAGNOSTICS["missing_price_or_category"],1)
    def test_source_failures_and_old_items_are_counted(self):
        xml = b'<rss><channel><item><title>Nike trainers</title><link>https://www.hotukdeals.com/fixture</link><description>Price \xc2\xa320 free delivery</description><pubDate>Mon, 01 Jan 2001 00:00:00 GMT</pubDate></item></channel></rss>'
        with patch.object(config, "FEEDS", {"trainers": ["good", "broken"]}), patch.object(hotukdeals, "_fetch", side_effect=[xml, OSError("fixture")]):
            errors=[]; self.assertEqual(hotukdeals.scan(log=errors.append), [])
        self.assertEqual(hotukdeals.LAST_DIAGNOSTICS["feeds_failed"], 1)
        self.assertEqual(hotukdeals.LAST_DIAGNOSTICS["old_dropped"], 1)
        self.assertEqual(len(errors), 1)

class Operational(unittest.TestCase):
    def test_new_rescan_price_changes_and_gap(self):
        state = runtime.load("/nonexistent/synthetic-state")
        when = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(runtime.observe([raw()], state, when)["new"], 1)
        state["last_success"] = runtime.stamp(when-dt.timedelta(hours=7))
        r = raw(); r["price"] = 19
        count = runtime.observe([r], state, when)
        self.assertEqual((count["new"], count["rescanned"], count["price_changed"]), (0, 1, 1))
        self.assertAlmostEqual(count["gap_minutes"], 420, delta=0.1)
    def test_corrupt_state_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; p.write_text("[]")
            with self.assertRaises(ValueError): runtime.load(p)
    def test_tier_requires_integer_not_bool_string_or_out_of_range(self):
        for value in (True, "1", 1.0, -1, 5, None):
            with self.assertRaises(ValueError): tier_sync.validate({"tier": value})
        self.assertEqual(tier_sync.validate({"tier": 0}), 0)
        self.assertEqual(tier_sync.fetch("")[0], 0)
    def test_tier_failure_does_not_echo_private_body(self):
        def broken(*a, **kw): raise ValueError("SECRET PRIVATE BODY")
        tier, warning = tier_sync.fetch("SECRET TOKEN", opener=broken)
        self.assertEqual((tier, warning), (0, "ValueError"))
    def test_send_kill_switch_even_if_webhook_is_set(self):
        with patch.dict(os.environ, {"MONEYHUNTER_DISABLE_SEND": "1", discord.ENV: "https://discord.com/api/webhooks/SYNTHETIC"}), patch("urllib.request.urlopen") as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(discord.post([]), 0); call.assert_not_called()
    def test_network_delivery_failure_is_safe_retryable_status(self):
        with patch.dict(os.environ, {"MONEYHUNTER_DISABLE_SEND":"0", discord.ENV:"https://discord.com/api/webhooks/SYNTHETIC"}), patch("urllib.request.urlopen", side_effect=OSError("fixture")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(discord.post([]),0)
    def test_delivery_errors_are_exported_not_silently_swallowed(self):
        stats={"A":1,"B":0,"errors":["synthetic source warning"],"scanned":0,"priced":0,"unpriced":0,"affordable":0,"R":0}
        with tempfile.TemporaryDirectory() as td, patch.object(hub,"PRICES",str(Path(td)/"prices.json")), patch.object(hub, "hooks", return_value={"bot-status":"https://discord.com/api/webhooks/SYNTHETIC"}), patch.object(discord,"post",return_value=500), patch.object(hub,"price_drops",return_value=([],{})), contextlib.redirect_stdout(io.StringIO()):
            hub.route([],[],stats,[],set(),dry=False)
            self.assertEqual(stats["delivery_failures"],1)
            self.assertTrue(any("HTTP 500" in error for error in stats["errors"]))
    @patch("moneyhunter.publication.allowed",new=lambda *a:True)
    def test_grade_promotion_and_watch_keys_do_not_suppress_buy(self):
        d = grading.Deal("Synthetic trainers", raw()["url"], 20, "trainers", "fixture", target=66)
        r = grading.grade(d, 200); r.grade = "A — BUY"
        base = hotukdeals.dedupe_key(d.title, d.buy_price)
        seen = {"alert:B:" + base, "w:" + d.url, base}
        with patch.object(hub, "send", return_value=204) as send, patch.object(hub, "price_drops", return_value=([], {})), tempfile.TemporaryDirectory() as td, patch.object(hub, "PRICES", str(Path(td)/"prices.json")):
            out = hub.route([], [(d,r)], {"A":1, "B":0, "errors":[], "scanned":1, "priced":0, "unpriced":1, "affordable":0, "R":0}, [], seen, dry=True)
            self.assertIn("alert:A:"+base, out)
            self.assertTrue(any(c.args[0] == "buy-now" for c in send.call_args_list))
    def test_unknown_watch_check_is_retryable_not_marked_seen(self):
        r=raw()
        with patch.object(hub, "send", return_value=204), patch.object(hotukdeals, "live_status", return_value="unknown"), patch.object(hub, "price_drops", return_value=([], {})), tempfile.TemporaryDirectory() as td, patch.object(hub, "PRICES", str(Path(td)/"prices.json")):
            out=hub.route([r],[],{"A":1,"B":0,"errors":[],"scanned":1,"priced":0,"unpriced":1,"affordable":0,"R":0},[],set(),dry=True)
            self.assertNotIn("w:"+r["url"],out)
    def test_price_increases_update_latest_baseline(self):
        with tempfile.TemporaryDirectory() as td, patch.object(hub, "PRICES", str(Path(td)/"prices.json")):
            r=raw(); p=Path(hub.PRICES); p.write_text(json.dumps({hub.title_key(r["title"]): {"price":10,"low":10,"ts":runtime.stamp(runtime.now()),"url":r["url"]}}))
            drops, state=hub.price_drops([r]); self.assertEqual(drops, [])
            self.assertEqual(state[hub.title_key(r["title"])]["price"], 20)
            self.assertEqual(state[hub.title_key(r["title"])]["low"], 10)

class Integration(EvidenceHelpers, unittest.TestCase):
    def test_offline_scan_import_grade_export_review_and_rescan(self):
        c = self.comp()[0]
        unknown = raw(); unknown.update(title="Unmatched LEGO 12345 free delivery", category="lego", url="https://www.hotukdeals.com/deals/other-synthetic")
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"MONEYHUNTER_DISABLE_SEND":"1", "MONEYHUNTER_COMMUNITY":"1", "MH_TIER":"0"}, clear=True), patch.object(cli, "OPERATIONAL", str(Path(td)/"scan_state.json")), patch.object(comps, "load", return_value=[c]), patch.object(ebay, "available", return_value=False), patch.object(hotukdeals, "scan", side_effect=lambda **kw: [raw(), unknown.copy()]), patch.object(hotukdeals, "LAST_DIAGNOSTICS", {"feeds_ok":1,"feeds_failed":0}), patch.object(hotukdeals, "live_status", return_value="live"), patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network")), contextlib.redirect_stdout(io.StringIO()):
            _, _, pairs, _, unpriced, stats = cli.run_scan()
            self.assertEqual((stats["scanned"],stats["new"],stats["sold_valued"],stats["A"],stats["unpriced"]), (2,2,1,1,1))
            self.assertEqual(cli.LAST_REVIEW[0]["url"], unknown["url"])
            out=Path(td)/"deals.json"; cli.export_public(str(out),stats,pairs)
            data=json.loads(out.read_text()); self.assertEqual(data["schema_version"],2)
            self.assertEqual(data["deals"][0]["evidence_type"],"sold")
            runtime.save(cli.OPERATIONAL,cli.LAST_OPERATIONAL)
            again=cli.run_scan()[-1]
            self.assertEqual((again["new"],again["rescanned"]),(0,2))
    def test_unmatched_items_have_no_fake_net_profit(self):
        d=cli.build_deal(raw(),None)
        self.assertIsNone(grading.grade(d,200))

class ReviewedPricing(EvidenceHelpers, unittest.TestCase):
    def test_catalog_is_independent_of_any_acquisition_offer(self):
        r=record(); r.pop("offers"); r.pop("floor"); r.pop("velocity")
        for o in r["observations"]:
            o["observed_at"]=TODAY.isoformat(); o["item_price"]=o["price"]-2.7; o["shipping"]=2.7
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"evidence.json"; path.write_text(json.dumps({"schema_version":1,"records":[r]}))
            catalog=evidence.public_catalog(path)
            self.assertEqual(len(catalog),1)
            self.assertEqual(catalog[0]["sample_count"],5)
            self.assertFalse(catalog[0]["is_buy_signal"])
            self.assertEqual(catalog[0]["sold_sources"][0]["shipping"],2.7)
            self.assertEqual(catalog[0]["sold_sources"][0]["observed_at"],TODAY.isoformat())
            self.assertNotIn("floor",catalog[0]); self.assertNotIn("offers",catalog[0])
    def test_catalog_ages_out_by_sale_not_observation(self):
        r=record()
        for o in r["observations"]:
            o["sold_at"]=(TODAY-dt.timedelta(days=31)).isoformat(); o.pop("listed_at"); o["observed_at"]=TODAY.isoformat()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"evidence.json"; p.write_text(json.dumps({"schema_version":1,"records":[r]}))
            self.assertEqual(evidence.public_catalog(p),[])
    def test_observation_dates_and_shipping_breakdown_validate(self):
        for change in (lambda o:o.update(observed_at=(TODAY-dt.timedelta(days=1)).isoformat()),
                       lambda o:o.update(item_price=60,shipping=2.7),
                       lambda o:o.update(shipping=2.7),
                       lambda o:o.update(item_price=62.3,shipping=-1)):
            r=record(); change(r["observations"][0])
            with self.subTest(change=change),self.assertRaises(ValueError): evidence.validate(r)
    def test_review_cannot_precede_actual_sale(self):
        r=record(); r["reviewed_at"]=(TODAY-dt.timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError): evidence.validate(r)
    def test_missing_observation_dates_remain_unknown_not_inferred(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"evidence.json"; p.write_text(json.dumps({"schema_version":1,"records":[record()]}))
            self.assertIsNone(evidence.public_catalog(p)[0]["sold_sources"][0]["observed_at"])
    def test_search_query_preserves_exact_sku_and_platform(self):
        self.assertIn("21345",embeds.short_query("LEGO Ideas Polaroid OneStep SX-70 Camera 21345"))
        self.assertIn("SX-70",embeds.short_query("LEGO Ideas Polaroid OneStep SX-70 Camera 21345"))
        self.assertIn("Switch",embeds.short_query("Mario Kart 8 Deluxe (Nintendo Switch) - with code"))
    def test_reviewed_used_offer_cannot_override_new_or_refurbished_title(self):
        from moneyhunter import matching
        r=record(); r["identity"]["condition"]="used"
        for o in r["observations"]: o["identity"]["condition"]="used"
        r.pop("offers"); r.pop("floor")
        c=self.comp(r)[0]
        self.assertTrue(matching.quoted_offer_check(raw()["title"]+" new", "", c))
        self.assertTrue(matching.quoted_offer_check(raw()["title"]+" refurbished", "", c))
    def test_trending_uses_landed_delivery_and_labels_unknown_lower_bound(self):
        a=raw(); a.update(heat=125,inbound_delivery=4,category="gaming")
        b=raw(); b.update(heat=126,inbound_delivery=None,url=a["url"]+"-other",category="gaming")
        with patch.object(hub,"send",return_value=204) as send,patch.object(hotukdeals,"live_status",return_value="unknown"),patch.object(hub,"price_drops",return_value=([],{})),patch.object(hub,"read_prices",return_value={}):
            hub.route([a,b],[],{"A":1,"B":0,"errors":[],"scanned":1,"priced":0,"unpriced":1,"affordable":0,"R":0},[],set(),dry=True)
            self.assertFalse(any(c.args[0]=="trending" for c in send.call_args_list))
            self.assertNotIn(a["title"],hub.market_pulse([a,b],{}))

if __name__ == "__main__": unittest.main()
