"""Synthetic offline active-ask models; no genuine sales or live delivery."""
import copy
import datetime as dt
import unittest
from moneyhunter import asking, fees, config, market

NOW=dt.datetime(2026,11,7,14,tzinfo=dt.timezone.utc)
RAW={"title":"Synthetic exact game PS5 Standard", "url":"https://www.hotukdeals.com/deals/synthetic-ask-model", "category":"gaming", "price":15.,"inbound_delivery":2.,"online_eligible":True,"merchant":"Synthetic retailer"}
def offer(i,price=50.,**changes):
    return {"item_id":f"v1|{123456789000+i}|0", "url":f"https://www.ebay.co.uk/itm/{123456789000+i}","seller":f"synthetic-seller-{i}","country":"GB","currency":"GBP","declared_condition":"new","item_price":price-3,"shipping":3.,"listed_total":price,**changes}
def snap(offers=None):return {"kind":"active_ask","query":"Synthetic exact game PS5 Standard","category":"gaming","observed_at":NOW.isoformat(),"offers":offers if offers is not None else [offer(i,50+i) for i in range(6)]}
def model(raw=None,offers=None):return asking.estimate(raw or RAW,snap(offers),NOW)

class Estimate(unittest.TestCase):
    def test_usable_ask_opportunity_is_distinct_from_verified_buy_and_sold(self):
        m=model();self.assertTrue(m["estimated_opportunity"])
        self.assertIn("CHECK BEFORE BUYING",m["signal"])
        self.assertNotIn("sold_90d",m);self.assertNotIn("grade",m)
        self.assertEqual(m["estimated_resale"],48.5)
        self.assertLessEqual(m["suggested_listing"],m["competition_low"])
        self.assertIn("speed",m["quick_sale_basis"])
    def test_exclude_acquisition_id_url_tracking_and_same_seller(self):
        raw={**RAW,"acquisition_url":"https://www.ebay.co.uk/itm/123456789000?tracking=x","acquisition_seller":"SYNTHETIC-SELLER-1"}
        m=model(raw);self.assertEqual(m["acquisition_excluded"],2)
        self.assertEqual(m["competition_low"],52)
        self.assertFalse(any(o["seller"].endswith(("-0","-1")) for o in m["sources"]))
    def test_syndicated_acquisition_urls_and_same_promo_not_regular_reference(self):
        raw={**RAW,"acquisition_urls":["https://www.ebay.co.uk/itm/123456789000?different=tracking"],"promotion_id":"synthetic-code"}
        xs=[offer(0,20),offer(1,25,promotion_id="synthetic-code",advertised_original_total=100)]+[offer(i,50+i) for i in range(2,8)]
        m=model(raw,xs);self.assertEqual(m["competition_low"],25)
        self.assertEqual(m["same_promotion_references_excluded"],1)
        self.assertIsNone(m["advertised_original_range"])
        self.assertLessEqual(m["estimated_resale"],25)
    def test_real_cheaper_discount_competition_never_cherry_picked_away(self):
        xs=[offer(0,12,discount_status="advertised_discount",advertised_original_total=80)]+[offer(i,50+i) for i in range(1,7)]
        m=model({**RAW,"price":20},xs)
        self.assertEqual(m["competition_low"],12);self.assertTrue(m["discount_overlap"])
        self.assertLessEqual(m["estimated_resale"],12);self.assertFalse(m["estimated_opportunity"])
    def test_one_seller_multiquantity_does_not_create_independence(self):
        m=model(offers=[offer(i,50+i,seller="same-seller",quantity=100) for i in range(20)])
        self.assertEqual((m["sample_count"],m["seller_count"]),(1,1));self.assertFalse(m["estimated_opportunity"])
    def test_unknown_seller_low_offer_caps_price_not_confidence(self):
        m=model(offers=[offer(0,10,seller=None)]+[offer(i,50+i) for i in range(1,7)])
        self.assertEqual(m["competition_low"],10);self.assertFalse(m["estimated_opportunity"])
    def test_condition_currency_shipping_and_staleness_rejected(self):
        for change in ({"declared_condition":"used"},{"currency":"USD"},{"country":"US"},{"shipping":None}):
            self.assertIsNone(model(offers=[offer(0,**change)]))
        self.assertIsNone(asking.estimate(RAW,snap(),NOW+dt.timedelta(hours=7)))
    def test_wide_spread_lowers_confidence_without_dropping_cheap_competition(self):
        m=model(offers=[offer(0,50),offer(1,51)]+[offer(i,100+i*10) for i in range(2,7)])
        self.assertEqual(m["confidence"],"limited");self.assertEqual(m["competition_low"],50)
        self.assertEqual(m["estimated_resale"],48.5)
    def test_unknown_inbound_is_qualified_not_free(self):
        m=model({**RAW,"inbound_delivery":None})
        self.assertIsNone(m["net"]);self.assertIsNone(m["roi"]);self.assertIsNone(m["max_item_buy"])
        self.assertIsNotNone(m["net_before_unknown_delivery"]);self.assertFalse(m["estimated_opportunity"])
        self.assertFalse(m["delivery_known"])
    def test_max_buy_and_cost_breakdown_use_real_fee_engine(self):
        m=model();k=fees.net_profit(m["estimated_resale"],m["max_landed_buy"],"ebay_business","gaming",config.postage_for("gaming"),.5,.03)
        self.assertGreaterEqual(k.net,8);self.assertGreaterEqual(k.net/m["max_landed_buy"],.4)
        actual=fees.net_profit(m["estimated_resale"],17,"ebay_business","gaming",config.postage_for("gaming"),.5,.03)
        self.assertEqual(m["net"],actual.net);self.assertEqual(m["fees"],actual.platform_fee)
    def test_coupon_unknown_or_unresolved_ebay_acquisition_requires_check(self):
        self.assertFalse(model(offers=[offer(i,50+i,available_coupons=True) for i in range(6)])["estimated_opportunity"])
        self.assertFalse(model({**RAW,"merchant":"eBay"})["estimated_opportunity"])
    def test_persisted_payload_has_all_competitor_provenance(self):
        m=model();o=m["sources"][0]
        self.assertTrue(all(k in o for k in ("item_id","seller","country","declared_condition","shipping","item_price","url")))
        self.assertIsNone(m["regular_price_reference"])

class FullFlow(unittest.TestCase):
    def test_real_pipeline_can_emit_estimated_opportunity_without_sold_grade(self):
        import contextlib, io, os, tempfile
        from pathlib import Path
        from unittest.mock import patch
        from moneyhunter import cli, hub
        from moneyhunter.scanners import ebay, hotukdeals
        raw={**RAW,"title":"LEGO Synthetic Moon Rover 75402","price":5,"inbound_delivery":0,"category":"lego","desc":"","delivery":"Free","heat":0}
        items=[{"itemId":o["item_id"],"itemWebUrl":o["url"],"seller":{"username":o["seller"]},"conditionId":"1000","itemLocation":{"country":"GB"},"title":"LEGO Synthetic Moon Rover 75402 new sealed","price":{"value":str(o["item_price"]),"currency":"GBP"},"shippingOptions":[{"shippingCostType":"FIXED","shippingCost":{"value":str(o["shipping"]),"currency":"GBP"}}]} for o in [offer(i,50+i) for i in range(6)]]
        with tempfile.TemporaryDirectory() as td,patch.object(cli,"OPERATIONAL",str(Path(td)/"state.json")),patch.dict(os.environ,{"MONEYHUNTER_COMMUNITY":"1","MONEYHUNTER_DISABLE_SEND":"1"},clear=True),patch.object(cli,"ebay_status",return_value="active only"),patch.object(hotukdeals,"scan",return_value=[raw]),patch.object(hotukdeals,"LAST_DIAGNOSTICS",{"feeds_ok":1,"feeds_failed":0}),patch.object(cli.CP,"load",return_value=[]),patch.object(ebay,"available",return_value=True),patch.object(ebay,"active_items",return_value={"itemSummaries":items}),contextlib.redirect_stdout(io.StringIO()):
            br,tier,graded,affordable,unpriced,stats=cli.run_scan()
            self.assertEqual((stats["A"],stats["B"],stats["sold_valued"]),(0,0,0))
            self.assertEqual((stats["ask_valued"],stats["estimated_opportunities"]),(1,1))
            self.assertTrue(cli.LAST_REVIEW[0]["ask_estimate"]["estimated_opportunity"])
            with patch.object(hotukdeals,"live_status",return_value="live"),patch.object(hub,"send",return_value=204) as send,patch.object(hub,"read_prices",return_value={}),patch.object(hub,"price_drops",return_value=([],{})):
                hub.route([raw],graded,stats,[],set(),dry=True,max_cards=1)
                calls=[c.args[0] for c in send.call_args_list]
                self.assertIn("verify",calls)
                self.assertNotIn("buy-now",calls);self.assertNotIn("fast-movers",calls)
                card=next(c.args[1][0] for c in send.call_args_list if c.args[0]=="verify")
                self.assertIn("ESTIMATED OPPORTUNITY",card["author"]["name"])
