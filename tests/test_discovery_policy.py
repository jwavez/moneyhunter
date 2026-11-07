"""Offline synthetic fixtures only; no sales, deliveries or accounts contacted."""
import copy
import datetime as dt
import os
import unittest
from unittest.mock import patch
from moneyhunter import asking, market, policy, runtime, hub
from moneyhunter.scanners import discovery, ebay
from tests.test_asking_estimates import RAW, NOW, offer, snap

class Policy(unittest.TestCase):
    def test_distinct_manual_review_and_strong(self):
        m=asking.estimate({**RAW,'price':60,'inbound_delivery':0},snap([offer(i,100+i) for i in range(6)]),NOW)
        self.assertFalse(m['estimated_opportunity']);self.assertTrue(m['worth_reviewing'])
        self.assertGreaterEqual(m['net'],10);self.assertGreaterEqual(m['roi'],20)
        self.assertIn('MANUAL',m['signal'])
    def test_above_budget_never_promoted_even_when_profitable(self):
        m=asking.estimate({**RAW,'price':70,'inbound_delivery':0},snap([offer(i,150+i) for i in range(6)]),NOW)
        self.assertTrue(m['above_budget']);self.assertFalse(m['estimated_opportunity']);self.assertFalse(m['worth_reviewing'])
        self.assertIn('WATCH ONLY',m['signal'])
    def test_missing_delivery_and_sparse_comps_never_manual_review(self):
        for raw,xs in [({**RAW,'inbound_delivery':None},[offer(i,100+i) for i in range(6)]),(RAW,[offer(0,100)])]:
            m=asking.estimate(raw,snap(xs),NOW);self.assertFalse(m['worth_reviewing']);self.assertFalse(m['estimated_opportunity'])
    def test_exact_tiers_and_safe_fallback(self):
        for index,cap in enumerate((60,120,300,600,1200)):
            with self.subTest(index=index),patch.dict(os.environ,{'MH_TIER':str(index),'MH_TIER_WARNING':''}):
                self.assertEqual(policy.current()['cap'],cap)
        for value in ('bad','-1','5'):
            with patch.dict(os.environ,{'MH_TIER':value}):self.assertEqual(policy.current()['cap'],60)
        with patch.dict(os.environ,{'MH_TIER':'4','MH_TIER_WARNING':'fallback'}):self.assertEqual(policy.current()['cap'],60)
    def test_exact_sony_model_colour_and_accessory(self):
        raw={'category':'tech','title':'Sony WH-1000XM5 Wireless Headphones Black','price':120}
        ident=market.identity(raw);self.assertIsNotNone(ident)
        self.assertTrue(market.matches('Sony WH1000XM5 Headphones Black NEW',ident))
        for title in ('Sony WH1000XM4 Headphones Black','Sony WH1000XM5 Headphones Silver','Sony WH1000XM5 Black Replacement Ear Pads','Sony WH1000XM5 Black Refurbished'):
            self.assertFalse(market.matches(title,ident),title)
        self.assertIsNone(market.identity({**raw,'title':'Sony WH1000XM5 Headphones'}))

class Source(unittest.TestCase):
    def payload(self):
        return {'itemSummaries':[{'itemId':f'v1|{123456789000+i}|0','itemWebUrl':f'https://www.ebay.co.uk/itm/{123456789000+i}',
            'seller':{'username':f'synthetic-{i}'},'buyingOptions':['FIXED_PRICE'],'conditionId':'1000','title':'LEGO Synthetic Moon Rover 75402 New Sealed',
            'itemLocation':{'country':'GB'},'price':{'value':str(20+i),'currency':'GBP'},
            'shippingOptions':[{'shippingCostType':'FIXED','shippingCost':{'value':'2','currency':'GBP'}}]} for i in range(8)]}
    def raw(self):return {**RAW,'category':'lego','title':'LEGO Synthetic Moon Rover 75402','price':20}
    def test_live_source_bounded_delivery_self_exclusion_and_durable_cooldown(self):
        state={'ask_cache':{}};raw=self.raw()
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=self.payload()) as call:
            rows=discovery.scan([raw],state,NOW)
            self.assertEqual(len(rows),3);self.assertEqual(call.call_count,1)
            self.assertEqual(rows[0]['inbound_delivery'],2)
            self.assertEqual(rows[0]['source'],'ebay_browse')
            ident=market.identity(raw);m=asking.estimate(rows[0],market.summary(self.payload(),ident,NOW),NOW)
            self.assertNotIn(market.cache_key(ident),state['ask_cache'])
            call.assert_called_once_with(ident.match,business_only=True)
            self.assertEqual(m['acquisition_excluded'],1);self.assertEqual(m['competition_low'],23)
            discovery.scan([raw],state,NOW+dt.timedelta(minutes=2));self.assertEqual(call.call_count,1)
            state.update({'items':{}});counts=runtime.observe(rows,state,NOW);self.assertEqual(counts['new'],3)
            self.assertEqual(runtime.observe(rows,state,NOW)['rescanned'],3)
    def test_permission_block_shared_no_retry_and_no_browser_fallback(self):
        import urllib.error
        state={'ask_cache':{}}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',side_effect=urllib.error.HTTPError('https://api.ebay.com',403,'forbidden',{},None)) as call:
            self.assertEqual(discovery.scan([self.raw()],state,NOW),[])
            discovery.scan([self.raw()],state,NOW+dt.timedelta(hours=2));self.assertEqual(call.call_count,1)
            self.assertIn('browse-blocked',state['ask_cache'])
    def test_api_listing_status_never_uses_challenged_html(self):
        raw={**self.raw(),'source':'ebay_browse','source_observed_at':NOW.isoformat()}
        self.assertEqual(discovery.status(raw,NOW),'live')
        self.assertEqual(discovery.status(raw,NOW+dt.timedelta(minutes=16)),'unknown')
        with patch.object(discovery,'status',return_value='unknown'),patch.object(hub.hotukdeals,'live_status',side_effect=AssertionError('must not fetch eBay HTML')):
            self.assertEqual(hub.acquisition_status(raw),'unknown')
    def test_auctions_and_unknown_shipping_not_acquisition(self):
        payload=self.payload()
        for row in payload['itemSummaries']:row['buyingOptions']=['AUCTION']
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=payload):
            self.assertEqual(discovery.scan([self.raw()],{'ask_cache':{}},NOW),[])

class Boundaries(unittest.TestCase):
    def test_cost_ceiling_cent_boundary_matches_fee_policy(self):
        from moneyhunter.fees import net_profit
        from moneyhunter import config as C
        proceeds=net_profit(100,0,'ebay_business','gaming',C.postage_for('gaming'),.5,.03).net
        ceiling=policy.ceiling(proceeds,10,.2,60)
        self.assertGreaterEqual(proceeds-ceiling,10)
        self.assertGreaterEqual((proceeds-ceiling)/ceiling,.2)
        self.assertTrue(ceiling==60 or proceeds-ceiling-.01<10 or (proceeds-ceiling-.01)/(ceiling+.01)<.2)
    def test_review_to_strong_routes_separately_never_buy_and_no_html(self):
        from unittest.mock import patch
        model=asking.estimate({**RAW,'price':60,'inbound_delivery':0},snap([offer(i,100+i) for i in range(6)]),NOW)
        raw={**RAW,'price':60,'inbound_delivery':0,'heat':0,'ask_estimate':model,'source':'ebay_browse'}
        with patch.object(hub,'acquisition_status',return_value='live'),patch.object(hub,'send',return_value=204) as send,patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([],{})):
            seen=hub.route([raw],[],{'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0,'A':0,'B':0,'R':0},[],set(),dry=True,max_cards=1)
            self.assertTrue(any(k.startswith('review:') for k in seen))
            self.assertNotIn('buy-now',[c.args[0] for c in send.call_args_list if c.args[1][0].get('author')])
            raw['ask_estimate']={**model,'estimated_opportunity':True,'worth_reviewing':False,'signal':'ESTIMATED OPPORTUNITY — CHECK BEFORE BUYING'}
            after=hub.route([raw],[],{'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0,'A':0,'B':0,'R':0},[],seen,dry=True,max_cards=1)
            self.assertTrue(any(k.startswith('estimated:') for k in after))
    def test_above_budget_routing_watch_only(self):
        m=asking.estimate({**RAW,'price':70,'inbound_delivery':0},snap([offer(i,150+i) for i in range(6)]),NOW)
        raw={**RAW,'price':70,'inbound_delivery':0,'heat':0,'ask_estimate':m}
        with patch.object(hub,'acquisition_status',return_value='live'),patch.object(hub,'send',return_value=204) as send,patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([],{})):
            seen=hub.route([raw],[],{'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0,'A':0,'B':0,'R':0},[],set(),dry=True,max_cards=1)
            self.assertFalse(any(k.startswith(('review:','estimated:','alert:')) for k in seen))
            self.assertTrue(any('WATCH ONLY' in str(c.args[1]) for c in send.call_args_list))

class Stress(unittest.TestCase):
    def test_low_margin_review_must_survive_scenario_not_just_twenty_percent(self):
        # Synthetic £50 cost, about £11 modeled net: cheap-threshold-only would pass;
        # lower resale scenario fails the stronger capital-protection requirement.
        for cost in range(20,61):
            for sale in range(40,110):
                m=asking.estimate({**RAW,'price':cost,'inbound_delivery':0},snap([offer(i,sale+i) for i in range(6)]),NOW)
                if m['net']>=10 and m['roi']>=20 and not m['review_stress_passed']:
                    self.assertFalse(m['worth_reviewing']);return
        self.fail('fixture must exercise a nominally profitable but stress-failing trade')
    def test_wide_spread_does_not_gain_lower_roi_review(self):
        m=asking.estimate({**RAW,'price':60,'inbound_delivery':0},snap([offer(i,100+i) for i in range(3)]+[offer(i,200+i) for i in range(3,6)]),NOW)
        self.assertFalse(m['estimated_opportunity']);self.assertFalse(m['worth_reviewing'])

class Refresh(unittest.TestCase):
    def test_new_acquisition_forces_all_seller_refresh_not_business_only_cache(self):
        raw={**Source().raw(),'source':'ebay_browse','source_observed_at':NOW.isoformat()}
        ident=market.identity(raw);old=market.summary(Source().payload(),ident,NOW-dt.timedelta(hours=1))
        state={'ask_cache':{market.cache_key(ident):old}}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=Source().payload()) as call:
            rows=[{'url':raw['url']}];market.enrich(rows,[raw],state,NOW)
            call.assert_called_once_with(ident.match)
            self.assertEqual(rows[0]['ask_context']['observed_at'],NOW.isoformat(timespec='seconds'))
    def test_query_budget_does_not_fall_back_to_old_pre_acquisition_snapshot(self):
        raw={**Source().raw(),'source':'ebay_browse','source_observed_at':NOW.isoformat()}
        ident=market.identity(raw);old=market.summary(Source().payload(),ident,NOW-dt.timedelta(hours=1))
        state={'ask_cache':{market.cache_key(ident):old}};rows=[{'url':raw['url']}]
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',side_effect=AssertionError('budget exhausted')):
            market.enrich(rows,[raw],state,NOW,budget=0)
            self.assertNotIn('ask_context',rows[0]);self.assertEqual(state['ask_cache'][market.cache_key(ident)]['observed_at'],old['observed_at'])

class ActualIntakeCorrection(unittest.TestCase):
    def test_actual_xbox_digital_key_never_spends_physical_acquisition_budget(self):
        self.assertIsNone(market.identity({'title':'Alan Wake 2 Deluxe Edition Xbox Series X S Europe UK Key','category':'gaming'}))
        self.assertIsNotNone(market.identity({'title':'Little Nightmares II Xbox Series X','category':'gaming'}))
    def test_first_query_prefers_known_exact_shipped_catalog_not_alphabetical_noise(self):
        raw=Source().raw();ident=market.identity(raw)
        state={'ask_cache':{market.cache_key(ident):{'sample_count':8}}}
        other={**raw,'title':'A Different Physical Game PS5','category':'gaming'}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=Source().payload()) as call:
            discovery.scan([other,raw],state,NOW)
            self.assertEqual(call.call_args_list[0].args,(ident.match,))
            self.assertEqual(call.call_count,2)  # additive four-query batch retains known-catalog priority
            self.assertEqual(discovery.LAST_DIAGNOSTICS['query'],ident.match)
            self.assertEqual(discovery.LAST_DIAGNOSTICS['matched_shipped_samples'],8)

class ActualMarketingNoise(unittest.TestCase):
    def test_actual_sealed_marketing_does_not_hide_cheaper_exact_competition(self):
        titles=['Little Nightmares II Enhanced Edition Xbox Series X BRAND NEW AND SEALED',
                'Little Nightmares II Enhanced Edition - Xbox Series X',
                'Little Nightmares II Enhanced Edition Xbox Series X IN STOCK FREE P&P']
        ids=[market.identity({'title':t,'category':'gaming'}) for t in titles]
        self.assertEqual(len({i.match for i in ids}),1)
        self.assertIn('enhanced edition',ids[0].match)
        payload=Source().payload();payload['itemSummaries']=payload['itemSummaries'][:3]
        for row,title,price in zip(payload['itemSummaries'],titles,[16.95,18.85,26.59]):
            row['title']=title;row['price']['value']=str(price)
            row['shippingOptions'][0]['shippingCost']['value']='0'
        snapshot=market.summary(payload,ids[0],NOW)
        self.assertEqual(snapshot['sample_count'],3)
        raw={**RAW,'title':titles[0],'price':16.95,'inbound_delivery':0,'merchant':'eBay','ebay_item_id':payload['itemSummaries'][0]['itemId']}
        m=asking.estimate(raw,snapshot,NOW)
        self.assertEqual(m['competition_low'],18.85)
        self.assertLess(m['estimated_resale'],18.85)
        self.assertFalse(m['worth_reviewing']);self.assertFalse(m['estimated_opportunity'])
