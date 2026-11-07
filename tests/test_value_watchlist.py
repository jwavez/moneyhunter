"""Offline fixtures only. No network, messages, seen resets or live runs."""
import copy, datetime as dt, io, json, unittest, urllib.parse, urllib.error
from unittest.mock import patch
from moneyhunter import market,watchlist,details,asking,hub,config as C
from moneyhunter.scanners import ebay,discovery,capture
from tests.test_discovery_policy import Source
from tests.test_asking_estimates import NOW,RAW

class ValueLed(unittest.TestCase):
    def state(self):
        raw=Source().raw();i=market.identity(raw)
        return {'ask_cache':{market.cache_key(i):market.summary(Source().payload(),i,NOW)}},i
    def test_actual_townfall_marketing_aliases_not_editions_platforms(self):
        names=['SILENT HILL: Townfall - Day One Edition (PS5) New Sealed Game',
               'Silent Hill: Townfall Day One Edition PS5 BRAND NEW AND SEALED = FREE SHIPPING',
               'Silent Hill Townfall (Day One Edition) (PS5)']
        ids=[market.identity({'title':t,'category':'gaming'}) for t in names]
        self.assertTrue(all(ids));self.assertEqual(len({market.cache_key(i) for i in ids}),1)
        for t in ('Silent Hill Townfall PS5','Silent Hill Townfall Day One Edition PS4','Silent Hill Townfall Day One Edition PS5 Digital Key'):
            self.assertFalse(market.matches(t,ids[0]),t)
        self.assertIn('game',market.canonical_game('Squid Game The Challenge Nintendo Switch 2'))
        self.assertNotEqual(market.canonical_game('Squid Game Nintendo Switch'),market.canonical_game('Squid Game Nintendo Switch 2'))
    def test_real_observation_union_keeps_cheaper_clock_and_old_records(self):
        state={'ask_cache':{}}
        for n,(suffix,price) in enumerate([('game',64.99),('free shipping',46.50)]):
            i=watchlist.ident({'category':'gaming','query':'silent hill townfall day one edition ps5 '+suffix})
            payload=Source().payload();payload['itemSummaries']=payload['itemSummaries'][:1]
            o=payload['itemSummaries'][0];o['title']='Silent Hill Townfall Day One Edition PS5';o['itemId']+=str(n);o['price']['value']=str(price);o['shippingOptions'][0]['shippingCost']['value']='0'
            s=market.summary(payload,i,NOW-dt.timedelta(minutes=10+n));state['ask_cache']['legacy-'+str(n)]=s
        watchlist.migrate(state,NOW)
        k=market.cache_key(watchlist.ident(state['ask_cache']['legacy-0']))
        merged=state['ask_cache'][k];self.assertEqual(merged['listed_total_low'],46.5)
        self.assertEqual(merged['observed_at'],state['ask_cache']['legacy-1']['observed_at'])
        self.assertEqual(len(merged['offers']),2);self.assertIn('legacy-0',state['ask_cache'])
    def test_watchlist_is_fresh_financial_target_not_approval(self):
        s,i=self.state();health=watchlist.build(s,NOW,inspect=False);e=s['value_watchlist'][market.cache_key(i)]
        self.assertEqual(health['usable_targets'],1);self.assertLessEqual(e['max_landed_buy'],60)
        self.assertEqual(e['max_landed_buy'],asking.max_cost(e['estimated_resale'],'lego'))
        self.assertEqual(e['competition_low'],22);self.assertIn('not purchase approval',e['cost_basis'])
        watchlist.build(s,NOW+dt.timedelta(hours=7),inspect=False)
        self.assertIsNone(s['value_watchlist'][market.cache_key(i)]['max_landed_buy'])
    def test_sparse_coupon_and_perfume_remain_research(self):
        for mode in ('sparse','coupon','fragrance'):
            s,i=self.state();snapshot=s['ask_cache'][market.cache_key(i)]
            if mode=='sparse':snapshot['offers']=snapshot['offers'][:2]
            if mode=='coupon':snapshot['offers'][0]['available_coupons']=True
            if mode=='fragrance':
                snapshot['category']='fragrance';snapshot['query']='boss bottled EDT 100ml';snapshot['identity']={'condition':'new','family':'boss bottled','ml':100,'concentration':'edt'}
            h=watchlist.build(s,NOW,inspect=False);self.assertEqual(h['usable_targets'],0,mode)
    def test_persistent_query_survives_no_current_feed_and_checks_landed(self):
        s,i=self.state();watchlist.build(s,NOW,inspect=False)
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=Source().payload()) as api:
            rows=discovery.scan([],s,NOW)
            self.assertEqual(rows,[]) # item price22+shipping2 exceeds true ceiling
            self.assertEqual(api.call_count,1);kwargs=api.call_args.kwargs
            self.assertEqual(kwargs['sort'],'price');self.assertGreater(kwargs['max_item_price'],0)
            self.assertEqual(discovery.LAST_DIAGNOSTICS['price_led_queries'],1)
            discovery.scan([],s,NOW+dt.timedelta(hours=1));self.assertEqual(api.call_args.kwargs['sort'],'newlyListed')
    def test_global_quota_blocks_both_detail_and_search(self):
        s,i=self.state();watchlist.build(s,NOW,inspect=False)
        with patch.object(ebay,'available',return_value=True),patch('moneyhunter.research_budget.reserve',return_value=False),patch.object(ebay,'active_items') as api:
            discovery.scan([],s,NOW);api.assert_not_called()
    def test_documented_sort_filter_and_single_getitem_encoding(self):
        def response():return io.BytesIO(b'{}')
        with patch.object(ebay,'_auth',return_value='offline-fixture'),patch.object(ebay.urllib.request,'urlopen',side_effect=lambda *a,**kw:response()) as api:
            ebay.active_items('Sony & exact',business_only=True,sort='price',max_item_price=18.66)
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(api.call_args.args[0].full_url).query)
            self.assertEqual(q['sort'],['price']);self.assertIn('price:[..18.66]',q['filter'][0]);self.assertIn('BUSINESS',q['filter'][0])
            ebay.item_details('v1|123456789012|0');self.assertTrue(api.call_args.args[0].full_url.endswith('/item/v1%7C123456789012%7C0'))
        for bad in (0,-1,float('nan'),True):
            with self.assertRaises(ValueError):ebay.active_items('q',max_item_price=bad)
        with self.assertRaises(ValueError):ebay.item_details('https://127.0.0.1/private')

class ExactDetails(unittest.TestCase):
    def fixture(self):
        i=market.identity({'category':'fragrance','title':'Hugo Boss Boss Bottled Eau de Toilette 100ml'})
        o=Source().payload()['itemSummaries'][0];o['title']='Hugo Boss Boss Bottled Eau de Toilette 100ml'
        s=market.summary({'itemSummaries':[o]},i,NOW);offer=s['offers'][0]
        data={**o,'estimatedAvailabilities':[{'estimatedAvailabilityStatus':'IN_STOCK'}],
            'localizedAspects':[{'name':'Volume','value':'100ml'},{'name':'Type','value':'Eau de Toilette'}]}
        return i,s,offer,data
    def test_actual_declared_variant_fields_verify_not_authenticity(self):
        i,s,o,d=self.fixture();r=details.assess(d,o,i,NOW)
        self.assertEqual(r['status'],'verified_fields');self.assertEqual(r['checked_item_price'],20);self.assertIn('NOT authenticity',r['meaning'])
    def test_20ml_empty_missing_lotion_variation_or_changed_price_do_not_verify(self):
        i,s,o,d=self.fixture()
        for mutate in ('volume','missing','lotion','variation','price','stock','condition'):
            x=copy.deepcopy(d)
            if mutate=='volume':x['localizedAspects'][0]['value']='20ml'
            if mutate=='missing':x['localizedAspects']=[]
            if mutate=='lotion':x['localizedAspects'][1]['value']='Aftershave Lotion'
            if mutate=='variation':x['primaryItemGroup']={'itemGroupId':'synthetic'}
            if mutate=='price':x['price']['value']='1'
            if mutate=='stock':x['estimatedAvailabilities']=[{'estimatedAvailableQuantity':0}]
            if mutate=='condition':x['conditionId']='3000'
            self.assertNotEqual(details.assess(x,o,i,NOW)['status'],'verified_fields',mutate)
    def test_cached_detail_tied_to_identity_price_and_ttl(self):
        i,s,o,d=self.fixture();state={'ask_cache':{}}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'item_details',return_value=d) as api:
            details.inspect_snapshot(s,i,state,NOW);details.inspect_snapshot(s,i,state,NOW+dt.timedelta(minutes=1));self.assertEqual(api.call_count,1)
            changed=copy.deepcopy(s);changed['offers'][0]['item_price']=19
            details.inspect_snapshot(changed,i,state,NOW+dt.timedelta(minutes=2));self.assertEqual(api.call_count,2)
            details.inspect_snapshot(s,i,state,NOW+dt.timedelta(minutes=31));self.assertEqual(api.call_count,3)
    def test_permission_failure_pauses_details_no_retry_no_fallback(self):
        i,s,o,d=self.fixture();state={'ask_cache':{}}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'item_details',side_effect=urllib.error.HTTPError('https://api.ebay.com',403,'forbidden',{},None)) as api:
            details.inspect_snapshot(s,i,state,NOW);details.inspect_snapshot(s,i,state,NOW+dt.timedelta(hours=1));self.assertEqual(api.call_count,1)
            self.assertIn('browse_details_blocked',state)
    def test_four_detail_calls_bounded_and_pending_does_not_raise_low(self):
        i,s,o,d=self.fixture();state={'ask_cache':{},'detail_run':{'calls':4,'cached':0,'errors':[]}}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'item_details') as api:
            result=details.inspect_snapshot(s,i,state,NOW);api.assert_not_called()
            self.assertEqual(result['offers'][0]['listed_total'],22);self.assertEqual(result['detail_status'],'awaiting_detail_budget')
    def test_low_detail_cannot_validate_a_different_independent_listing(self):
        from tests.test_asking_estimates import snap,offer
        s=snap([offer(i,100+i) for i in range(6)])
        s.update(detail_required=True,detail_status='verified_fields',lowest_detail={'item_id':'not-the-low','checked_item_price':100})
        m=asking.estimate({**RAW,'price':20,'inbound_delivery':0},s,NOW)
        self.assertFalse(m['estimated_opportunity']);self.assertFalse(m['worth_reviewing'])

class RetailPreserved(unittest.TestCase):
    def test_all18_retail_feeds_and_10minute_capture_still_connected(self):
        self.assertEqual(sum(len(paths) for paths in C.FEEDS.values()),18)
        self.assertIn('crons = ["*/10 * * * *"]',open('worker/wrangler.toml').read())
        self.assertIn('capture.merge(raws, capture.scan',open('moneyhunter/cli.py').read())
    def test_retailer_original_image_price_url_not_overwritten_by_ebay(self):
        retail={**Source().raw(),'thumb':'original-retailer-photo','url':'https://www.hotukdeals.com/deals/synthetic-retail','price':10,'merchant':'Retailer'}
        snapshot=copy.deepcopy(retail)
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=Source().payload()):extra=discovery.scan([retail],{'ask_cache':{}},NOW)
        self.assertEqual(retail,snapshot);self.assertTrue(extra);self.assertNotEqual(extra[0]['url'],retail['url'])
        self.assertEqual(capture.merge([retail],[{**retail,'price':30}]),[retail])
    def test_ebay_volume_does_not_starve_retail_category_notifications(self):
        retail={**RAW,'category':'gaming','title':'Synthetic Physical Retail Game PS5','url':'https://www.hotukdeals.com/deals/synthetic-retail','merchant':'Retailer','price':15,'heat':0,'review_priority':0}
        extras=[{**retail,'url':f'https://www.ebay.co.uk/itm/{1000+n}','source':'ebay_browse','review_priority':100} for n in range(8)]
        with patch.object(hub,'acquisition_status',return_value='live'),patch.object(hub,'send',return_value=204) as send,patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([],{})):
            hub.route(extras+[retail],[],{'errors':[],'scanned':9,'priced':0,'A':0,'B':0},[],set(),dry=True)
            category=[c for c in send.call_args_list if c.args[0]==hub.CAT_CHANNEL['gaming']]
            self.assertEqual(len(category),3);self.assertIn(retail['url'],str(category[0]))
    def test_retail_candidate_gets_same_independent_comps_as_ebay_without_overwrite(self):
        raw=Source().raw();i=market.identity(raw);retail={**raw,'url':'https://www.hotukdeals.com/deals/synthetic-retail','merchant':'Retailer'}
        eb={**raw,'url':'https://www.ebay.co.uk/itm/987654321000','source':'ebay_browse','source_observed_at':NOW.isoformat()}
        rows=[{'url':eb['url']},{'url':retail['url']}]
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=Source().payload()) as api:
            market.enrich(rows,[eb,retail],{'ask_cache':{}},NOW,budget=1)
            self.assertEqual(api.call_count,1);self.assertTrue(all(r.get('ask_context') for r in rows))

class OtherRiskyVariants(unittest.TestCase):
    def test_sony_model_colour_and_trainer_style_size_gender_aspects(self):
        cases=[('tech','Sony WF-C510 Yellow',[('Model','WF-C510'),('Colour','Yellow')]),
               ('trainers','Nike Air Max 90 DM0029-012 UK 9 Mens Black',[('Style Code','DM0029-012'),('UK Shoe Size','9'),('Department','Men')])]
        for cat,title,aspects in cases:
            i=market.identity({'category':cat,'title':title});row=Source().payload()['itemSummaries'][0];row['title']=title
            snapshot=market.summary({'itemSummaries':[row]},i,NOW);offer=snapshot['offers'][0]
            data={**row,'estimatedAvailabilities':[{'estimatedAvailableQuantity':2}],'localizedAspects':[{'name':k,'value':v} for k,v in aspects]}
            self.assertEqual(details.assess(data,offer,i,NOW)['status'],'verified_fields')
            if cat=='tech':data['localizedAspects'][1]['value']='Black'
            else:data['localizedAspects'][1]['value']='8'
            self.assertEqual(details.assess(data,offer,i,NOW)['status'],'conflict')
