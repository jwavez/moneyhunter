"""Offline fixtures; asking prices synthetic, never production sales evidence."""
import copy,datetime as dt,unittest
from unittest.mock import patch
from moneyhunter import market,asking,transport,hub,discord
from tests.test_asking_estimates import RAW,NOW,snap,offer

EDT={'title':'Hugo Boss Boss Bottled Eau de Toilette - 100ml - Free C&C','category':'fragrance','price':45,'url':'https://example.com/synthetic-edt','inbound_delivery':None,'merchant':'Argos','online_eligible':True,'heat':0}
LOTION={**EDT,'title':'Hugo Boss Boss Bottled 100ml Aftershave Lotion','price':26.99,'url':'https://example.com/synthetic-lotion'}

class FragranceCards(unittest.TestCase):
    def test_exact_edt_lotion_and_balm_are_not_the_same_product(self):
        edt=market.identity(EDT);lotion=market.identity(LOTION)
        self.assertIsNotNone(edt);self.assertIsNotNone(lotion)
        self.assertEqual(lotion.match,'boss bottled aftershave lotion 100ml')
        self.assertNotEqual(market.cache_key(edt),market.cache_key(lotion))
        self.assertTrue(market.matches('Hugo Boss Bottled Aftershave Lotion 100ml New',lotion))
        for title in ('Hugo Boss Bottled EDT 100ml','Hugo Boss Bottled EDP 100ml','Hugo Boss Bottled Aftershave Balm 100ml','Boss Bottled 200ml Aftershave Lotion','Boss Bottled Aftershave Lotion 100ml TESTER'):
            self.assertFalse(market.matches(title,lotion),title)
        self.assertFalse(market.matches(LOTION['title'],edt))
    def test_published_profile_is_conditional_with_provenance_and_inclusive_vat(self):
        p=transport.profile(EDT,NOW)
        self.assertEqual(p['postage'],3.75);self.assertEqual(p['checked_at'],'2026-11-07')
        self.assertFalse(p['actual_parcel_verified'])
        self.assertIn('royalmail.com',p['rate_source'])
        self.assertIn('NOT collection or postbox',p['requirements'])
        self.assertIn('ID8000',p['requirements']);self.assertIn('2kg',p['requirements'])
        self.assertIn('exclusions',p['liability'])
    def test_100ml_does_not_get_a_200ml_warning_and_lotion_chemistry_not_guessed(self):
        sc=transport.scenario(LOTION,35,NOW)
        self.assertNotIn('200ml',sc['profile']['reason'])
        self.assertIn('do NOT assume',sc['profile']['reason'])
        self.assertIsNone(sc['net']);self.assertIsNotNone(sc['net_before_unknown_delivery'])
        self.assertFalse(sc['inbound_known'])
    def test_200ml_missing_volume_multipack_and_stale_tariff_do_not_get_small_bottle_rate(self):
        for title in ('Armani Profondo Parfum 200ml','Boss Bottled EDT','Boss Bottled EDT 2 x 100ml','Boss Bottled EDT 50ml or 100ml'):
            self.assertIsNone(transport.profile({**EDT,'title':title},NOW)['postage'],title)
        self.assertIsNone(transport.profile(EDT,NOW+dt.timedelta(days=31))['postage'])
    def test_market_resale_survives_unknown_parcel_cost_but_never_becomes_buy(self):
        s=snap([offer(i,35+i) for i in range(6)])
        m=asking.estimate(EDT,s,NOW)
        self.assertEqual(m['estimated_resale'],33.94)
        self.assertIsNone(m['net']);self.assertIsNone(m['roi']);self.assertIsNone(m['max_landed_buy'])
        self.assertFalse(m['estimated_opportunity']);self.assertFalse(m['worth_reviewing'])
        self.assertEqual(m['transport_scenario']['profile']['postage'],3.75)
        self.assertIsNotNone(m['transport_scenario']['net_before_unknown_delivery'])
        card=hub.watch_card({**EDT,'ask_estimate':m},{})
        text=str(card)
        self.assertIn('Estimated sell price',text);self.assertIn('33.94',text)
        self.assertIn('CONDITIONAL',text);self.assertNotIn('a 200ml bottle exceeds',text)
    def test_scenario_uses_fee_engine_once_and_inbound_cost_is_not_silently_free(self):
        from moneyhunter.fees import net_profit
        sc=transport.scenario({**EDT,'inbound_delivery':4},60,NOW)
        expected=net_profit(60,49,'ebay_business','fragrance',3.75,.5,.03)
        self.assertEqual(sc['net'],expected.net);self.assertEqual(sc['fees'],expected.platform_fee)
        unknown=transport.scenario(EDT,60,NOW)
        self.assertEqual(round(unknown['net_before_unknown_delivery']-sc['net'],2),4)
        self.assertIsNone(unknown['roi'])
    def test_no_comparators_shows_explicit_missing_estimate_not_a_required_price_as_market_value(self):
        card=hub.watch_card(LOTION,{})
        self.assertEqual(card['fields'][0]['name'],'1 · Sell / starting listing')
        self.assertTrue(any(f['name']=='Estimated sell price — competitor asks' for f in card['fields']))
        self.assertIn('Not established',card['fields'][0]['value'])
        self.assertNotIn('200ml',str(card))
    def test_serialized_cards_all_categories_remain_within_discord_limits(self):
        for category,title in [('fragrance',EDT['title']),('fragrance',LOTION['title']),('tech','Sony WF-C510 Yellow'),('gaming','Some Physical Game PS5'),('trainers','Nike HJ5996-003 Womens UK6'),('tools','Bosch Exact Drill 18V')]:
            raw={**EDT,'category':category,'title':title}
            payload=discord.build_payload([hub.watch_card(raw,{})])
            e=payload['embeds'][0];self.assertLessEqual(len(e['fields']),25)
            self.assertTrue(all(len(f['value'])<=1024 for f in e['fields']))
            length=len(e['title'])+len(e['description'])+len(e['footer']['text'])+sum(len(f['name'])+len(f['value']) for f in e['fields'])
            self.assertLessEqual(length,6000)

    def test_more_than_fifty_modeled_offers_survive_export_and_remain_no_send(self):
        import os,tempfile,contextlib,io
        from pathlib import Path
        from moneyhunter import cli
        from tests.test_market_research import item
        r={**EDT,'title':'LEGO Synthetic Moon Rover 75402','category':'lego','inbound_delivery':0,'delivery':'synthetic fixed delivery','desc':''}
        raws=[{**r,'url':f'https://example.com/synthetic-retained-{i}'} for i in range(55)]
        with tempfile.TemporaryDirectory() as td,patch.object(cli,'OPERATIONAL',str(Path(td)/'state.json')),patch.object(cli,'bankroll',return_value=200),patch.object(cli,'ebay_status',return_value='active listings only'),patch.object(cli.hotukdeals,'scan',return_value=raws),patch.object(cli.CP,'load',return_value=[]),patch('moneyhunter.scanners.discovery.scan',return_value=[]),patch('moneyhunter.scanners.discovery.LAST_DIAGNOSTICS',{'errors':[]}),patch('moneyhunter.images.prepare',return_value={}),patch('moneyhunter.scanners.ebay.available',return_value=True),patch('moneyhunter.scanners.ebay.active_items',return_value={'itemSummaries':[item(i) for i in range(5)]}),patch.dict(os.environ,{'MONEYHUNTER_COMMUNITY':'1','MONEYHUNTER_DISABLE_SEND':'1'}),contextlib.redirect_stdout(io.StringIO()):
            _,_,_,_,_,stats=cli.run_scan()
            self.assertEqual(stats['ask_valued'],55)
            self.assertEqual(stats['review_candidates'],55)
            self.assertEqual(len(cli.LAST_REVIEW),55)
