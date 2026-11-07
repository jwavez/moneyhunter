"""Offline synthetic API prices only; no production sale or message fixtures."""
import copy, datetime as dt, unittest
from unittest.mock import patch
from moneyhunter import market, variants, research_budget, asking, hub, embeds
from moneyhunter.scanners import discovery, ebay
from tests.test_discovery_policy import Source
from tests.test_asking_estimates import RAW, NOW, offer, snap

class ExactVariants(unittest.TestCase):
    def ident(self,title,cat):return market.identity({'title':title,'category':cat})
    def test_sony_current_models_and_colour_alias(self):
        for title in ('Sony WH-CH520 White','Sony WF-C510 Yellow','Sony WF-C710N Pink','Sony WH-1000XM5 Smoky Pink'):
            with self.subTest(title=title):
                i=self.ident(title,'tech');self.assertIsNotNone(i);self.assertTrue(market.matches(title+' NEW',i))
        i=self.ident('Sony WF-C710N Glass Blue','tech')
        self.assertTrue(market.matches('Sony WFC710N Blue New',i))
        for title in ('Sony WFC710N Pink','Sony WFC710N Blue Charging Case','Sony WFC710N Blue Refurbished','Sony WFC510 Blue'):
            self.assertFalse(market.matches(title,i),title)
    def test_tech_ambiguity_accessories_and_editions(self):
        for title in ('Sony WF-C510 Black or White','Sony WF-C510','Sony WH-CH520 White One Piece Limited Edition','Sony WF-C510 Yellow Replacement Earbud','Sony WFC510 Yellow USB Cable','Sony WH1000XM5 Smoky Pink or Black'):
            self.assertIsNone(self.ident(title,'tech'),title)
    def test_scent_concentration_flanker_volume_format(self):
        i=self.ident('Hugo Boss Boss Bottled Eau de Toilette 100ml','fragrance')
        self.assertIsNotNone(i)
        self.assertTrue(market.matches('BOSS Bottled EDT 100ml New Sealed',i))
        for title in ('Boss Bottled EDP 100ml','Boss Bottled Infinite EDT 100ml','Boss Bottled Night EDT 100ml','Boss Bottled Horizon EDT 100ml','Boss Bottled EDT 200ml','Boss Bottled EDT 100ml refillable','Boss Bottled EDT 100ml Tester','Boss Bottled EDT 100ml Gift Set'):
            self.assertFalse(market.matches(title,i),title)
        self.assertIsNone(self.ident('Boss Bottled EDT 50ml or 100ml','fragrance'))
        self.assertIsNone(self.ident('Boss Bottled EDT 2 x 100ml','fragrance'))
        i=self.ident('Giorgio Armani Acqua di Gio Profondo Parfum 200ml','fragrance')
        self.assertIsNotNone(i)
        for title in ('Armani Acqua di Gio Profondo EDP 200ml','Armani Acqua di Gio Parfum 200ml','Armani Acqua di Gio Profondo Lights Parfum 200ml'):
            self.assertFalse(market.matches(title,i),title)
    def test_condition_in_description_not_lost(self):
        self.assertIsNone(market.identity({'title':'Sony WF-C510 Yellow','category':'tech','desc':'Ex display with marks and discolouration'}))
    def test_trainer_exact_style_colourcode_uk_size_and_adult(self):
        i=self.ident('Nike P-6000 IM9013-001 Womens UK 5 New','trainers')
        self.assertIsNotNone(i)
        self.assertTrue(market.matches('Nike IM9013-001 UK5 US7 EU38 New',i))
        for title in ('Nike IM9013-001 UK4 Womens','Nike IM9013-002 UK5 Womens','Nike IM9013-001 US5 Womens','Nike IM9013-001 UK5 Mens','Nike IM9013-001 UK5 GS','Nike IM9013-001 UK5/6','Nike IM9013-001 UK5 or 6','Nike IM9013-001 UK5 ShoeLaces'):
            self.assertFalse(market.matches(title,i),title)
    def test_trainer_family_is_discovery_only_never_a_valuation(self):
        raw={'title':'Nike P-6000 sizes 4 or 5','category':'trainers','desc':'Style Code: IM9013-001'}
        self.assertIsNone(market.identity(raw))
        seed=variants.trainer(raw,seed=True);self.assertTrue(seed.discovery_seed)
        self.assertTrue(market.matches('Nike IM9013-001 UK5 Womens NEW',seed))
        self.assertFalse(market.matches('Nike IM9013-001 US5 Womens',seed))
        self.assertFalse(market.matches('Nike IM9013-002 UK5 Womens',seed))
    def test_reviewed_lego_anchor_normalises_promo_without_number_only_match(self):
        a=self.ident('LEGO Pokemon Munchlax 72150 Brand New Free Click Collect','lego')
        b=self.ident('LEGO Pokemon Munchlax 72150 building kit','lego')
        self.assertEqual(market.cache_key(a),market.cache_key(b))
        self.assertTrue(market.matches('LEGO 72150 Munchlax NEW',a))
        self.assertFalse(market.matches('LEGO 72150 Munchlax Sticker Sheet',a))
        self.assertFalse(market.matches('LEGO 72150 NEW',a))

class BudgetAndRouting(unittest.TestCase):
    def test_daily_cap_and_day_rollover(self):
        state={'browse_usage':{'date':NOW.date().isoformat(),'calls':799,'by_purpose':{}}}
        self.assertTrue(research_budget.reserve(state,NOW,'acquisition'))
        self.assertFalse(research_budget.reserve(state,NOW,'asking'))
        self.assertTrue(research_budget.reserve(state,NOW+dt.timedelta(days=1),'asking'))
        self.assertEqual(state['browse_usage']['calls'],1)
    def test_fair_category_order_does_not_starve_legacy(self):
        rows=[('lego',str(i)) for i in range(15)]+[(c,'0') for c in ('trainers','tech','fragrance','gaming')]
        result=research_budget.fair_order(rows,lambda x:x[0],lambda x:x[1])
        self.assertEqual([x[0] for x in result[:5]],['trainers','fragrance','tech','lego','gaming'])
    def test_acquisition_batch_uses_actual_exact_variants_and_bounded_calls(self):
        raw={'title':'Nike P-6000 sizes 4 or 5','url':'https://example.com/synthetic-trainer','category':'trainers','desc':'Style Code: IM9013-001','price':50}
        payload=Source().payload()
        for x in payload['itemSummaries']:x['title']='Nike P-6000 IM9013-001 Womens UK5 New'
        state={'ask_cache':{}}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=payload) as call:
            got=discovery.scan([raw],state,NOW)
        self.assertEqual(call.call_count,1);self.assertEqual(len(got),3)
        self.assertTrue(all(market.identity(x).identity['uk_size']==5 for x in got))
        self.assertEqual(state['browse_usage']['calls'],1)
        self.assertEqual(discovery.LAST_DIAGNOSTICS['queries_by_category'],{'trainers':1})
    def test_asking_slots_reach_new_categories_not_just_lego(self):
        raws=[{'title':t,'category':c,'url':f'https://example.com/{n}'} for n,(c,t) in enumerate([
            ('lego','LEGO Synthetic Moon Rover 75402'),('tech','Sony WF-C510 Yellow'),('fragrance','Boss Bottled EDT 100ml'),('trainers','Nike IM9013-001 UK5 Womens')])]
        rows=[{'url':x['url'],'priority':0} for x in raws]
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value={'itemSummaries':[]}) as call:
            health=market.enrich(rows,raws,{'ask_cache':{}},NOW,budget=4)
        self.assertEqual(call.call_count,4)
        self.assertEqual(set(health['queries_by_category']),{'lego','tech','fragrance','trainers'})
    def test_fragrance_market_estimate_cannot_become_profit_or_opportunity(self):
        m=asking.estimate({**RAW,'category':'fragrance','price':10,'inbound_delivery':0},snap([offer(i,100+i) for i in range(6)]),NOW)
        self.assertEqual(m['estimated_resale'],97)
        for k in ('net','roi','max_landed_buy','net_before_unknown_delivery','review_max_landed_buy','outbound_postage'):self.assertIsNone(m[k],k)
        self.assertFalse(m['estimated_opportunity']);self.assertFalse(m['worth_reviewing'])
        self.assertFalse(m['transport_validated'])
        text=str(hub.estimate_fields(m));self.assertIn('Unknown',text);self.assertIn('97.00',text)
    def test_report_preserves_legacy_counts_but_labels_denominators(self):
        stats={'scanned':304,'priced':3,'unpriced':301,'without_any_pricing':280,'affordable':0,'A':0,'B':0,'R':3}
        text=str(embeds.scan_summary(stats,[]))
        self.assertIn('301 without legacy/reference',text);self.assertIn('280 without either',text)
        self.assertIn('Legacy/reference-priced under',text)
