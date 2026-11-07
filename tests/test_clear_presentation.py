"""Offline source-shaped formatting and nonphysical exclusion regressions."""
import copy,datetime as dt,unittest
from unittest.mock import patch
from moneyhunter import product_format as PF,presentation,hub,market,discord,asking
from moneyhunter.scanners import hotukdeals,discovery,ebay
from tests.test_asking_estimates import RAW,offer,snap
NOW=dt.datetime.now(dt.timezone.utc)
class Formats(unittest.TestCase):
 def test_category_store_cannot_override_pc_key(self):
  for t in ('Keyboard Simulator PC Key','Windows 11 Home Licence','LEGO Batman PC‑Key'):
   self.assertTrue(PF.reason({'title':t}),t)
  for merchant in ('Loaded','Unknown shop','Steam','Epic Games','GOG'):
   raw={**RAW,'title':'Lego Batman: Legacy of the Dark Knight - PC Key','category':'lego','merchant':merchant,'price':29.99}
   self.assertTrue(PF.reason(raw));self.assertEqual(hotukdeals.classify(raw['title'],'lego'),'digital');self.assertFalse(hub.resellable(raw));self.assertFalse(hotukdeals.online_status(raw['title']));self.assertIsNone(market.identity(raw))
   self.assertEqual(hub.watch_card(raw,{})['fields'],[]);self.assertIsNone(discord.build_payload([hub.watch_card(raw,{})]))
   with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items') as api:discovery.scan([raw],{'ask_cache':{}},NOW);api.assert_not_called()
 def test_physical_lego_games_keys_and_console_not_digital(self):
  for t in ('Logitech keyboard replacement PC key','LEGO Batman keychain','Sony PS5 Digital Edition Console'):
   self.assertFalse(PF.reason({'title':t}),t)
  raw={'title':'LEGO Batman Legacy of the Dark Knight PS5 physical game','category':'lego'}
  self.assertEqual(PF.normalize(raw)['category'],'gaming');self.assertEqual(hotukdeals.classify(raw['title'],'lego'),'gaming')
  self.assertEqual(PF.normalize({'title':'LEGO Nintendo Mario Kart 72051 building set','category':'lego'})['category'],'lego')
 def test_actual_desktop_with_bundled_game_pass_remains_physical_tech(self):
  raw={'title':'HP OMEN 16L Gaming Desktop, AMD Ryzen 5, 16GB, 1TB, NVIDIA GeForce RTX 5060 Ti 8GB, with Xbox Game Pass with code','category':'gaming','merchant':'HP'}
  self.assertFalse(PF.reason(raw));self.assertEqual(PF.normalize(raw)['category'],'tech');self.assertEqual(hotukdeals.classify(raw['title'],'gaming'),'tech')
  self.assertTrue(PF.reason({'title':'Desktop Dungeons','merchant':'Loaded','category':'gaming'}))
 def test_legacy_rows_quarantined_without_financials_or_clock_changes(self):
  original=[{'title':'LEGO Batman PC Key','category':'lego','url':'https://www.hotukdeals.com/deals/key','price':29.99,'observed_at':'2026-11-07T20:21:00+00:00'}]
  before=copy.deepcopy(original);physical,excluded=PF.partition(original);self.assertEqual(physical,[]);self.assertEqual(original,before);self.assertNotIn('postage',excluded[0]);self.assertNotIn('breakeven',excluded[0])
 def test_digital_guard_all_public_routes_without_acknowledgement(self):
  raw={**RAW,'title':'LEGO Batman PC Key','category':'lego','price':29.99,'heat':700}
  with patch.object(hub,'send',return_value=204) as send,patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([],{})):
   seen=hub.route([raw],[],{'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0,'R':0,'A':0,'B':0},[],set(),dry=True)
   self.assertFalse(any(raw['url'] in str(c) for c in send.call_args_list));self.assertFalse(any('key' in k for k in seen))
class Clarity(unittest.TestCase):
 def model(self,price=34.99,sale=51.03,category='gaming',delivery=None):
  s=snap([offer(0,sale)]);s.update(observed_at=NOW.isoformat(),category=category)
  raw={**RAW,'category':category,'price':price,'inbound_delivery':delivery,'title':'Resident Evil Requiem Xbox Series X'}
  return raw,asking.estimate(raw,s,NOW)
 def test_one_seller_resident_price_profit_same_basis_and_no_buy(self):
  raw,m=self.model();f=presentation.fields(raw,m)
  self.assertIn('51.02',f[0]['value']);self.assertIn('INDICATIVE ONLY',f[0]['value']);self.assertIn('51.02 sale',f[1]['value']);self.assertIn('UNKNOWN',f[1]['value']);self.assertIn('NOT A BUY',f[2]['value'])
  from moneyhunter.fees import net_profit
  from moneyhunter import config as C
  n=net_profit(m['suggested_listing'],raw['price'],'ebay_business','gaming',C.postage_for('gaming'),C.PACKAGING,C.RETURNS_ALLOWANCE).net
  self.assertIn(presentation.signed(n),f[1]['value']);self.assertIn('3.25',f[1]['value'])
 def test_all_categories_unpriced_explicit_no_reliable_estimate(self):
  for cat in hub.CAT_LABEL:
   raw={**RAW,'category':cat,'title':'Physical product','price':20}
   card=hub.watch_card(raw,{})
   self.assertEqual([f['name'] for f in card['fields'][:3]],['1 · Sell / starting listing','2 · Profit at that sale price','3 · Buy conclusion'])
   self.assertIn('No reliable resale estimate',card['fields'][0]['value']);self.assertIn('UNKNOWN',card['fields'][1]['value']);self.assertLessEqual(len(card['fields']),25)
 def test_loss_prominent_above_budget_not_buy_and_stale_not_freshened(self):
  raw,m=self.model(117.99,123.98,'lego');self.assertIn('SKIP',presentation.fields(raw,m)[2]['value']) if not m['above_budget'] else self.assertIn('WATCH ONLY',presentation.fields(raw,m)[2]['value'])
  raw,m=self.model(59,60,'lego',0);self.assertIn('SKIP',presentation.fields(raw,m)[2]['value'])
  stamp=m['observed_at'];m['observed_at']=(NOW-dt.timedelta(hours=7)).isoformat();f=presentation.fields(raw,m);self.assertIn('No reliable',f[0]['value']);self.assertNotEqual(stamp,m['observed_at'])
 def test_fragrance_costs_remain_unknown_no_default_carrier(self):
  raw,m=self.model(26.99,24,'fragrance');f=presentation.fields(raw,m)
  self.assertIn('UNKNOWN',f[1]['value']);self.assertIn('RESEARCH ONLY',f[2]['value']);self.assertIsNone(m['net'])
