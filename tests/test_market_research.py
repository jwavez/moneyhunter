"""Synthetic/offline only. No production sold evidence or outbound delivery."""
import copy
import datetime as dt
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from moneyhunter import market, runtime
from moneyhunter.scanners import capture, ebay, hotukdeals

NOW = dt.datetime(2026,11,7,12,tzinfo=dt.timezone.utc)
RAW = {"title":"LEGO Synthetic Moon Rover 75402 new sealed", "url":"https://www.hotukdeals.com/deals/synthetic-fixture", "price":20, "category":"lego"}

def item(i=0, **changes):
    x={"itemId":f"synthetic-fixture-{i}","title":"LEGO 75402 Synthetic Moon Rover sealed new","conditionId":"1000",
       "itemLocation":{"country":"GB"},"itemWebUrl":f"https://www.ebay.co.uk/itm/synthetic-fixture-{i}?tracking=discard",
       "price":{"value":str(30+i),"currency":"GBP"},"shippingOptions":[{"shippingCostType":"FIXED","shippingCost":{"value":"3","currency":"GBP"}}]}
    x.update(changes);return x

class Identity(unittest.TestCase):
    def test_exact_lego_and_physical_game(self):
        self.assertEqual(market.identity(RAW).match,"LEGO 75402")
        self.assertIsNotNone(market.identity({"title":"Mario Kart 8 Deluxe Nintendo Switch", "category":"gaming"}))
    def test_ambiguous_identity_never_guessed(self):
        for title in ["LEGO 75402 and 75403", "LEGO 75402 instructions only", "LEGO 75402 box only", "LEGO 75402 MOC compatible", "LEGO 75402 used", "LEGO bundle 75402", "LEGO 75402 minifigures"]:
            self.assertIsNone(market.identity({**RAW,"title":title}),title)
        for title in ["Mario Kart Nintendo Switch digital", "Elden Ring PS5 PS4", "Game PS5"]:
            self.assertIsNone(market.identity({"title":title,"category":"gaming"}),title)
    def test_set_number_is_not_whole_product_identity(self):
        ident=market.identity(RAW)
        for title in ["LEGO 75402 Synthetic Moon Rover Sticker Sheet new", "LEGO 75402 Synthetic Moon Rover Instruction Booklet new",
                      "LEGO 75402 Synthetic Moon Rover display stand new", "LEGO 75402 Synthetic Moon Rover SMART tag new",
                      "LEGO 75402 Synthetic Moon Rover LED lighting new", "LEGO 75402 new sealed", "LEGO 75402 Galactic Robot new"]:
            self.assertFalse(market.matches(title,ident),title)
        self.assertTrue(market.matches("LEGO 75402 Synthetic Moon Rover complete new sealed",ident))
        self.assertIsNone(market.identity({**RAW,"title":"LEGO 75402 new sealed"}))

    def test_name_fingerprint_prevents_same_number_wrong_name_cache_reuse(self):
        other=market.identity({**RAW,"title":"LEGO Synthetic Galactic Robot 75402 new sealed"})
        self.assertNotEqual(market.cache_key(market.identity(RAW)),market.cache_key(other))

    def test_product_names_normalise_accents_and_single_distinctive_name(self):
        c=market.identity({**RAW,"title":"LEGO Pokémon Munchlax 72150"})
        self.assertEqual(c.name_terms,["munchlax"])
        self.assertTrue(market.matches("LEGO Pokemon Munchlax 72150 sealed new",c))
        self.assertFalse(market.matches("LEGO Pokemon 72150 Sticker Sheet",c))

    def test_other_platform_and_accessory_not_a_comp(self):
        c=market.identity({"title":"Elden Ring PS5 Standard game", "category":"gaming"})
        self.assertIsNotNone(c)
        for title in ["Elden Ring PS4 Standard game", "Elden Ring PS5 Standard game controller", "Elden Ring PS5 Standard game Deluxe edition"]:
            self.assertFalse(market.matches(title,c),title)

class Asking(unittest.TestCase):
    def summary(self,items):return market.summary({"itemSummaries":items},market.identity(RAW),NOW)
    def test_shipping_is_included_no_haircut_or_fake_sales(self):
        s=self.summary([item(i) for i in range(5)])
        self.assertEqual((s["sample_count"],s["listed_total_low"],s["listed_total_median"]),(5,33,35))
        self.assertEqual(s["kind"],"active_ask");self.assertNotIn("sold_90d",s)
        self.assertNotIn("?",s["offers"][0]["url"])
    def test_accepted_examples_keep_auditable_title_item_shipping_and_condition(self):
        x=item();s=self.summary([x]);o=s["offers"][0]
        self.assertEqual(o["title"],x["title"])
        self.assertEqual(o["item_price"]+o["shipping"],o["listed_total"])
        self.assertEqual(o["declared_condition"],"new")
        self.assertTrue(s["name_terms"])

    def test_unknown_shipping_currency_condition_location_and_ended_rejected(self):
        xs=[item(0,shippingOptions=[]),item(1,conditionId="3000"),item(2,itemLocation={}),
            item(3,price={"value":"30","currency":"USD"}),item(4,itemEndDate="2026-11-06T00:00:00Z"),item(5,itemGroupType="SELLER_DEFINED_VARIATIONS"),item(6,price={"value":"NaN","currency":"GBP"})]
        s=self.summary(xs);self.assertEqual(s["sample_count"],0);self.assertIsNone(s["listed_total_median"])
        self.assertEqual(sum(s["rejected"].values()),7)
    def test_bad_url_title_and_duplicates_rejected(self):
        s=self.summary([item(),item(),item(2,title="LEGO 75402 instructions"),item(3,itemWebUrl="https://evil.example/itm/1")])
        self.assertEqual(s["sample_count"],1);self.assertEqual(sum(s["rejected"].values()),3)
    def test_extremes_retained_and_flagged_not_inflated(self):
        s=self.summary([item(),item(1),item(2,price={"value":"200","currency":"GBP"})])
        self.assertEqual(s["sample_count"],3);self.assertEqual(s["listed_total_low"],33);self.assertEqual(s["listed_total_high"],203)
        self.assertEqual(s["status"],"wide_spread")
    def test_cache_reused_budget_rotation_and_never_mutates_raw(self):
        raws=[{**RAW,"title":f"LEGO Synthetic Moon Rover {75402+i}","url":RAW["url"]+str(i)} for i in range(3)]
        original=copy.deepcopy(raws);rows=[{"url":r["url"],"priority":3-i} for i,r in enumerate(raws)];state={"ask_cache":{}}
        with patch.object(ebay,"available",return_value=True),patch.object(ebay,"active_items",return_value={"itemSummaries":[item()]}) as call:
            h=market.enrich(rows,raws,state,NOW,budget=1);self.assertEqual(h["queries"],1)
            self.assertEqual(rows[0]["ask_status"],"small_sample")
            market.enrich(rows,raws,state,NOW,budget=1);self.assertEqual(call.call_count,2)
            self.assertEqual(len(state["ask_cache"]),2)
        self.assertEqual(raws,original)
    def test_permission_rate_limit_pause_survives_future_invocations(self):
        for code in (401,403,429):
            state={"ask_cache":{}};rows=[{"url":RAW["url"]}]
            with patch.object(ebay,"available",return_value=True),patch.object(ebay,"active_items",side_effect=HTTPError("https://api.ebay.com",code,"fixture",{},None)) as call:
                self.assertEqual(market.enrich(rows,[RAW],state,NOW)["status"],"paused_operator_review_required")
                market.enrich(rows,[RAW],state,NOW+dt.timedelta(days=2));self.assertEqual(call.call_count,1)
    def test_no_keys_no_requests(self):
        with patch.object(ebay,"available",return_value=False),patch.object(ebay,"active_items") as call:
            h=market.enrich([{"url":RAW["url"]}],[RAW],{"ask_cache":{}},NOW)
        call.assert_not_called();self.assertEqual(h["status"],"unavailable_no_keys")
    def test_oauth_expiry_refreshes_without_logging_credentials(self):
        response=lambda:io.BytesIO(json.dumps({"access_token":"synthetic-only","expires_in":120}).encode())
        with patch.dict(os.environ,{"EBAY_CLIENT_ID":"synthetic-id","EBAY_CLIENT_SECRET":"synthetic-secret"}),patch.object(ebay,"_token",None),patch.object(ebay,"_token_expires",0),patch.object(ebay.time,"monotonic",return_value=0) as clock,patch.object(ebay.urllib.request,"urlopen",side_effect=lambda *a,**k:response()) as call:
            ebay._auth();clock.return_value=30;ebay._auth();self.assertEqual(call.call_count,1)
            clock.return_value=70;ebay._auth();self.assertEqual(call.call_count,2)

class EndToEnd(unittest.TestCase):
    def test_high_active_asks_cannot_create_sold_prices_or_buy_signals(self):
        import contextlib, tempfile
        from pathlib import Path
        from moneyhunter import cli
        r={**RAW,"merchant":"Synthetic retailer","delivery":"Unknown","inbound_delivery":0,"online_eligible":True,"desc":""}
        with tempfile.TemporaryDirectory() as td,patch.object(cli,"OPERATIONAL",str(Path(td)/"state.json")),patch.object(cli,"bankroll",return_value=200),patch.object(cli,"ebay_status",return_value="active listings only"),patch.object(cli.hotukdeals,"scan",return_value=[r]),patch.object(cli.CP,"load",return_value=[]),patch.object(ebay,"available",return_value=True),patch.object(ebay,"active_items",return_value={"itemSummaries":[item(i,price={"value":"300","currency":"GBP"}) for i in range(5)]}),patch.dict(os.environ,{"MONEYHUNTER_COMMUNITY":"1","MONEYHUNTER_DISABLE_SEND":"1"}),contextlib.redirect_stdout(io.StringIO()):
            br,tier,graded,affordable,unpriced,stats=cli.run_scan()
            self.assertEqual((stats["A"],stats["B"],stats["sold_valued"],stats["priced"]),(0,0,0,0))
            self.assertEqual(cli.LAST_REVIEW[0]["ask_context"]["sample_count"],5)
            out=Path(td)/"public.json";cli.export_public(str(out),stats,graded);payload=json.loads(out.read_text())
            self.assertEqual(payload["pricing_status"]["sold_observations"],0)
            self.assertEqual(payload["pricing_status"]["indicative_asking_products"],1)
            self.assertEqual(payload["deals"],[])

class FeedPrices(unittest.TestCase):
    def test_unambiguous_only(self):
        for s in ["was £80 now £40","£20 + £3 delivery","Save £20: £40","£9.999"]:
            self.assertIsNone(hotukdeals._price(s),s)
        for s in ["£40 £40","Rated 4.5 stars £40","&pound;40"]:self.assertEqual(hotukdeals._price(s),40)

class DigitalSources(unittest.TestCase):
    def test_code_merchant_cannot_masquerade_as_physical_game(self):
        from moneyhunter import hub
        for merchant in ("Xbox", "Loaded", "Eneba"):
            self.assertFalse(hub.resellable({"title":"Some Game Xbox Series X", "category":"gaming","merchant":merchant}))
        self.assertTrue(hub.resellable({"title":"Xbox Wireless Controller", "category":"gaming","merchant":"Microsoft"}))

class Capture(unittest.TestCase):
    def test_disabled_without_request_and_wrong_endpoint_refused(self):
        with patch.dict(os.environ,{},clear=True),patch.object(capture,"urlopen") as call:self.assertEqual(capture.scan(),[])
        call.assert_not_called()
        with patch.dict(os.environ,{"MONEYHUNTER_CAPTURE_URL":"https://evil.example"}),self.assertRaises(ValueError):capture.scan()
    def test_valid_capture_whitelists_fields_and_stale_wrong_host_rejected(self):
        x={**RAW,"published_at":NOW.isoformat(),"last_seen":NOW.isoformat(),"kind":"feed_offer_only", "floor":100, "sold_90d":1000}
        data={"schema_version":1,"kind":"feed_capture_only","items":[x,{**x,"url":"https://evil.example/deals/x"},{**x,"last_seen":"2026-10-01T00:00:00Z"}]}
        with patch.dict(os.environ,{"MONEYHUNTER_CAPTURE_URL":capture.URL}),patch.object(capture,"urlopen",return_value=io.BytesIO(json.dumps(data).encode())):
            raws=capture.scan(when=NOW)
        self.assertEqual(len(raws),1);self.assertIsNone(raws[0]["inbound_delivery"]);self.assertNotIn("floor",raws[0]);self.assertNotIn("sold_90d",raws[0])
        self.assertEqual(capture.LAST_DIAGNOSTICS["invalid"],2)
    def test_current_direct_feed_wins_conflict_and_captured_duplicates(self):
        with patch.object(capture,"LAST_DIAGNOSTICS",{}):
            merged=capture.merge([RAW],[{**RAW,"price":10},{**RAW,"url":RAW["url"]+"2"},{**RAW,"title":"LEGO 75403","url":RAW["url"]+"3"}])
            self.assertEqual(len(merged),2);self.assertEqual(merged[0]["price"],20);self.assertEqual(capture.LAST_DIAGNOSTICS["duplicates"],2)
