"""Offline synthetic image regression tests; no requests or Discord posts."""
import copy
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from moneyhunter import images, hub, embeds, intel, market
from moneyhunter.scanners import discovery, ebay, hotukdeals
from tests import test_discovery_policy as discovery_fixtures
from tests.test_asking_estimates import NOW
PHOTO='https://images.hotukdeals.com/threads/raw/test/123_1/re/150x150/qt/55/123.jpg'
EBAY='https://i.ebayimg.com/images/g/synthetic/s-l500.jpg'
RAW={'title':'LEGO Synthetic Moon Rover 75402 New Sealed','category':'lego','url':'https://www.hotukdeals.com/deals/synthetic','price':20,'merchant':'Amazon','thumb':PHOTO,'inbound_delivery':0}
class ProductImages(unittest.TestCase):
    def test_public_approved_https_images_only(self):
        for bad in ['http://i.ebayimg.com/x.jpg','https://localhost/x','https://127.0.0.1/x','https://i.ebayimg.com.evil/x','https://a:b@i.ebayimg.com/x','https://i.ebayimg.com:444/x','https://i.ebayimg.com/logo.png','https://i.ebayimg.com/x.svg','data:image/png,x',None]:
            self.assertEqual(images.safe(bad),'',str(bad))
        self.assertEqual(images.safe(PHOTO),PHOTO) # validation must not invent another URL
        self.assertEqual(images.safe(EBAY),EBAY)
    def test_rss_media_content_thumbnail_enclosure_and_description(self):
        for body in [f'<media:content url="{PHOTO}"/>',f'<media:thumbnail url="{PHOTO}"/>',f'<enclosure url="{PHOTO}" type="image/jpeg"/>',f'<description><![CDATA[<img src="{PHOTO}">]]></description>']:
            item=ET.fromstring('<item xmlns:media="http://search.yahoo.com/mrss/">'+body+'</item>')
            self.assertEqual(images.feed(item,hotukdeals.NS),images.safe(PHOTO))
    def test_own_listing_photo_never_overwritten_by_reference(self):
        rows=[copy.deepcopy(RAW),{**RAW,'url':'https://www.ebay.co.uk/itm/123456789000','thumb':EBAY}]
        images.enrich(rows);self.assertEqual(rows[1]['thumb'],EBAY)
    def test_reference_is_exact_set_not_accessory_or_other_set(self):
        for title in ['LEGO Synthetic Moon Rover 75403','LEGO Synthetic Moon Rover 75402 used','LEGO Synthetic Moon Rover 75402 instructions only','LEGO Synthetic Galactic Robot 75402']:
            rows=[copy.deepcopy(RAW),{**RAW,'title':title,'thumb':'','url':'https://www.ebay.co.uk/itm/123456789000'}]
            images.enrich(rows);self.assertFalse(rows[1]['thumb'],title)
        rows=[copy.deepcopy(RAW),{**RAW,'thumb':'','url':'https://www.ebay.co.uk/itm/123456789000'}];images.enrich(rows)
        self.assertEqual(rows[1]['thumb'],images.safe(PHOTO));self.assertIn('Reference',rows[1]['image_basis']);self.assertEqual(rows[1]['image_source_url'],RAW['url'])
    def test_browse_own_image_survives_source_summary(self):
        payload=discovery_fixtures.Source().payload()
        for x in payload['itemSummaries']:x['image']={'imageUrl':EBAY}
        with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value=payload):
            rows=discovery.scan([copy.deepcopy(RAW)],{'ask_cache':{}},NOW)
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['thumb']==EBAY and r['image_source_url']==r['url'] for r in rows))
    def test_watch_abovebudget_and_mini_use_clear_full_image(self):
        for row in [RAW,{**RAW,'price':90},{**RAW,'category':'tech'}]:
            self.assertEqual(hub.watch_card(row,{})['image']['url'],images.safe(PHOTO))
        self.assertEqual(hub.mini(RAW,0)['image']['url'],images.safe(PHOTO))
    def test_summary_distinguishes_rescans_and_asking_estimates(self):
        text=embeds.quiet_card({'scanned':307,'priced':3,'new':10,'rescanned':297,'ask_valued':20,'above_budget_estimates':5},'pulse')['description']
        for part in ['10 new / 297 rescans','20 competitor-ask estimates','3 legacy/reference valuations','0 Strong CHECK','5 above-budget']:self.assertIn(part,text)
    def test_fragrance_transport_not_pretended_valid_or_returns_guaranteed(self):
        card=hub.watch_card({**RAW,'category':'fragrance','title':'Armani Profondo Parfum 200ml','price':89.99},{})
        self.assertIn('Unknown until compliant',card['fields'][0]['value']);self.assertIn('prohibits perfume',card['footer']['text'])
        self.assertNotIn('14-day',intel.retailer('Amazon')['label'])

    def test_graded_cards_use_full_image(self):
        from moneyhunter import grading as G
        d=G.Deal('LEGO Synthetic Moon Rover','https://www.ebay.co.uk/itm/123456789000',20,'lego','synthetic',target=50,stretch=60)
        d.thumb=EBAY
        self.assertEqual(embeds.deal_card(d,G.grade(d,200))[0]['image']['url'],EBAY)
