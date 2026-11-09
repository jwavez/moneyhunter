"""Task 16 Part D — approximate_priced retired in favour of research_model_only."""
import unittest
from unittest.mock import patch
from moneyhunter import pricing_labels as L

class PricingLabels(unittest.TestCase):
    def test_exact_priced_when_publication_allowed(self):
        row={'ask_estimate':{'suggested_listing':15.13,'estimated_resale':15.0}}
        with patch('moneyhunter.publication.allowed', return_value=True), \
             patch('moneyhunter.publication.proof', return_value={'ok':True,'listing':15.13}):
            self.assertEqual(L.classify(row),'exact_priced')
            self.assertEqual(L.selling_price_of(row),15.13)
    def test_research_model_only_when_estimate_not_allowed(self):
        row={'ask_estimate':{'model':'competitor-asks-v1','suggested_listing':20.0}}
        with patch('moneyhunter.publication.allowed', return_value=False):
            self.assertEqual(L.classify(row),'research_model_only')
            self.assertIsNone(L.selling_price_of(row))
    def test_unpriced_without_estimate(self):
        self.assertEqual(L.classify({}),'unpriced')
    def test_summarize_drops_approximate_alias(self):
        rows=[
            {'ask_estimate':{'suggested_listing':10.0}},  # allowed → exact
            {'ask_estimate':{'model':'competitor-asks-v1'}},  # not allowed → research_model_only
            {},
        ]
        def allowed(r, now=None):
            return bool((r.get('ask_estimate') or {}).get('suggested_listing')==10.0)
        def proof(r, now=None):
            return {'ok':True,'listing':10.0}
        with patch('moneyhunter.publication.allowed', side_effect=allowed), \
             patch('moneyhunter.publication.proof', side_effect=proof):
            s=L.summarize(rows)
        self.assertEqual(s['exact_priced'],1)
        self.assertEqual(s['research_model_only'],1)
        self.assertEqual(s['unpriced'],1)
        self.assertIsNone(s['approximate_priced'])
