import copy,datetime as dt,unittest
from unittest.mock import patch
from moneyhunter import publication as P,market,watchlist,hub,discord
from moneyhunter.scanners.hotukdeals import delivery_cost
from moneyhunter.offer_integrity import primary
from tests.publication_fixtures import priced

class MandatoryPrice(unittest.TestCase):
 def setUp(self):self.r=priced(dict(title="LEGO 75402 Star Wars ARC-170 Starfighter",category="lego",price=110,inbound_delivery=None,url="https://fixture.invalid/retail",merchant="Retailer",heat=150))
 def test_evidence_backed_loss_allowed_but_unsupported_never(self):
  self.assertTrue(P.allowed(self.r));self.assertFalse(P.allowed({**self.r,"ask_estimate":None,"target":200,"breakeven":100}))
  for change in ({"observed_at":"2001-01-01T00:00:00+00:00"},{"observed_at":"2999-01-01T00:00:00+00:00"},{"detail_status":"detail_budget_pending"},{"suggested_listing":200},{"competitor_coupon_unknown":True}):
   with self.subTest(change=change):self.assertFalse(P.allowed({**self.r,"ask_estimate":{**self.r["ask_estimate"],**change}}))
 def test_exact_seller_depth_shipping_and_variant(self):
  for mutate in (lambda s:s.update(title="LEGO 99999 other set"),lambda s:s.update(shipping=None),lambda s:s.update(seller="same")):
   r=copy.deepcopy(self.r)
   for o in r["ask_estimate"]["sources"]:mutate(o)
   self.assertFalse(P.allowed(r))
  r=copy.deepcopy(self.r);r["ask_estimate"]["sources"]=r["ask_estimate"]["sources"][:1];self.assertFalse(P.allowed(r))
 def test_serializer_hold_and_aggregate_no_bypass(self):
  self.assertIsNone(discord.build_payload([{"title":"Unpriced tool","url":"https://fixture.invalid/item","target":90}]))
  self.assertIsNone(discord.build_payload([{"title":"Digest","_mh_product_rows":[{"title":"unpriced"}]}]))
  self.assertIsNotNone(discord.build_payload([{"title":"Health","description":"15 products still in research"}]))
 def test_held_notification_not_acknowledged_and_hottest_not_named(self):
  r={**self.r,"ask_estimate":None};seen={"existing"}
  with patch.object(hub,"send",return_value=204),patch.object(hub,"price_drops",return_value=([],{})),patch.object(hub,"read_prices",return_value={}):
   out=hub.route([r],[],{"scanned":1,"priced":0,"affordable":0,"unpriced":1,"R":0,"A":0,"B":0,"errors":[]},[],seen,dry=True)
  self.assertFalse(any(r["url"] in k for k in out));self.assertNotIn(r["title"],hub.market_pulse([r],{}));self.assertTrue(P.allowed(self.r))
 def test_secondary_offer_price_is_never_delivery(self):
  t="Makita DUB185Z 18V LXT Blower Bare Unit / Makita BL1830 18V Battery - £29.99"
  self.assertIsNone(delivery_cost(t,"Delivery information at checkout"))
  self.assertEqual(delivery_cost(t,"Delivery £5.99"),5.99)
  self.assertIsNone(delivery_cost(t,"Free delivery over £100"))
  self.assertEqual(delivery_cost(t,"Free delivery"),0)
  r=primary({"title":t,"price":39.99,"price_basis":"rss_merchant_price","category":"tools"});self.assertEqual(r["title"],t.split(" / ")[0]);self.assertIsNotNone(market.identity(r))
  self.assertTrue(primary({"title":t,"price":39.99,"category":"tools"}).get("offer_ambiguity"))
 def test_aggregate_price_cannot_be_hidden_or_clipped(self):
  self.assertIsNone(discord.build_payload([{"title":"Digest","_mh_product_rows":[self.r],"description":self.r["url"]}]))
  p=P.proof(self.r);self.assertIsNotNone(discord.build_payload([{"title":"Digest","_mh_product_rows":[self.r],"description":self.r["url"]+f" Sell £{p['listing']:.2f}"}]))
 def test_exact_tool_variants_and_watchlist_reconstruction(self):
  for t in ("Makita DUB185Z 18V Blower Bare Unit","DeWalt DCF887N 18V Impact Driver Body Only","DeWalt DCF887N-XJ 18V Impact Driver Tool Only"):
   i=market.identity({"title":t,"category":"tools"});self.assertIsNotNone(i,t);j=watchlist.ident({"category":"tools","query":i.match,"identity":i.identity});self.assertTrue(market.matches(t,j))
  for t in ("Makita BL1830 Battery","Makita DUB186Z Blower","Makita DUB185Z 12V Blower","Makita DUB185Z with battery","Makita DUB185Z housing only","DeWalt DCF887D2 Kit","DeWalt DT7500-QZ Bit Holder","DeWalt DCF887N with battery charger","DeWalt DCF887N 18V Bare Tool + Case","DeWalt DCF887N 18V Bare + 12 inch Tool Bag"):
   self.assertIsNone(market.identity({"title":t,"category":"tools"}),t)

 def test_tool_battery_aspects_preserve_not_included_but_reject_yes(self):
  from moneyhunter import details
  i=market.identity({'title':'DeWalt DCF887N 18V Bare Tool','category':'tools'})
  o={'item_id':'fixture','item_price':50,'shipping':0,'url':'https://www.ebay.co.uk/itm/123456789000'}
  data={'title':'DeWalt DCF887N 18V Bare Tool','conditionId':'1000','price':{'value':'50','currency':'GBP'},'shippingOptions':[{'shippingCostType':'FIXED','shippingCost':{'value':'0','currency':'GBP'}}],'estimatedAvailabilities':[{'estimatedAvailabilityStatus':'IN_STOCK'}]}
  for value,status in [('No','verified_fields'),('Not Included','verified_fields'),('Yes','conflict')]:
   x={**data,'localizedAspects':[{'name':'Model','value':'DCF887N'},{'name':'Battery Included','value':value}]}
   self.assertEqual(details.assess(x,o,i,dt.datetime.now(dt.timezone.utc))['status'],status)
